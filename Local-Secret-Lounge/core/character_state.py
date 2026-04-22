from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
import re
from typing import Any, Callable

from core.memory_scorer import (
    empty_delta_payload,
    score_message_with_llm,
)

logger = logging.getLogger(__name__)

STATIC_TOP_LEVEL_KEYS = (
    'id',
    'slug',
    'name',
    'role',
    'story_role',
    'title',
    'description',
    'system_prompt',
    'starting_scenario',
    'greeting',
    'identity',
    'voice',
    'knowledge',
    'world_lore_notes',
    'tags',
    'folder',
    'is_favorite',
    'source',
    'avatar_path',
    'avatar',
    'image',
    'image_path',
)

MEMORY_TOP_LEVEL_KEYS = (
    'relationship_with_user',
    'relationships_with_characters',
    'emotional_baseline',
    'memories',
    'open_threads',
    'scene_flags',
    'knowledge',
)

# Maximum number of tracked character-to-character relationships per memory file.
MAX_CHARACTER_RELATIONSHIPS = 10

POSITIVE_PATTERNS = (
    'thank', 'thanks', 'appreciate', 'glad', 'good', 'great', 'kind', 'care', 'help', 'safe',
    'love', 'like you', 'trust', 'proud', 'sorry', 'support', 'gentle', 'reassure', 'comfort',
)
NEGATIVE_PATTERNS = (
    'hate', 'stupid', 'idiot', 'shut up', 'leave', 'annoy', 'angry', 'mad', 'furious', 'threat',
    'kill', 'hurt', 'liar', 'useless', 'disgust', 'resent', 'jealous', 'ignore', 'ignored',
)
FLIRT_PATTERNS = (
    'beautiful', 'cute', 'pretty', 'kiss', 'date', 'flirt', 'sexy', 'attractive', 'love you',
)
FEAR_PATTERNS = (
    'scared', 'afraid', 'danger', 'panic', 'terrified', 'threat', 'hurt', 'injured', 'blood',
)


def _clean_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clamp(value: Any, low: int = 0, high: int = 100, default: int = 0) -> int:
    return max(low, min(high, _clean_int(value, default)))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _normalize_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            results.append(text)
    return results


def _character_ref(character: dict[str, Any]) -> dict[str, str]:
    return {
        'id': str(character.get('id', '')).strip(),
        'slug': str(character.get('slug', '')).strip(),
        'name': str(character.get('name', '')).strip(),
    }


def _empty_relationship_block() -> dict[str, Any]:
    """Return a blank relationship stat block (same fields as relationship_with_user)."""
    return {
        'status_label': 'Neutral',
        'trust': 0,
        'affection': 0,
        'respect': 0,
        'fear': 0,
        'resentment': 0,
        'dependency': 0,
        'openness': 0,
        'attraction': 0,
        'last_change_reason': '',
        'interpretation': '',
    }


