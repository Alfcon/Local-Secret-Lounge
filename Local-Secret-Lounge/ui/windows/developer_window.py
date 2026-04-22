"""Developer Mode popup window.

A detached QDialog that displays the internal state of the currently-active
character (or characters) as the chat progresses. Shown only when the
"Developer Mode" checkbox in Settings is enabled.

The window is intentionally non-modal and stays on top of the main chat so
the user can watch state transitions in real time.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime
from typing import Any, Iterable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


def _clamp_int(value: Any, low: int = 0, high: int = 100, default: int = 0) -> int:
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        ivalue = int(default)
    return max(low, min(high, ivalue))


def _stat_hint(label: str, value: int) -> str:
    """Short human-readable hint beside a 0-100 stat."""
    label_lower = label.lower()
    if label_lower == 'confidence':
        if value >= 70:
            return 'Self-assured'
        if value >= 40:
            return 'Steady'
        return 'Uncertain'
    if label_lower == 'anxiety':
        if value >= 70:
            return 'On edge'
        if value >= 40:
            return 'Slightly tense'
        return 'Calm'
    if label_lower == 'hope':
        if value >= 70:
            return 'Optimistic'
        if value >= 40:
            return 'Cautiously hopeful'
        return 'Low'
    if label_lower == 'affection':
        if value >= 70:
            return 'Warm'
        if value >= 40:
            return 'Friendly'
        if value >= 15:
            return 'Low, but rising with interaction'
        return 'Distant'
    if label_lower == 'openness':
        if value >= 70:
            return 'Willing to share more'
        if value >= 40:
            return 'Selective'
        return 'Guarded'
    if label_lower == 'trust':
        if value >= 70:
            return 'Trusts user'
        if value >= 40:
            return 'Trust building'
        return 'Wary'
    if label_lower == 'respect':
        if value >= 70:
            return 'High regard'
        if value >= 40:
            return 'Respectful'
        return 'Neutral'
    if label_lower == 'anger':
        if value >= 70:
            return 'Furious'
        if value >= 40:
            return 'Irritated'
        return 'Calm'
    if label_lower == 'guilt':
        if value >= 70:
            return 'Heavy guilt'
        if value >= 40:
            return 'Some regret'
        return ''
    if label_lower == 'loneliness':
        if value >= 70:
            return 'Feels isolated'
        if value >= 40:
            return 'Seeks company'
        return 'Content alone'
    return ''


class DeveloperWindow(QDialog):
    """Live read-only snapshot of character state, scene flags, and recent
    activity.

    Refreshed explicitly by the owning ChatWindow via :meth:`update_snapshot`.
    The window is safe to construct even if no chat is active — it simply
    shows a placeholder until data is pushed in.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle('Developer Mode — Character State')
        self.setModal(False)
        # Qt.Tool keeps the window alive without stealing focus from the chat.
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.resize(520, 720)
        self.setMinimumSize(380, 420)

        self._last_user_text: str = ''
        self._last_reply_text: str = ''
        self._prev_snapshot: dict[str, dict[str, Any]] = {}
        self._build_ui()
        self._apply_stylesheet()
        self._render_placeholder()

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        self._title_label = QLabel('Developer Mode')
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        self._title_label.setFont(font)
        header.addWidget(self._title_label)
        header.addStretch()

        self._timestamp_label = QLabel('')
        self._timestamp_label.setStyleSheet('color: #a8a8c8; font-size: 10px;')
        header.addWidget(self._timestamp_label)
        outer.addLayout(header)

        # Scroll area for the content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(10)

        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setAcceptRichText(True)
        self._body.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._body.setMinimumHeight(320)
        self._content_layout.addWidget(self._body)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

    def _apply_stylesheet(self) -> None:
        # Self-contained so the dialog looks consistent even if the global
        # theme stylesheet hasn't been applied to a Qt.Tool window.
        self.setStyleSheet(
            """
            QDialog { background-color: #16213e; color: #f0f0f5; }
            QLabel { color: #f0f0f5; }
            QTextEdit {
                background-color: #1a1a2e;
                color: #f0f0f5;
                border: 1px solid #2a2a4a;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #2a2a4a;
                color: #f0f0f5;
                border: 1px solid #3a3a5a;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3a3a5a; }
            QScrollArea { background-color: #16213e; border: none; }
            """
        )

    # ── Public API ──────────────────────────────────────────────────────

    def remember_user_text(self, text: str) -> None:
        """Record the most recent user message so it can appear in
        'Recent Memory'. The chat window calls this on every send."""
        cleaned = str(text or '').strip()
        if cleaned:
            self._last_user_text = cleaned

    def remember_reply_text(self, text: str) -> None:
        """Record the most recent assistant reply for the 'Recent Memory'
        line. Called from ChatWindow._on_worker_finished."""
        cleaned = str(text or '').strip()
        if cleaned:
            self._last_reply_text = cleaned

    def clear_last_turn(self) -> None:
        self._last_user_text = ''
        self._last_reply_text = ''

    def update_snapshot(
        self,
        *,
        participants: Iterable[dict[str, Any]],
        user_display_name: str,
        scene_flags: dict[str, Any] | None = None,
        last_user_text: str | None = None,
        last_reply_text: str | None = None,
    ) -> None:
        """Rebuild the displayed snapshot from the supplied live state.

        Safe to call on every turn. No file I/O, no threads — just formats
        the in-memory state that ChatWindow already maintains.
        """
        if last_user_text is not None:
            self.remember_user_text(last_user_text)
        if last_reply_text is not None:
            self.remember_reply_text(last_reply_text)

        participants_list = [p for p in participants if isinstance(p, dict)]
        if not participants_list:
            self._render_placeholder()
            return

        sections: list[str] = []
        for idx, participant in enumerate(participants_list):
            sections.append(self._format_participant_html(participant, user_display_name))
            if idx < len(participants_list) - 1:
                sections.append('<hr style="border: 0; border-top: 1px solid #2a2a4a; margin: 8px 0;" />')

        extras = self._format_extras_html(
            scene_flags=scene_flags or {},
            user_display_name=user_display_name,
            participants=participants_list,
        )
        if extras:
            sections.append('<hr style="border: 0; border-top: 1px solid #2a2a4a; margin: 8px 0;" />')
            sections.append(extras)

        self._body.setHtml('\n'.join(sections))
        self._timestamp_label.setText(datetime.now().strftime('Updated %H:%M:%S'))

    # ── Rendering helpers ───────────────────────────────────────────────

    def _render_placeholder(self) -> None:
        self._body.setHtml(
            '<p style="color:#a8a8c8;">No active character state yet. '
            'Open a chat to see live internal state updates here.</p>'
        )
        self._timestamp_label.setText('')

    def _format_participant_html(
        self,
        participant: dict[str, Any],
        user_display_name: str,
    ) -> str:
        name = html.escape(str(participant.get('name') or 'Character'))
        role = html.escape(str(participant.get('story_role') or participant.get('role') or '').strip())

        emotional = participant.get('emotional_baseline') if isinstance(participant.get('emotional_baseline'), dict) else {}
        relationship = participant.get('relationship_with_user') if isinstance(participant.get('relationship_with_user'), dict) else {}

        confidence = _clamp_int(emotional.get('confidence', 50))
        anxiety = _clamp_int(emotional.get('anxiety', 50))
        hope = _clamp_int(emotional.get('hope', 50))
        anger = _clamp_int(emotional.get('anger', 0))
        guilt = _clamp_int(emotional.get('guilt', 0))
        loneliness = _clamp_int(emotional.get('loneliness', 0))

        affection = _clamp_int(relationship.get('affection', 0))
        openness = _clamp_int(relationship.get('openness', 0))
        trust = _clamp_int(relationship.get('trust', 0))
        respect = _clamp_int(relationship.get('respect', 0))
        status_label = html.escape(str(relationship.get('status_label') or 'Neutral'))
        interpretation = html.escape(str(relationship.get('interpretation') or '').strip())
        last_change_reason = html.escape(str(relationship.get('last_change_reason') or '').strip())

        personality = self._personality_summary(participant)
        recent_memory = self._recent_memory_line(participant)

        # Get previous stats for change calculation
        prev_stats = self._prev_snapshot.get(name, {})
        prev_emotional = prev_stats.get('emotional', {})
        prev_relationship = prev_stats.get('relationship', {})

        change_confidence = confidence - _clamp_int(prev_emotional.get('confidence', confidence))
        change_anxiety = anxiety - _clamp_int(prev_emotional.get('anxiety', anxiety))
        change_hope = hope - _clamp_int(prev_emotional.get('hope', hope))
        change_anger = anger - _clamp_int(prev_emotional.get('anger', anger))
        change_guilt = guilt - _clamp_int(prev_emotional.get('guilt', guilt))
        change_loneliness = loneliness - _clamp_int(prev_emotional.get('loneliness', loneliness))
        change_affection = affection - _clamp_int(prev_relationship.get('affection', affection))
        change_openness = openness - _clamp_int(prev_relationship.get('openness', openness))
        change_trust = trust - _clamp_int(prev_relationship.get('trust', trust))
        change_respect = respect - _clamp_int(prev_relationship.get('respect', respect))

        parts: list[str] = []

        parts: list[str] = []
        header_line = f'<h3 style="margin: 0 0 6px 0; color:#e94560;">{name}'
        if role:
            header_line += f' <span style="color:#a8a8c8; font-weight: normal; font-size: 11px;">— {role}</span>'
        header_line += '</h3>'
        parts.append(header_line)

        parts.append('<p style="margin: 2px 0; font-weight:bold; color:#f0f0f5;">Character State Table</p>')
        parts.append('<table style="width:100%; border-collapse:collapse; margin: 4px 0 8px 0;">')
        parts.append('<thead><tr><th style="text-align:left; padding:3px 6px; color:#c4b5fd; border-bottom:1px solid #3a3a5c; font-size:11px;">Attribute</th><th style="text-align:center; padding:3px 6px; color:#c4b5fd; border-bottom:1px solid #3a3a5c; font-size:11px;">Change</th><th style="text-align:center; padding:3px 6px; color:#c4b5fd; border-bottom:1px solid #3a3a5c; font-size:11px;">Value</th><th style="text-align:left; padding:3px 6px; color:#c4b5fd; border-bottom:1px solid #3a3a5c; font-size:11px;">Status</th></tr></thead>')
        parts.append('<tbody>')
        parts.append(self._stat_line_html('Confidence', confidence, change_confidence))
        parts.append(self._stat_line_html('Anxiety', anxiety, change_anxiety))
        parts.append(self._stat_line_html('Hope', hope, change_hope))
        parts.append(self._stat_line_html('Affection', affection, change_affection))
        parts.append(self._stat_line_html('Openness', openness, change_openness))
        parts.append(self._stat_line_html('Trust', trust, change_trust))
        parts.append(self._stat_line_html('Respect', respect, change_respect))
        if anger:
            parts.append(self._stat_line_html('Anger', anger, change_anger))
        if guilt:
            parts.append(self._stat_line_html('Guilt', guilt, change_guilt))
        if loneliness >= 20:
            parts.append(self._stat_line_html('Loneliness', loneliness, change_loneliness))

        if personality:
            parts.append(
                f'<tr><td style="padding:3px 6px; color:#f0f0f5;"><b>Personality</b></td><td style="padding:3px 6px; text-align:center; color:#fcd34d;">-</td><td colspan="2" style="padding:3px 6px; color:#f0f0f5;">{html.escape(personality)}</td></tr>'
            )
        parts.append(
            f'<tr><td style="padding:3px 6px; color:#f0f0f5;"><b>Relationship</b></td><td style="padding:3px 6px; text-align:center; color:#fcd34d;">-</td><td colspan="2" style="padding:3px 6px; color:#f0f0f5;">{status_label}'
            + (f' — {interpretation}' if interpretation else '')
            + '</td></tr>'
        )
        if recent_memory:
            parts.append(
                f'<tr><td style="padding:3px 6px; color:#f0f0f5;"><b>Recent Memory</b></td><td style="padding:3px 6px; text-align:center; color:#fcd34d;">-</td><td colspan="2" style="padding:3px 6px; color:#f0f0f5;">{html.escape(recent_memory)}</td></tr>'
            )
        if last_change_reason:
            parts.append(
                f'<tr><td style="padding:3px 6px; color:#f0f0f5;"><b>Last Change</b></td><td style="padding:3px 6px; text-align:center; color:#fcd34d;">-</td><td colspan="2" style="padding:3px 6px; color:#f0f0f5;">{last_change_reason}</td></tr>'
            )
        parts.append('</tbody></table>')

        reaction_html = self._format_reaction_section(
            participant=participant,
            user_display_name=user_display_name,
            affection=affection,
            openness=openness,
            confidence=confidence,
            anxiety=anxiety,
            hope=hope,
            anger=anger,
            status_label=str(relationship.get('status_label') or 'Neutral'),
        )
        parts.append(reaction_html)

        # Update previous snapshot for next change calculation
        self._prev_snapshot[name] = {
            'emotional': {
                'confidence': confidence,
                'anxiety': anxiety,
                'hope': hope,
                'anger': anger,
                'guilt': guilt,
                'loneliness': loneliness,
            },
            'relationship': {
                'affection': affection,
                'openness': openness,
                'trust': trust,
                'respect': respect,
            }
        }

        return '\n'.join(parts)

    def _stat_line_html(self, label: str, value: int, change: int) -> str:
        hint = _stat_hint(label, value)
        hint_html = html.escape(hint) if hint else '—'
        # Format change
        if change > 0:
            change_color = '#86efac'  # green
            change_text = f'+{change}'
        elif change < 0:
            change_color = '#fca5a5'  # red
            change_text = f'{change}'  # already has -
        else:
            change_color = '#fcd34d'  # orange
            change_text = '-0'
        change_html = f'<span style="color:{change_color}; font-weight:bold;">{change_text}</span>'
        return (
            f'<tr>'
            f'<td style="padding:3px 6px; color:#f0f0f5;"><b>{html.escape(label)}</b></td>'
            f'<td style="padding:3px 6px; text-align:center; color:#f0f0f5;">{change_html}</td>'
            f'<td style="padding:3px 6px; text-align:center; color:#f0f0f5;">{value}/100</td>'
            f'<td style="padding:3px 6px; color:#a8a8c8;">{hint_html}</td>'
            f'</tr>'
        )

    def _personality_summary(self, participant: dict[str, Any]) -> str:
        """Build a short personality descriptor from static fields."""
        identity = participant.get('identity')
        voice = participant.get('voice')
        description = participant.get('description')

        traits: list[str] = []
        if isinstance(identity, dict):
            for key in ('personality', 'traits', 'temperament', 'archetype'):
                val = identity.get(key)
                if isinstance(val, str) and val.strip():
                    traits.append(val.strip())
                elif isinstance(val, list):
                    for item in val:
                        text = str(item).strip()
                        if text:
                            traits.append(text)
        elif isinstance(identity, str) and identity.strip():
            traits.append(identity.strip())

        if isinstance(voice, dict):
            for key in ('tone', 'style', 'mannerisms'):
                val = voice.get(key)
                if isinstance(val, str) and val.strip():
                    traits.append(val.strip())
        elif isinstance(voice, str) and voice.strip():
            traits.append(voice.strip())

        if not traits and isinstance(description, str) and description.strip():
            # Fall back to the first sentence of the description.
            desc = description.strip().replace('\n', ' ')
            first_sentence = desc.split('.')[0].strip()
            if first_sentence:
                traits.append(first_sentence[:160])

        # Deduplicate while preserving order, then cap length.
        seen: set[str] = set()
        unique_traits: list[str] = []
        for t in traits:
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_traits.append(t)
            if len(unique_traits) >= 4:
                break

        summary = ', '.join(unique_traits)
        if len(summary) > 220:
            summary = summary[:217].rstrip() + '...'
        return summary

    def _recent_memory_line(self, participant: dict[str, Any]) -> str:
        """Return the freshest episodic memory or the last reply snippet."""
        memories = participant.get('memories') if isinstance(participant.get('memories'), dict) else {}
        episodic = memories.get('episodic') if isinstance(memories.get('episodic'), list) else []
        if episodic:
            latest = episodic[-1]
            if isinstance(latest, dict):
                text = str(latest.get('summary') or latest.get('text') or latest.get('content') or '').strip()
                if text:
                    return text[:220] + ('...' if len(text) > 220 else '')

        if self._last_reply_text:
            snippet = self._last_reply_text.strip().replace('\n', ' ')
            if len(snippet) > 180:
                snippet = snippet[:177].rstrip() + '...'
            return snippet
        if self._last_user_text:
            snippet = self._last_user_text.strip().replace('\n', ' ')
            if len(snippet) > 180:
                snippet = snippet[:177].rstrip() + '...'
            return f'User said: "{snippet}"'
        return ''

    def _format_reaction_section(
        self,
        *,
        participant: dict[str, Any],
        user_display_name: str,
        affection: int,
        openness: int,
        confidence: int,
        anxiety: int,
        hope: int,
        anger: int,
        status_label: str,
    ) -> str:
        """Heuristic 'Determine Reaction' + 'Internal thought' derived from the
        actual stat values. These are labels the developer would use to sanity-
        check whether stats move in a sensible direction — they are NOT
        generated by an LLM call.
        """
        user = html.escape(user_display_name or 'the user')
        name = html.escape(str(participant.get('name') or 'She'))

        bullets: list[str] = []
        # Confidence / anxiety interaction
        if confidence >= 60 and anxiety <= 40:
            bullets.append(f'{name} feels steady and is willing to engage with {user} openly.')
        elif anxiety >= 60 and confidence < 50:
            bullets.append(f'{name} is visibly tense; expect guarded or hesitant phrasing.')
        else:
            bullets.append(f'{name} is balanced — neither eager nor withdrawn.')

        # Affection / openness
        if affection >= 50 and openness >= 50:
            bullets.append(f'Warmth is present — {name} will likely share personal details or flirt lightly.')
        elif openness >= 50:
            bullets.append(f'{name} is willing to share, even if affection has not caught up yet.')
        elif affection >= 50 and openness < 40:
            bullets.append(f'{name} cares but keeps topics surface-level.')
        elif affection < 20 and openness < 30:
            bullets.append(f'{name} is reserved and likely to deflect deeper questions.')

        # Hope / anger
        if hope >= 60:
            bullets.append(f'Hope is high — {name} wants the interaction to go somewhere good.')
        if anger >= 50:
            bullets.append(f'{name} is holding back anger; watch for clipped or sharp replies.')

        # Relationship status narrative
        if status_label:
            bullets.append(f'Relationship reads as "{html.escape(status_label)}".')

        bullet_html = ''.join(f'<li>{b}</li>' for b in bullets)

        # Internal thought (single line, derived from the dominant axis).
        internal_thought = self._derive_internal_thought(
            affection=affection,
            openness=openness,
            confidence=confidence,
            anxiety=anxiety,
            hope=hope,
            anger=anger,
        )

        section = (
            '<p style="margin: 8px 0 2px 0; font-weight:bold; color:#f0f0f5;">'
            f'Determine {name}\'s Reaction:</p>'
            f'<ul style="margin: 2px 0 6px 18px; padding: 0;">{bullet_html}</ul>'
            '<p style="margin: 4px 0 2px 0; font-style: italic; color:#c4b5fd;">'
            f'Internal thought: {html.escape(internal_thought)}</p>'
        )
        return section

    @staticmethod
    def _derive_internal_thought(
        *,
        affection: int,
        openness: int,
        confidence: int,
        anxiety: int,
        hope: int,
        anger: int,
    ) -> str:
        if anger >= 60:
            return 'I need to hold my tongue before I say something I\'ll regret.'
        if anxiety >= 70:
            return 'This is a lot — I have to steady myself before I answer.'
        if affection >= 70 and openness >= 60:
            return 'I actually want them to stay — I like where this is going.'
        if affection >= 40 and confidence >= 60:
            return 'Keep the energy up — I\'ve got this, and I want to stay the main attraction.'
        if hope >= 60 and confidence >= 50:
            return 'There\'s real momentum here. Don\'t drop it.'
        if openness >= 60 and affection < 30:
            return 'Curious enough to stay in the conversation — not ready to trust yet.'
        if confidence < 40 and anxiety >= 40:
            return 'Tread carefully — one wrong word and I\'ll pull back.'
        return 'Reading the room before I commit to anything.'

    def _voice_bits_for_participant(self, participant: dict[str, Any]) -> list[tuple[str, str]]:
        """Return the same voice / identity / boundary fields that
        chat_window.py's ``_participant_voice_lines`` emits into the
        prompt, formatted as (label, value) pairs for HTML rendering.

        Mirrors the 'raw' fallback logic so user-created characters
        (which are stored flat) render the same as built-in characters.
        """

        def _as_list(value: Any) -> list[str]:
            if not value:
                return []
            if isinstance(value, (list, tuple, set)):
                items = [str(item).strip() for item in value]
            elif isinstance(value, dict):
                items = [str(item).strip() for item in value.values()]
            else:
                items = [str(value).strip()]
            return [item for item in items if item]

        raw_candidate = participant.get('raw') if isinstance(participant, dict) else None
        raw = raw_candidate if isinstance(raw_candidate, dict) and raw_candidate else participant
        if not isinstance(raw, dict):
            raw = {}
        identity = raw.get('identity') if isinstance(raw.get('identity'), dict) else {}
        if not isinstance(identity, dict):
            identity = {}
        voice = raw.get('voice') if isinstance(raw.get('voice'), dict) else {}
        if not isinstance(voice, dict):
            voice = {}
        boundaries = identity.get('boundaries') if isinstance(identity.get('boundaries'), dict) else {}
        if not isinstance(boundaries, dict):
            boundaries = {}
        goals = identity.get('goals') if isinstance(identity.get('goals'), dict) else {}
        if not isinstance(goals, dict):
            goals = {}

        def _join(items: list[str], limit: int = 6) -> str:
            return ', '.join(items[:limit])

        pairs: list[tuple[str, str]] = []

        age = str(identity.get('age_band', identity.get('age', '')) or '').strip()
        if age:
            pairs.append(('Age', age))

        tone = str(voice.get('tone', '') or '').strip()
        if tone:
            pairs.append(('Tone', tone))

        cadence = str(voice.get('cadence', '') or '').strip()
        if cadence:
            pairs.append(('Cadence', cadence))

        favored = _join(_as_list(voice.get('favored_patterns')))
        if favored:
            pairs.append(('Favored phrases', favored))

        avoid = _join(_as_list(voice.get('avoid_patterns')))
        if avoid:
            pairs.append(('Avoid', avoid))

        traits = _join(_as_list(identity.get('core_traits')))
        if traits:
            pairs.append(('Core traits', traits))

        values = _join(_as_list(identity.get('values')))
        if values:
            pairs.append(('Values', values))

        fears = _join(_as_list(identity.get('fears')))
        if fears:
            pairs.append(('Fears', fears))

        goal_bits: list[str] = []
        for horizon_key, horizon_label in (
            ('short_term', 'short'),
            ('mid_term', 'mid'),
            ('long_term', 'long'),
        ):
            horizon_items = _as_list(goals.get(horizon_key))
            horizon_text = _join(horizon_items, limit=3)
            if horizon_text:
                goal_bits.append(f'{horizon_label}: {horizon_text}')
        if goal_bits:
            pairs.append(('Goals', '; '.join(goal_bits)))

        hard = _join(_as_list(boundaries.get('hard')))
        if hard:
            pairs.append(('Hard limits', hard))

        soft = _join(_as_list(boundaries.get('soft')))
        if soft:
            pairs.append(('Soft preferences', soft))

        private_truths = _join(_as_list(identity.get('private_truths')))
        if private_truths:
            pairs.append(('Private truths', private_truths))

        return pairs

    def _format_voice_preview_html(self, participants: list[dict[str, Any]]) -> str:
        """Render a 'Voice & Limits Sent To Model' panel showing the exact
        voice/identity fields being injected into the prompt for each
        participant. This is the developer-mode mirror of
        ``_participant_voice_lines`` in chat_window.py.
        """
        participants = [p for p in (participants or []) if isinstance(p, dict)]
        if not participants:
            return ''

        blocks: list[str] = []
        for p in participants:
            pairs = self._voice_bits_for_participant(p)
            if not pairs:
                continue
            name = html.escape(str(p.get('name') or 'Character'))
            rows: list[str] = []
            for label, value in pairs:
                safe_label = html.escape(label)
                # Truncate very long values so the panel stays readable.
                display_value = value if len(value) <= 500 else value[:500] + '…'
                safe_value = html.escape(display_value)
                rows.append(
                    '<li style="margin: 1px 0; color:#e8e8f5;">'
                    f'<span style="color:#7dd3fc;"><b>{safe_label}:</b></span> {safe_value}'
                    '</li>'
                )
            if not rows:
                continue
            blocks.append(
                f'<p style="margin: 6px 0 2px 0; color:#f3a6ff;"><b>{name}</b></p>'
                '<ul style="margin: 0 0 6px 18px; padding: 0; font-size: 12px;">'
                + '\n'.join(rows)
                + '</ul>'
            )

        if not blocks:
            return ''

        header = (
            '<p style="margin: 2px 0; font-weight:bold; color:#f0f0f5;">'
            'Voice &amp; Limits Sent To Model:'
            '</p>'
            '<p style="margin: 0 0 4px 0; color:#a8a8c8; font-size: 11px;">'
            'Exact voice, traits, goals, and boundaries injected into the '
            'prompt. Empty fields are omitted.'
            '</p>'
        )
        return header + '\n'.join(blocks)

    def _format_example_dialogue_html(self, participants: list[dict[str, Any]]) -> str:
        """Render any configured ``example_dialogue`` text per participant
        so the developer can confirm it is being delivered to the model.
        """
        participants = [p for p in (participants or []) if isinstance(p, dict)]
        rows: list[str] = []
        for p in participants:
            raw_candidate = p.get('raw') if isinstance(p.get('raw'), dict) else None
            raw = raw_candidate if isinstance(raw_candidate, dict) and raw_candidate else p
            text = str(raw.get('example_dialogue', '') or p.get('example_dialogue', '') or '').strip()
            if not text:
                continue
            name = html.escape(str(p.get('name') or 'Character'))
            snippet = html.escape(text if len(text) <= 600 else text[:600] + '…')
            # Preserve line breaks for readability.
            snippet = snippet.replace('\n', '<br/>')
            rows.append(
                f'<p style="margin: 4px 0 2px 0; color:#f3a6ff;"><b>{name}</b></p>'
                f'<p style="margin: 0 0 6px 12px; color:#e8e8f5; font-size: 12px; '
                f'border-left: 2px solid #3a4163; padding-left: 8px;">{snippet}</p>'
            )
        if not rows:
            return ''
        return (
            '<p style="margin: 2px 0; font-weight:bold; color:#f0f0f5;">'
            'Example Dialogue Provided:'
            '</p>'
            + '\n'.join(rows)
        )

    def _format_extras_html(
        self,
        *,
        scene_flags: dict[str, Any],
        user_display_name: str,
        participants: list[dict[str, Any]] | None = None,
    ) -> str:
        parts: list[str] = []

        # Voice & limits preview — show what chat_window is sending into the
        # prompt for each participant. Developers can verify voice data is
        # actually reaching the model.
        voice_html = self._format_voice_preview_html(participants or [])
        if voice_html:
            parts.append(voice_html)

        # Example dialogue preview (if any characters have it configured).
        dialogue_html = self._format_example_dialogue_html(participants or [])
        if dialogue_html:
            parts.append(dialogue_html)

        if scene_flags:
            flag_items: list[str] = []
            for key, value in scene_flags.items():
                if isinstance(value, bool):
                    if value:
                        flag_items.append(html.escape(str(key).replace('_', ' ')))
                elif value not in (None, '', 0):
                    flag_items.append(f'{html.escape(str(key))}={html.escape(str(value))}')
            if flag_items:
                parts.append(
                    '<p style="margin: 2px 0; font-weight:bold; color:#f0f0f5;">Scene Flags:</p>'
                    f'<p style="margin: 2px 0 6px 0;">{", ".join(flag_items)}</p>'
                )

        if self._last_user_text or self._last_reply_text:
            parts.append('<p style="margin: 2px 0; font-weight:bold; color:#f0f0f5;">Last Turn:</p>')
            if self._last_user_text:
                snippet = html.escape(self._last_user_text[:300])
                parts.append(
                    f'<p style="margin: 2px 0; color:#7dd3fc;"><b>{html.escape(user_display_name or "User")}:</b> {snippet}</p>'
                )
            if self._last_reply_text:
                snippet = html.escape(self._last_reply_text[:400])
                parts.append(
                    f'<p style="margin: 2px 0; color:#f3a6ff;"><b>Reply:</b> {snippet}</p>'
                )

        return '\n'.join(parts)

    # ── Event handlers ──────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: D401 - Qt override
        """Hide instead of destroying so the ChatWindow can re-show it."""
        event.ignore()
        self.hide()
