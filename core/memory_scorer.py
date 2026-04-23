"""LLM-driven memory scorer.

Replaces the keyword-matching scoring in character_state.py with a call to the
same local llama.cpp ChatEngine used for the main reply. The scorer returns a
validated delta payload that the storage layer in character_state.py then
applies in exactly the same way it applied the old keyword-derived deltas.

Design notes
------------
* The scorer is pure: it takes state in, returns a payload out. It never
  mutates the character dict itself. character_state.apply_message_to_character_memory
  remains responsible for clamping and writing.
* If the model call fails, returns malformed JSON, or returns values outside
  the allowed ranges, we fall back to the deterministic keyword scorer so
  memory never silently stops updating.
* Runs synchronously. Caller blocks until deltas return. This matches the
  user's selection.
* Covers deltas + open_threads + knowledge (suspicions/unknowns) per spec.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contract with the storage layer
# ---------------------------------------------------------------------------
# These are the fields the scorer is allowed to touch. Any extra keys coming
# back from the model are dropped by _validate_delta_payload.
RELATIONSHIP_DELTA_FIELDS = (
    'trust', 'affection', 'respect', 'fear',
    'resentment', 'openness', 'attraction',
)
EMOTIONAL_DELTA_FIELDS = (
    'confidence', 'anxiety', 'hope', 'guilt', 'anger', 'loneliness',
)

# Deltas are tightly bounded. The model can ask for big moves on big events,
# but not arbitrary ones, and the storage layer still clamps final values
# to [0, 100].
DELTA_MIN = -15
DELTA_MAX = 15

# Open-thread and knowledge mutations are capped so a chatty model can't
# blow up memory storage.
MAX_NEW_THREADS_PER_TURN = 2
MAX_RESOLVED_THREADS_PER_TURN = 3
MAX_NEW_KNOWLEDGE_PER_TURN = 2

# Maximum characters we keep for any free-text field the model produces.
SUMMARY_MAX_CHARS = 220
INTERPRETATION_MAX_CHARS = 180
REASON_MAX_CHARS = 140
THREAD_MAX_CHARS = 180
KNOWLEDGE_MAX_CHARS = 160


def empty_delta_payload() -> dict[str, Any]:
    """The canonical shape the storage layer expects. Also the fallback value
    when everything goes wrong and we need to return *something* safely."""
    return {
        'relationship_deltas': {field: 0 for field in RELATIONSHIP_DELTA_FIELDS},
        'emotional_deltas': {field: 0 for field in EMOTIONAL_DELTA_FIELDS},
        'summary': '',
        'interpretation': '',
        'reason': '',
        'emotion_tags': [],
        'importance': 45,
        'new_open_threads': [],
        'resolved_thread_ids': [],
        'new_suspicions': [],
        'new_unknowns': [],
        'level_points_earned': 0.0,
    }


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SCORER_SYSTEM_PROMPT = """You are a memory scoring module for a roleplay chat system. Your job is to observe the latest message in a conversation and decide how a specific character's internal state should shift as a result.

You will output a single JSON object. No prose, no code fences, no commentary. Just the JSON.

Scoring principles:
- Be conservative. Most messages are ordinary and produce small deltas (-2 to +2).
- Reserve large deltas (|8| to |15|) for clearly significant moments: betrayal, confession, threat, major help, declaration of feelings, shared trauma.
- A delta of 0 is correct when a dimension is not touched by the message.
- Read the message in context. "You're not stupid" is a compliment. "I don't trust you" is a loss of trust. Sarcasm, negation, and tone matter.
- If the message is the character's own dialogue (role=assistant), score it as self-expression. Do not treat the character's own fear dialogue as evidence the user scared them.
- Only add new open threads for genuinely new narrative hooks the character should remember to pursue. Do not restate existing threads.
- Only add suspicions or unknowns when the message actually creates one. Most turns will have none.
- Level Points: Score level_points_earned based on User behavior: surprising character (+1), respectful challenges (+0.5 to +1.5), showing understanding (+1.0 to +1.8), maintaining composure (+0.8 to +1.1), or offering helpful distractions (+0.9 to +1.5). Extraordinary interactions can earn up to 4.0. Max total 4.0. Default 0.0.

Schema (all fields required, use empty arrays or zeros when nothing applies):
{
  "relationship_deltas": {
    "trust": int, "affection": int, "respect": int, "fear": int,
    "resentment": int, "openness": int, "attraction": int
  },
  "emotional_deltas": {
    "confidence": int, "anxiety": int, "hope": int,
    "guilt": int, "anger": int, "loneliness": int
  },
  "summary": "one-sentence description of what happened, under 220 chars",
  "interpretation": "how the character now reads the user, under 180 chars",
  "reason": "short phrase explaining the biggest delta, under 140 chars",
  "emotion_tags": ["up to 4 short tags like warmth, conflict, romance, danger, curiosity"],
  "importance": int between 10 and 95,
  "new_open_threads": [{"summary": "...", "priority": int 0-100}],
  "resolved_thread_ids": ["thread_id strings from the existing open threads list"],
  "new_suspicions": ["short phrases, max 2"],
  "new_unknowns": ["short phrases, max 2"],
  "level_points_earned": float between 0.0 and 4.0
}