def _extract_relationship_block(source: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a relationship stat block from raw dict data."""
    return {
        'status_label': str(source.get('status_label', defaults['status_label'])).strip() or defaults['status_label'],
        'trust': _clamp(source.get('trust', defaults['trust'])),
        'affection': _clamp(source.get('affection', defaults['affection'])),
        'respect': _clamp(source.get('respect', defaults['respect'])),
        'fear': _clamp(source.get('fear', defaults['fear'])),
        'resentment': _clamp(source.get('resentment', defaults['resentment'])),
        'dependency': _clamp(source.get('dependency', defaults['dependency'])),
        'openness': _clamp(source.get('openness', defaults['openness'])),
        'attraction': _clamp(source.get('attraction', defaults['attraction'])),
        'last_change_reason': str(source.get('last_change_reason', defaults['last_change_reason'])).strip(),
        'interpretation': str(source.get('interpretation', defaults['interpretation'])).strip(),
    }


def _extract_character_relationship_entry(raw: Any) -> dict[str, Any] | None:
    """Parse and validate one entry from relationships_with_characters.

    Returns None if the entry is structurally invalid (no usable character_ref).
    """
    if not isinstance(raw, dict):
        return None
    char_ref_raw = raw.get('character_ref')
    if not isinstance(char_ref_raw, dict):
        return None
    char_ref = {
        'id': str(char_ref_raw.get('id', '')).strip(),
        'slug': str(char_ref_raw.get('slug', '')).strip(),
        'name': str(char_ref_raw.get('name', '')).strip(),
    }
    if not any(char_ref.values()):
        return None
    defaults = _empty_relationship_block()
    rel = _extract_relationship_block(raw, defaults)
    return {'character_ref': char_ref, **rel}


def default_memory_payload_for_character(character: dict[str, Any] | None = None) -> dict[str, Any]:
    source = character if isinstance(character, dict) else {}
    return {
        'character_ref': _character_ref(source),
        'knowledge': {
            'suspicions': [],
            'unknowns': [],
            'secrets_held': [],
        },
        'relationship_with_user': _empty_relationship_block(),
        'relationships_with_characters': [],
        'emotional_baseline': {
            'confidence': 50,
            'anxiety': 50,
            'hope': 50,
            'guilt': 0,
            'anger': 0,
            'loneliness': 50,
        },
        'memories': {
            'stable': [],
            'episodic': [],
        },
        'open_threads': [],
        'scene_flags': {
            'available_for_interaction': True,
            'injured': False,
            'hostile_mode': False,
            'romance_locked': False,
        },
    }


def extract_character_static(character: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(character) if isinstance(character, dict) else {}
    static_payload: dict[str, Any] = {}
    for key in STATIC_TOP_LEVEL_KEYS:
        if key in source:
            static_payload[key] = deepcopy(source[key])

    knowledge = static_payload.get('knowledge') if isinstance(static_payload.get('knowledge'), dict) else {}
    static_payload['knowledge'] = {
        'known_facts': _normalize_list_of_strings(knowledge.get('known_facts', [])),
    }
    return static_payload


def extract_character_memory(character: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(character) if isinstance(character, dict) else {}
    defaults = default_memory_payload_for_character(source)

    memory_payload = defaults
    memory_payload['character_ref'] = _character_ref(source)

    source_knowledge = source.get('knowledge') if isinstance(source.get('knowledge'), dict) else {}
    memory_payload['knowledge'] = {
        'suspicions': _normalize_list_of_strings(source_knowledge.get('suspicions', defaults['knowledge']['suspicions'])),
        'unknowns': _normalize_list_of_strings(source_knowledge.get('unknowns', defaults['knowledge']['unknowns'])),
        'secrets_held': _normalize_list_of_strings(source_knowledge.get('secrets_held', defaults['knowledge']['secrets_held'])),
    }

    relationship = source.get('relationship_with_user') if isinstance(source.get('relationship_with_user'), dict) else {}
    memory_payload['relationship_with_user'] = _extract_relationship_block(relationship, defaults['relationship_with_user'])

    # Character-to-character relationships (up to MAX_CHARACTER_RELATIONSHIPS = 10).
    raw_char_rels = source.get('relationships_with_characters')
    validated_char_rels: list[dict[str, Any]] = []
    if isinstance(raw_char_rels, list):
        seen_ids: set[str] = set()
        for raw_entry in raw_char_rels:
            entry = _extract_character_relationship_entry(raw_entry)
            if entry is None:
                continue
            dedup_key = (
                entry['character_ref'].get('slug')
                or entry['character_ref'].get('id')
                or entry['character_ref'].get('name', '').lower()
            )
            if dedup_key and dedup_key in seen_ids:
                continue
            if dedup_key:
                seen_ids.add(dedup_key)
            validated_char_rels.append(entry)
            if len(validated_char_rels) >= MAX_CHARACTER_RELATIONSHIPS:
                break
    memory_payload['relationships_with_characters'] = validated_char_rels

    emotional = source.get('emotional_baseline') if isinstance(source.get('emotional_baseline'), dict) else {}
    memory_payload['emotional_baseline'] = {
        'confidence': _clamp(emotional.get('confidence', defaults['emotional_baseline']['confidence'])),
        'anxiety': _clamp(emotional.get('anxiety', defaults['emotional_baseline']['anxiety'])),
        'hope': _clamp(emotional.get('hope', defaults['emotional_baseline']['hope'])),
        'guilt': _clamp(emotional.get('guilt', defaults['emotional_baseline']['guilt'])),
        'anger': _clamp(emotional.get('anger', defaults['emotional_baseline']['anger'])),
        'loneliness': _clamp(emotional.get('loneliness', defaults['emotional_baseline']['loneliness'])),
    }

    memories = source.get('memories') if isinstance(source.get('memories'), dict) else {}
    stable = memories.get('stable') if isinstance(memories.get('stable'), list) else []
    episodic = memories.get('episodic') if isinstance(memories.get('episodic'), list) else []
    memory_payload['memories'] = {
        'stable': [deepcopy(item) for item in stable if isinstance(item, dict)],
        'episodic': [deepcopy(item) for item in episodic if isinstance(item, dict)],
    }

    open_threads = source.get('open_threads') if isinstance(source.get('open_threads'), list) else []
    memory_payload['open_threads'] = [deepcopy(item) for item in open_threads if isinstance(item, dict)]

    scene_flags = source.get('scene_flags') if isinstance(source.get('scene_flags'), dict) else {}
    memory_payload['scene_flags'] = {
        'available_for_interaction': bool(scene_flags.get('available_for_interaction', defaults['scene_flags']['available_for_interaction'])),
        'injured': bool(scene_flags.get('injured', defaults['scene_flags']['injured'])),
        'hostile_mode': bool(scene_flags.get('hostile_mode', defaults['scene_flags']['hostile_mode'])),
        'romance_locked': bool(scene_flags.get('romance_locked', defaults['scene_flags']['romance_locked'])),
    }

    return memory_payload


def merge_character_static_and_memory(static_data: dict[str, Any], memory_data: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(static_data) if isinstance(static_data, dict) else {}
    memory_payload = extract_character_memory(memory_data or merged)

    static_knowledge = merged.get('knowledge') if isinstance(merged.get('knowledge'), dict) else {}
    memory_knowledge = memory_payload.get('knowledge') if isinstance(memory_payload.get('knowledge'), dict) else {}
    merged['knowledge'] = {
        'known_facts': _normalize_list_of_strings(static_knowledge.get('known_facts', [])),
        'suspicions': _normalize_list_of_strings(memory_knowledge.get('suspicions', [])),
        'unknowns': _normalize_list_of_strings(memory_knowledge.get('unknowns', [])),
        'secrets_held': _normalize_list_of_strings(memory_knowledge.get('secrets_held', [])),
    }

    for key in ('relationship_with_user', 'relationships_with_characters', 'emotional_baseline', 'memories', 'open_threads', 'scene_flags'):
        merged[key] = deepcopy(memory_payload[key])

    merged['character_ref'] = deepcopy(memory_payload.get('character_ref', _character_ref(merged)))
    return merged


def build_memory_prompt_lines(character: dict[str, Any], *, max_stable: int = 2, max_episodic: int = 3, max_threads: int = 2) -> list[str]:
    name = str(character.get('name', 'Character')).strip() or 'Character'
    memory_payload = extract_character_memory(character)

    relationship = memory_payload['relationship_with_user']
    emotional = memory_payload['emotional_baseline']
    knowledge = memory_payload['knowledge']
    memories = memory_payload['memories']
    scene_flags = memory_payload['scene_flags']
    open_threads = memory_payload['open_threads']
    char_relationships = memory_payload['relationships_with_characters']

    lines: list[str] = []

    # User relationship.
    lines.append(
        f"- {name}: user relationship is {relationship['status_label']} | trust {relationship['trust']}/100 | affection {relationship['affection']}/100 | respect {relationship['respect']}/100 | fear {relationship['fear']}/100 | resentment {relationship['resentment']}/100 | openness {relationship['openness']}/100 | attraction {relationship['attraction']}/100."
    )
    lines.append(
        f"  Current emotional baseline: confidence {emotional['confidence']}/100, anxiety {emotional['anxiety']}/100, hope {emotional['hope']}/100, guilt {emotional['guilt']}/100, anger {emotional['anger']}/100, loneliness {emotional['loneliness']}/100."
    )

    # Character-to-character relationships (up to 10).
    for rel_entry in char_relationships[:MAX_CHARACTER_RELATIONSHIPS]:
        char_name = rel_entry.get('character_ref', {}).get('name', 'Unknown Character')
        lines.append(
            f"  {name} \u2192 {char_name}: {rel_entry['status_label']} | trust {rel_entry['trust']}/100 | affection {rel_entry['affection']}/100 | respect {rel_entry['respect']}/100 | fear {rel_entry['fear']}/100 | openness {rel_entry['openness']}/100 | attraction {rel_entry['attraction']}/100."
        )
        if rel_entry.get('interpretation'):
            lines.append(f"    Interpretation: {rel_entry['interpretation']}")

    stable_items = [str(item.get('summary', '')).strip() for item in memories.get('stable', []) if isinstance(item, dict)]
    if stable_items:
        lines.append(f"  Stable memory anchors: {' | '.join(item for item in stable_items[:max_stable] if item)}")

    episodic_items = [str(item.get('summary', '')).strip() for item in memories.get('episodic', []) if isinstance(item, dict)]
    if episodic_items:
        lines.append(f"  Recent episodic memories: {' | '.join(item for item in episodic_items[-max_episodic:] if item)}")

    thread_summaries = [str(item.get('summary', '')).strip() for item in open_threads if isinstance(item, dict)]
    if thread_summaries:
        lines.append(f"  Open threads: {' | '.join(item for item in thread_summaries[:max_threads] if item)}")

    suspicion_bits: list[str] = []
    for key in ('suspicions', 'unknowns', 'secrets_held'):
        values = _normalize_list_of_strings(knowledge.get(key, []))
        if values:
            suspicion_bits.append(f"{key.replace('_', ' ')}: {' | '.join(values[:2])}")
    if suspicion_bits:
        lines.append(f"  Mutable knowledge state: {' ; '.join(suspicion_bits)}")

    non_default_flags = [
        key.replace('_', ' ')
        for key, value in scene_flags.items()
        if (key == 'available_for_interaction' and not bool(value)) or (key != 'available_for_interaction' and bool(value))
    ]
    if non_default_flags:
        lines.append(f"  Active flags: {', '.join(non_default_flags)}")

    return lines


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = f" {str(text or '').casefold()} "
    return any(f" {pattern.casefold()} " in lowered or pattern.casefold() in lowered for pattern in patterns)


def _infer_emotion_tags(text: str) -> list[str]:
    tags: list[str] = []
    if _contains_any(text, POSITIVE_PATTERNS):
        tags.extend(['warmth', 'support'])
    if _contains_any(text, NEGATIVE_PATTERNS):
        tags.extend(['conflict', 'hurt'])
    if _contains_any(text, FLIRT_PATTERNS):
        tags.append('romance')
    if _contains_any(text, FEAR_PATTERNS):
        tags.append('danger')
    if not tags:
        tags.append('interaction')
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if tag not in seen:
            result.append(tag)
            seen.add(tag)
    return result[:4]


def _summarize_for_memory(text: str, *, speaker: str = '', role: str = '') -> str:
    cleaned = re.sub(r'\s+', ' ', str(text or '')).strip()
    cleaned = cleaned.strip('"\'')
    if not cleaned:
        return ''
    if len(cleaned) > 220:
        cleaned = cleaned[:219].rstrip() + '…'
    actor = str(speaker or '').strip() or ('The user' if role == 'user' else 'Someone')
    if role == 'assistant':
        return f'{actor} said or did: {cleaned}'
    if role == 'user':
        return f'The user said or did: {cleaned}'
    return cleaned


def _next_memory_id(existing: list[dict[str, Any]], prefix: str) -> str:
    used = {str(item.get('id', '')).strip() for item in existing if isinstance(item, dict)}
    counter = 1
    while True:
        candidate = f'{prefix}_{counter:03d}'
        if candidate not in used:
            return candidate
        counter += 1


def _relationship_status_label(relationship: dict[str, Any]) -> str:
    trust = _clamp(relationship.get('trust', 0))
    affection = _clamp(relationship.get('affection', 0))
    fear = _clamp(relationship.get('fear', 0))
    resentment = _clamp(relationship.get('resentment', 0))
    attraction = _clamp(relationship.get('attraction', 0))

    if fear >= 65 or resentment >= 65:
        return 'Guarded'
    if attraction >= 60 and affection >= 55:
        return 'Romantically interested'
    if trust >= 70 and affection >= 60:
        return 'Close'
    if trust >= 55 or affection >= 45:
        return 'Warm'
    if trust >= 35 or affection >= 25:
        return 'Curious'
    return 'Neutral'


def get_character_relationship(
    character: dict[str, Any],
    *,
    target_slug: str = '',
    target_name: str = '',
) -> dict[str, Any] | None:
    """Return the relationship entry for a specific character, or None if not found.

    Matches by slug first, then by name (case-insensitive).
    """
    rels = character.get('relationships_with_characters')
    if not isinstance(rels, list):
        return None
    slug_key = str(target_slug or '').strip().lower()
    name_key = str(target_name or '').strip().lower()
    for entry in rels:
        if not isinstance(entry, dict):
            continue
        ref = entry.get('character_ref', {})
        if slug_key and str(ref.get('slug', '')).strip().lower() == slug_key:
            return entry
        if name_key and str(ref.get('name', '')).strip().lower() == name_key:
            return entry
    return None


def upsert_character_relationship(
    character: dict[str, Any],
    *,
    target_ref: dict[str, str],
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Update (or insert) a relationship entry within relationships_with_characters.

    target_ref must contain at least one of id, slug, or name.
    updates is a partial dict of relationship fields to merge in.
    Returns the mutated character dict (modifies in place and also returns it).
    Respects the MAX_CHARACTER_RELATIONSHIPS cap — if the cap is reached and this
    is a new entry, the oldest entry (index 0) is dropped to make room.
    """
    rels: list[dict[str, Any]] = character.setdefault('relationships_with_characters', [])
    slug_key = str(target_ref.get('slug', '')).strip().lower()
    name_key = str(target_ref.get('name', '')).strip().lower()
    id_key = str(target_ref.get('id', '')).strip().lower()

    existing_index: int | None = None
    for idx, entry in enumerate(rels):
        if not isinstance(entry, dict):
            continue
        ref = entry.get('character_ref', {})
        if slug_key and str(ref.get('slug', '')).strip().lower() == slug_key:
            existing_index = idx
            break
        if id_key and str(ref.get('id', '')).strip().lower() == id_key:
            existing_index = idx
            break
        if name_key and str(ref.get('name', '')).strip().lower() == name_key:
            existing_index = idx
            break

    if existing_index is not None:
        entry = rels[existing_index]
    else:
        if len(rels) >= MAX_CHARACTER_RELATIONSHIPS:
            rels.pop(0)
        entry = {'character_ref': target_ref, **_empty_relationship_block()}
        rels.append(entry)

    entry['character_ref'] = {
        'id': str(target_ref.get('id', entry['character_ref'].get('id', ''))).strip(),
        'slug': str(target_ref.get('slug', entry['character_ref'].get('slug', ''))).strip(),
        'name': str(target_ref.get('name', entry['character_ref'].get('name', ''))).strip(),
    }
    for field, value in updates.items():
        if field == 'character_ref':
            continue
        if field in ('trust', 'affection', 'respect', 'fear', 'resentment', 'dependency', 'openness', 'attraction'):
            entry[field] = _clamp(value)
        else:
            entry[field] = value

    entry['status_label'] = _relationship_status_label(entry)
    return character


def _compute_deltas_via_keywords(
    cleaned_text: str,
    *,
    role: str,
    linked_to_user: bool,
) -> dict[str, Any]:
    """Deterministic keyword-based scoring. Used as fallback when the LLM
    scorer is unavailable or fails. Produces a payload in the same shape
    memory_scorer.empty_delta_payload() returns."""
    payload = empty_delta_payload()
    rel = payload['relationship_deltas']
    emo = payload['emotional_deltas']

    if _contains_any(cleaned_text, POSITIVE_PATTERNS):
        rel['trust'] += 3
        rel['affection'] += 2
        rel['respect'] += 1
        rel['openness'] += 1
        emo['hope'] += 2
        emo['anxiety'] -= 1
    if _contains_any(cleaned_text, NEGATIVE_PATTERNS):
        rel['trust'] -= 10
        rel['affection'] -= 6
        rel['respect'] -= 4
        rel['fear'] += 8
        rel['resentment'] += 10
        rel['openness'] -= 6
        emo['anxiety'] += 6
        emo['anger'] += 8
    if _contains_any(cleaned_text, FLIRT_PATTERNS):
        rel['attraction'] += 2
        rel['affection'] += 1
        rel['openness'] += 1
    if _contains_any(cleaned_text, FEAR_PATTERNS):
        rel['fear'] += 6
        emo['anxiety'] += 10
        emo['confidence'] -= 4
    if role == 'assistant':
        rel['openness'] += 1
    if linked_to_user and not any(rel.values()):
        rel['trust'] += 1
        rel['openness'] += 1

    # Interpretation line mirrors the original hardcoded strings.
    if linked_to_user:
        if _contains_any(cleaned_text, POSITIVE_PATTERNS):
            payload['interpretation'] = 'The user seems supportive and easier to trust right now.'
        elif _contains_any(cleaned_text, NEGATIVE_PATTERNS):
            payload['interpretation'] = 'The user feels unsafe or difficult to trust right now.'
        elif _contains_any(cleaned_text, FLIRT_PATTERNS):
            payload['interpretation'] = 'The user may be showing romantic or flirtatious interest.'
        else:
            payload['interpretation'] = 'The user is actively engaged in the current scene.'

    # Importance matches the original three-bucket rule.
    importance = 45
    if (
        _contains_any(cleaned_text, POSITIVE_PATTERNS)
        or _contains_any(cleaned_text, NEGATIVE_PATTERNS)
        or _contains_any(cleaned_text, FLIRT_PATTERNS)
    ):
        importance = 62
    if _contains_any(cleaned_text, FEAR_PATTERNS):
        importance = 70
    payload['importance'] = importance
    payload['emotion_tags'] = _infer_emotion_tags(cleaned_text)

    return payload


def apply_message_to_character_memory(
    character: dict[str, Any],
    *,
    text: str,
    role: str,
    speaker: str = '',
    user_name: str = '',
    scorer_fn: Callable[[list[dict[str, str]]], str] | None = None,
) -> dict[str, Any]:
    """Apply a message to a character's memory and return the updated dict.

    If scorer_fn is provided, runs the LLM-based scorer and falls back to
    deterministic keyword scoring on failure. If scorer_fn is None, uses
    keyword scoring directly — preserves behaviour for any caller that
    hasn't been updated to pass a scorer.
    """
    updated = merge_character_static_and_memory(character, character)
    cleaned_text = str(text or '').strip()
    if not cleaned_text:
        return updated

    memory_payload = extract_character_memory(updated)
    relationship = memory_payload['relationship_with_user']
    emotional = memory_payload['emotional_baseline']
    episodic = memory_payload['memories']['episodic']
    open_threads = memory_payload['open_threads']
    knowledge = memory_payload.get('knowledge', {}) or {}

    linked_to_user = role == 'user' or str(speaker).strip().casefold() == str(user_name or '').strip().casefold()

    # Try the LLM scorer first. None means either disabled or failed --
    # either way we fall back to keywords so memory never stops updating.
    delta_payload: dict[str, Any] | None = None
    if scorer_fn is not None:
        try:
            delta_payload = score_message_with_llm(
                updated,
                memory_payload,
                text=cleaned_text,
                role=role,
                speaker=speaker,
                user_name=user_name,
                scorer_fn=scorer_fn,
            )
        except Exception as exc:  # noqa: BLE001 - any failure means fall back
            logger.warning('LLM memory scoring raised; falling back to keywords: %s', exc)
            delta_payload = None

    if delta_payload is None:
        delta_payload = _compute_deltas_via_keywords(
            cleaned_text,
            role=role,
            linked_to_user=linked_to_user,
        )

    rel_deltas = delta_payload['relationship_deltas']
    emo_deltas = delta_payload['emotional_deltas']

    # Apply relationship deltas. _clamp pins to [0, 100].
    for field in ('trust', 'affection', 'respect', 'fear', 'resentment', 'openness', 'attraction'):
        relationship[field] = _clamp(relationship.get(field, 0) + rel_deltas.get(field, 0))
    relationship['status_label'] = _relationship_status_label(relationship)

    # Apply emotional deltas. Defaults match the original code.
    emotional_defaults = {'confidence': 50, 'anxiety': 50, 'hope': 50, 'guilt': 0, 'anger': 0, 'loneliness': 50}
    for field, default in emotional_defaults.items():
        emotional[field] = _clamp(emotional.get(field, default) + emo_deltas.get(field, 0))

    # Reason + interpretation on the relationship.
    if linked_to_user:
        reason = delta_payload.get('reason', '') or _summarize_for_memory(cleaned_text, speaker=speaker, role=role)
        relationship['last_change_reason'] = reason
        interpretation = delta_payload.get('interpretation', '')
        if interpretation:
            relationship['interpretation'] = interpretation

    # Episodic memory entry. Prefer the scorer's summary; fall back to the
    # truncated raw text if the scorer didn't supply one.
    memory_summary = delta_payload.get('summary', '') or _summarize_for_memory(cleaned_text, speaker=speaker, role=role)
    if memory_summary:
        last_summary = str(episodic[-1].get('summary', '')).strip() if episodic else ''
        if memory_summary != last_summary:
            emotion_tags = delta_payload.get('emotion_tags') or _infer_emotion_tags(cleaned_text)
            episodic.append({
                'id': _next_memory_id(episodic, 'epi'),
                'summary': memory_summary,
                'type': 'interaction' if linked_to_user else 'event',
                'linked_to_user': linked_to_user,
                'emotion_tags': emotion_tags,
                'emotional_impact': {
                    'trust': rel_deltas.get('trust', 0),
                    'affection': rel_deltas.get('affection', 0),
                    'fear': rel_deltas.get('fear', 0),
                    'resentment': rel_deltas.get('resentment', 0),
                    'openness': rel_deltas.get('openness', 0),
                },
                'importance': int(delta_payload.get('importance', 45)),
                'recency': _utc_now_iso(),
                'triggers': list(emotion_tags),
                'decays': True,
                'notes': '',
            })
            if len(episodic) > 30:
                episodic[:] = episodic[-30:]

    # New open threads from the scorer. Dedupe against existing summaries.
    existing_thread_summaries = {
        str(t.get('summary', '')).strip().casefold()
        for t in open_threads if isinstance(t, dict)
    }
    for new_thread in delta_payload.get('new_open_threads', []):
        summary_text = str(new_thread.get('summary', '')).strip()
        if not summary_text:
            continue
        if summary_text.casefold() in existing_thread_summaries:
            continue
        open_threads.append({
            'id': _next_memory_id(open_threads, 'thread'),
            'summary': summary_text,
            'priority': int(new_thread.get('priority', 50)),
        })
        existing_thread_summaries.add(summary_text.casefold())

    # Resolve threads the scorer marked as done.
    resolved_ids = set(delta_payload.get('resolved_thread_ids', []))
    if resolved_ids:
        open_threads[:] = [
            t for t in open_threads
            if not (isinstance(t, dict) and str(t.get('id', '')).strip() in resolved_ids)
        ]

    # New suspicions / unknowns. Dedupe case-insensitively against what's
    # already there.
    for knowledge_key, scorer_key in (('suspicions', 'new_suspicions'), ('unknowns', 'new_unknowns')):
        existing = knowledge.get(knowledge_key, []) or []
        existing_lower = {str(x).strip().casefold() for x in existing}
        for item in delta_payload.get(scorer_key, []):
            item_text = str(item).strip()
            if not item_text or item_text.casefold() in existing_lower:
                continue
            existing.append(item_text)
            existing_lower.add(item_text.casefold())
        knowledge[knowledge_key] = existing

    updated['relationship_with_user'] = relationship
    updated['relationships_with_characters'] = memory_payload['relationships_with_characters']
    updated['emotional_baseline'] = emotional
    updated['memories'] = memory_payload['memories']
    updated['open_threads'] = open_threads
    updated['scene_flags'] = memory_payload['scene_flags']
    # Preserve secrets_held and known_facts from the merged view while taking
    # the updated suspicions/unknowns from the scorer.
    merged_knowledge = merge_character_static_and_memory(updated, memory_payload).get('knowledge', {}) or {}
    merged_knowledge['suspicions'] = knowledge.get('suspicions', merged_knowledge.get('suspicions', []))
    merged_knowledge['unknowns'] = knowledge.get('unknowns', merged_knowledge.get('unknowns', []))
    updated['knowledge'] = merged_knowledge
    updated['character_ref'] = memory_payload['character_ref']
    return updated
