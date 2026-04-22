from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any


CONFLICT_KEYWORDS = {
    'angry', 'argument', 'argue', 'fight', 'furious', 'threat', 'tense', 'panic', 'afraid', 'fear', 'cry', 'shout', 'yell'
}
RESOLUTION_KEYWORDS = {
    'apologize', 'apologise', 'agree', 'calm', 'breathe', 'relax', 'smile', 'laugh', 'thank', 'understand', 'resolved'
}
CLOSING_KEYWORDS = {'leave', 'leaves', 'left', 'goodbye', 'bye', 'later', 'head home', 'walk away', 'end the night'}
LOCATION_PATTERNS = [
    re.compile(r'\b(?:at|in|inside|outside|near|by|into|onto)\s+([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,4})\b'),
    re.compile(r'\b(?:to|toward|towards)\s+the\s+([a-z][a-z0-9\-]*(?:\s+[a-z][a-z0-9\-]*){0,4})\b', flags=re.IGNORECASE),
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class SceneStateMachine:
    def __init__(self, initial_state: dict[str, Any] | None = None, *, default_location: str = '') -> None:
        self._state = deepcopy(initial_state) if isinstance(initial_state, dict) else self._default_state(default_location)

    @staticmethod
    def _default_state(default_location: str = '') -> dict[str, Any]:
        return {
            'phase': 'opening',
            'tension': 'steady',
            'location': str(default_location or '').strip(),
            'active_participants': [],
            'offscreen_participants': [],
            'recent_beats': [],
            'world_state': [],
            'unresolved_hooks': [],
            'last_event': '',
            'updated_at': _utc_now_iso(),
        }

    @property
    def state(self) -> dict[str, Any]:
        return deepcopy(self._state)

    def snapshot(self) -> dict[str, Any]:
        return self.state

    def set_participants(self, participants: list[dict[str, Any]]) -> None:
        names = []
        for participant in participants:
            name = str(participant.get('name', '')).strip()
            if name and name not in names:
                names.append(name)
        active = [name for name in self._state.get('active_participants', []) if name in names]
        for name in names:
            if name not in active:
                active.append(name)
        offscreen = [name for name in self._state.get('offscreen_participants', []) if name in names and name not in active]
        self._state['active_participants'] = active
        self._state['offscreen_participants'] = offscreen
        self._touch()

    def register_joined_participants(self, names: list[str]) -> None:
        active = list(self._state.get('active_participants', []))
        offscreen = list(self._state.get('offscreen_participants', []))
        added = []
        for raw_name in names:
            name = str(raw_name).strip()
            if not name:
                continue
            if name not in active:
                active.append(name)
                added.append(name)
            if name in offscreen:
                offscreen.remove(name)
        self._state['active_participants'] = active
        self._state['offscreen_participants'] = offscreen
        if added:
            self._append_world_state(f"Joined scene: {', '.join(added)}")
            self._set_phase('active')
        self._touch()

    def apply_message(self, *, text: str, role: str, speaker: str = '') -> None:
        cleaned = re.sub(r'\s+', ' ', str(text or '')).strip()
        if not cleaned or str(role).strip().lower() == 'system':
            return

        lower = cleaned.casefold()
        self._state['last_event'] = f"{speaker or role}: {cleaned[:180]}"
        self._append_recent_beat(f"{speaker or role}: {cleaned[:160]}")

        location = self._extract_location(cleaned)
        if location:
            self._state['location'] = location

        if any(keyword in lower for keyword in CONFLICT_KEYWORDS):
            self._state['tension'] = 'high'
            self._set_phase('escalation')
        elif any(keyword in lower for keyword in RESOLUTION_KEYWORDS):
            self._state['tension'] = 'easing'
            self._set_phase('cooldown')
        elif role == 'assistant' and self._state.get('phase') == 'opening':
            self._set_phase('active')

        if any(keyword in lower for keyword in CLOSING_KEYWORDS):
            self._set_phase('closing')

        question_bits = re.findall(r'([A-Z][^.?!]{0,80}\?)', cleaned)
        for hook in question_bits:
            self._append_unresolved_hook(hook)

        fact_patterns = [
            re.compile(r'\bthere (?:is|are) ([^.?!]{4,120})', flags=re.IGNORECASE),
            re.compile(r'\bthe ([A-Za-z0-9\- ]{3,80}) is ([^.?!]{2,100})', flags=re.IGNORECASE),
        ]
        for pattern in fact_patterns:
            for match in pattern.findall(cleaned):
                if isinstance(match, tuple):
                    summary = ' '.join(part.strip() for part in match if str(part).strip())
                else:
                    summary = str(match).strip()
                if summary:
                    self._append_world_state(summary)

        self._touch()

    def prompt_lines(self) -> list[str]:
        state = self._state
        lines = [
            'Scene state machine status:',
            f"- phase: {state.get('phase', 'opening')}",
            f"- tension: {state.get('tension', 'steady')}",
        ]
        location = str(state.get('location', '')).strip()
        if location:
            lines.append(f'- location: {location}')
        active = [str(item).strip() for item in state.get('active_participants', []) if str(item).strip()]
        if active:
            lines.append(f"- active participants: {', '.join(active)}")
        offscreen = [str(item).strip() for item in state.get('offscreen_participants', []) if str(item).strip()]
        if offscreen:
            lines.append(f"- offscreen participants: {', '.join(offscreen)}")
        beats = [str(item).strip() for item in state.get('recent_beats', []) if str(item).strip()]
        if beats:
            lines.append('- recent beats: ' + ' | '.join(beats[-4:]))
        world_state = [str(item).strip() for item in state.get('world_state', []) if str(item).strip()]
        if world_state:
            lines.append('- world state: ' + ' | '.join(world_state[-4:]))
        hooks = [str(item).strip() for item in state.get('unresolved_hooks', []) if str(item).strip()]
        if hooks:
            lines.append('- unresolved hooks: ' + ' | '.join(hooks[-4:]))
        return lines

    def _extract_location(self, text: str) -> str:
        for pattern in LOCATION_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            location = str(match.group(1)).strip(' .,!?:;')
            if location:
                return location
        return ''

    def _append_recent_beat(self, value: str) -> None:
        beats = [str(item).strip() for item in self._state.get('recent_beats', []) if str(item).strip()]
        if value not in beats:
            beats.append(value)
        self._state['recent_beats'] = beats[-8:]

    def _append_world_state(self, value: str) -> None:
        items = [str(item).strip() for item in self._state.get('world_state', []) if str(item).strip()]
        if value not in items:
            items.append(value)
        self._state['world_state'] = items[-8:]

    def _append_unresolved_hook(self, value: str) -> None:
        hooks = [str(item).strip() for item in self._state.get('unresolved_hooks', []) if str(item).strip()]
        cleaned = value.strip()
        if cleaned and cleaned not in hooks:
            hooks.append(cleaned)
        self._state['unresolved_hooks'] = hooks[-8:]

    def _set_phase(self, phase: str) -> None:
        self._state['phase'] = phase

    def _touch(self) -> None:
        self._state['updated_at'] = _utc_now_iso()