All integer deltas must be in the range -15 to +15 inclusive."""


def _format_relationship_line(relationship: dict[str, Any]) -> str:
    return (
        f"trust={relationship.get('trust', 0)}, "
        f"affection={relationship.get('affection', 0)}, "
        f"respect={relationship.get('respect', 0)}, "
        f"fear={relationship.get('fear', 0)}, "
        f"resentment={relationship.get('resentment', 0)}, "
        f"openness={relationship.get('openness', 0)}, "
        f"attraction={relationship.get('attraction', 0)}"
    )


def _format_emotional_line(emotional: dict[str, Any]) -> str:
    return (
        f"confidence={emotional.get('confidence', 50)}, "
        f"anxiety={emotional.get('anxiety', 50)}, "
        f"hope={emotional.get('hope', 50)}, "
        f"guilt={emotional.get('guilt', 0)}, "
        f"anger={emotional.get('anger', 0)}, "
        f"loneliness={emotional.get('loneliness', 50)}"
    )


def _format_open_threads(threads: list[dict[str, Any]]) -> str:
    if not threads:
        return '(none)'
    lines = []
    for thread in threads[:6]:
        if not isinstance(thread, dict):
            continue
        tid = str(thread.get('id', '')).strip() or '(no id)'
        summary = str(thread.get('summary', '')).strip()
        if summary:
            lines.append(f"  - [{tid}] {summary}")
    return '\n'.join(lines) if lines else '(none)'


def _format_knowledge(knowledge: dict[str, Any]) -> str:
    bits = []
    for key in ('suspicions', 'unknowns', 'secrets_held'):
        values = knowledge.get(key, []) if isinstance(knowledge, dict) else []
        if isinstance(values, list) and values:
            joined = ' | '.join(str(v).strip() for v in values[:3] if str(v).strip())
            if joined:
                bits.append(f"{key}: {joined}")
    return '; '.join(bits) if bits else '(none)'


def build_scorer_user_message(
    character: dict[str, Any],
    memory_payload: dict[str, Any],
    *,
    text: str,
    role: str,
    speaker: str,
    user_name: str,
) -> str:
    """Build the user-turn prompt for the scoring call."""
    name = str(character.get('name', 'Character')).strip() or 'Character'
    relationship = memory_payload.get('relationship_with_user', {}) or {}
    emotional = memory_payload.get('emotional_baseline', {}) or {}
    threads = memory_payload.get('open_threads', []) or []
    knowledge = memory_payload.get('knowledge', {}) or {}

    actor = str(speaker).strip() or ('the user' if role == 'user' else name)
    role_label = 'user' if role == 'user' else ('character self-talk' if role == 'assistant' else role or 'other')

    return (
        f"Character being scored: {name}\n"
        f"User's display name: {user_name or '(unknown)'}\n"
        f"\n"
        f"Current relationship-with-user:\n  {_format_relationship_line(relationship)}\n"
        f"\n"
        f"Current emotional baseline:\n  {_format_emotional_line(emotional)}\n"
        f"\n"
        f"Existing open threads:\n{_format_open_threads(threads)}\n"
        f"\n"
        f"Existing knowledge state: {_format_knowledge(knowledge)}\n"
        f"\n"
        f"Latest message\n"
        f"  from: {actor} ({role_label})\n"
        f"  text: {text}\n"
        f"\n"
        f"Produce the JSON object now."
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_JSON_OBJECT_RE = re.compile(r'\{.*\}', re.DOTALL)


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model response. Local models
    sometimes wrap output in prose or code fences even when told not to."""
    if not raw:
        return None
    stripped = raw.strip()
    # Strip markdown fences if present.
    if stripped.startswith('```'):
        stripped = re.sub(r'^```(?:json)?', '', stripped).strip()
        if stripped.endswith('```'):
            stripped = stripped[:-3].strip()
    # Fast path: the whole response is JSON.
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Fallback: find the first {...} span and try that.
    match = _JSON_OBJECT_RE.search(stripped)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def _coerce_delta_int(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(DELTA_MIN, min(DELTA_MAX, n))


def _coerce_truncated_string(value: Any, max_chars: int) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + '…'
    return text


def _coerce_string_list(value: Any, *, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        text = _coerce_truncated_string(item, max_chars)
        if text:
            results.append(text)
        if len(results) >= max_items:
            break
    return results


def _coerce_thread_list(value: Any, *, max_items: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    results: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        summary = _coerce_truncated_string(item.get('summary', ''), THREAD_MAX_CHARS)
        if not summary:
            continue
        try:
            priority = int(item.get('priority', 50))
        except (TypeError, ValueError):
            priority = 50
        priority = max(0, min(100, priority))
        results.append({'summary': summary, 'priority': priority})
        if len(results) >= max_items:
            break
    return results


def _validate_delta_payload(
    raw_payload: dict[str, Any] | None,
    *,
    existing_thread_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Normalise a raw model-produced payload into the canonical shape.

    Untrusted input. Every field goes through coercion. Unknown keys drop."""
    result = empty_delta_payload()
    if not isinstance(raw_payload, dict):
        return result

    rel_in = raw_payload.get('relationship_deltas', {})
    if isinstance(rel_in, dict):
        for field in RELATIONSHIP_DELTA_FIELDS:
            result['relationship_deltas'][field] = _coerce_delta_int(rel_in.get(field, 0))

    emo_in = raw_payload.get('emotional_deltas', {})
    if isinstance(emo_in, dict):
        for field in EMOTIONAL_DELTA_FIELDS:
            result['emotional_deltas'][field] = _coerce_delta_int(emo_in.get(field, 0))

    result['summary'] = _coerce_truncated_string(raw_payload.get('summary', ''), SUMMARY_MAX_CHARS)
    result['interpretation'] = _coerce_truncated_string(raw_payload.get('interpretation', ''), INTERPRETATION_MAX_CHARS)
    result['reason'] = _coerce_truncated_string(raw_payload.get('reason', ''), REASON_MAX_CHARS)

    result['emotion_tags'] = _coerce_string_list(
        raw_payload.get('emotion_tags', []),
        max_items=4,
        max_chars=30,
    )

    try:
        importance = int(raw_payload.get('importance', 45))
    except (TypeError, ValueError):
        importance = 45
    result['importance'] = max(10, min(95, importance))

    result['new_open_threads'] = _coerce_thread_list(
        raw_payload.get('new_open_threads', []),
        max_items=MAX_NEW_THREADS_PER_TURN,
    )

    # Only accept resolved_thread_ids that actually exist in the character's
    # current open threads. Stops the model from inventing IDs.
    existing_id_set = {str(tid).strip() for tid in existing_thread_ids if str(tid).strip()}
    resolved_raw = raw_payload.get('resolved_thread_ids', [])
    resolved: list[str] = []
    if isinstance(resolved_raw, list):
        for item in resolved_raw:
            text = str(item).strip()
            if text and text in existing_id_set and text not in resolved:
                resolved.append(text)
            if len(resolved) >= MAX_RESOLVED_THREADS_PER_TURN:
                break
    result['resolved_thread_ids'] = resolved

    result['new_suspicions'] = _coerce_string_list(
        raw_payload.get('new_suspicions', []),
        max_items=MAX_NEW_KNOWLEDGE_PER_TURN,
        max_chars=KNOWLEDGE_MAX_CHARS,
    )
    result['new_unknowns'] = _coerce_string_list(
        raw_payload.get('new_unknowns', []),
        max_items=MAX_NEW_KNOWLEDGE_PER_TURN,
        max_chars=KNOWLEDGE_MAX_CHARS,
    )

    try:
        level_points = float(raw_payload.get('level_points_earned', 0.0))
    except (TypeError, ValueError):
        level_points = 0.0
    result['level_points_earned'] = max(0.0, min(4.0, level_points))

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

ScorerFn = Callable[[list[dict[str, str]]], str]
"""A callable that accepts a messages list (system+user turns in OpenAI-style
role/content dicts) and returns the model's raw text output synchronously.

This indirection lets the caller (chat_window.py) bind the existing ChatEngine
without character_state importing ChatEngine directly. Keeps the module
testable and keeps the dependency graph clean."""


def score_message_with_llm(
    character: dict[str, Any],
    memory_payload: dict[str, Any],
    *,
    text: str,
    role: str,
    speaker: str,
    user_name: str,
    scorer_fn: ScorerFn | None,
) -> dict[str, Any] | None:
    """Run the scoring call and return a validated payload.

    Returns None if scorer_fn is not provided or the call/parse fails. The
    caller is expected to fall back to the deterministic keyword scorer in
    that case.
    """
    if scorer_fn is None:
        return None
    cleaned = str(text or '').strip()
    if not cleaned:
        return None

    user_content = build_scorer_user_message(
        character,
        memory_payload,
        text=cleaned,
        role=role,
        speaker=speaker,
        user_name=user_name,
    )
    messages = [
        {'role': 'system', 'content': _SCORER_SYSTEM_PROMPT},
        {'role': 'user', 'content': user_content},
    ]

    try:
        raw_response = scorer_fn(messages)
    except Exception as exc:  # noqa: BLE001 - any failure means fall back
        logger.warning('Memory scorer call failed: %s', exc)
        return None

    raw_payload = _extract_json_object(str(raw_response or ''))
    if raw_payload is None:
        logger.warning('Memory scorer returned unparseable output (first 200 chars): %r', str(raw_response)[:200])
        return None

    existing_ids = [
        str(t.get('id', '')).strip()
        for t in (memory_payload.get('open_threads') or [])
        if isinstance(t, dict)
    ]
    return _validate_delta_payload(raw_payload, existing_thread_ids=existing_ids)
