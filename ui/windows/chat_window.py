from __future__ import annotations

import html
import json
import logging
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QCloseEvent, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.character_manager import CharacterManager
from core.character_state import apply_message_to_character_memory, build_memory_prompt_lines
from core.chat_engine import ChatEngine
from core.memory_store import MemoryStore
from core.paths import get_data_dir
from core.prompt_assets import PromptAssetLoader
from core.scene_state import SceneStateMachine
from ui.windows.developer_window import DeveloperWindow


INTRO_PATTERNS = re.compile(
    r"\b(?:catch up with|meet|invite|bring in|add|include|call|find|visit|talk to|speak to|introduce(?:\s+to)?|join(?:\s+us|\s+the\s+chat|\s+the\s+story)?(?:\s+with)?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
)

TIMESTAMP_HEADER_RE = re.compile(r'(?m)^\[([0-9]{1,2}:[0-9]{2})\]\s*([^\n]+?)\s*$')
INLINE_TIMESTAMP_RE = re.compile(r'(?<=\S)(\[[0-9]{1,2}:[0-9]{2}\]\s*(?:Scene|System|[A-Z][^\n]{0,80}))')
MIN_REPLY_MAX_TOKENS = 384
CONTEXT_MESSAGE_TAIL_MIN = 8
CONTEXT_MESSAGE_TAIL_MAX = 14
CONTEXT_SUMMARY_MAX_LINES = 24
CONTEXT_SUMMARY_FUSED_CHARS = 900
CONTEXT_SUMMARY_LINE_CHARS = 220
CONTEXT_PROMPT_SAFETY_TOKENS = 192

logger = logging.getLogger(__name__)


CHARACTER_COLOR_PALETTE = [
    '#f3a6ff',
    '#7dd3fc',
    '#86efac',
    '#fca5a5',
    '#fcd34d',
    '#c4b5fd',
    '#fdba74',
    '#93c5fd',
]


def _safe_character_chat_color(value: Any, default: str = '') -> str:
    text = str(value or '').strip()
    if not text:
        return default
    if text.startswith('#'):
        hex_value = text[1:]
        if len(hex_value) in (3, 6) and all(ch in '0123456789abcdefABCDEF' for ch in hex_value):
            return text
    return default


class ChatWorker(QObject):
    finished = Signal(int, str)
    partial = Signal(int, str)
    error = Signal(int, str)

    def __init__(
        self,
        request_id: int,
        chat_engine: ChatEngine,
        model_entry: dict[str, Any],
        messages: list[dict[str, str]],
        generation_settings: dict[str, Any],
        stop_sequences: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.chat_engine = chat_engine
        self.model_entry = model_entry
        self.messages = messages
        self.generation_settings = generation_settings
        self.stop_sequences = [str(item) for item in (stop_sequences or []) if str(item).strip()]

    @Slot()
    def run(self) -> None:
        try:
            chunks: list[str] = []
            for piece in self.chat_engine.generate_reply_stream(
                model_entry=self.model_entry,
                messages=self.messages,
                temperature=float(self.generation_settings.get('temperature', 0.8)),
                max_tokens=max(MIN_REPLY_MAX_TOKENS, int(self.generation_settings.get('max_tokens', 512))),
                n_ctx=int(self.generation_settings.get('context_size', 4096)),
                n_threads=int(self.generation_settings.get('threads', 4)),
                n_gpu_layers=int(self.generation_settings.get('n_gpu_layers', 0)),
                stop=self.stop_sequences,
            ):
                if not piece:
                    continue
                chunks.append(piece)
                self.partial.emit(self.request_id, ''.join(chunks))
            reply = self.chat_engine.clean_generated_text(''.join(chunks))
            if not reply:
                raise RuntimeError('The model returned an empty response.')
        except Exception as exc:
            self.error.emit(self.request_id, str(exc))
            return
        self.finished.emit(self.request_id, reply)


class CharacterInfoCard(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()

        self.setStyleSheet(
            'QFrame { background-color: #101522; border: 1px solid #2f3756; border-radius: 16px; }'
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)

        self.avatar_label = QLabel('No image')
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setWordWrap(True)
        self.avatar_label.setMinimumSize(80, 110)
        self.avatar_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.avatar_label.setStyleSheet(
            'border: 1px solid #3a4163; border-radius: 12px; color: #b8b0d7; '
            'background-color: #171a26; padding: 4px;'
        )
        layout.addWidget(self.avatar_label, 0, Qt.AlignTop)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(6)

        self.name_label = QLabel('Character')
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet('font-size: 16px; font-weight: 700; color: #f3dbff; border: none;')
        text_column.addWidget(self.name_label)

        self.title_label = QLabel('')
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet('font-size: 13px; color: #d8d8f0; border: none; font-weight: bold;')
        text_column.addWidget(self.title_label)

        self.description_label = QLabel('')
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.description_label.setStyleSheet('font-size: 12px; color: #f0f0ff; border: none;')
        text_column.addWidget(self.description_label)

        layout.addLayout(text_column, stretch=1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self._apply_pixmap()

    def set_character(self, character: dict[str, Any]) -> None:
        name = str(character.get('name', 'Character')).strip() or 'Character'
        title = str(character.get('title', '')).strip()
        description = str(character.get('description', '')).strip()
        name_color = _safe_character_chat_color(
            character.get('name_color', character.get('name_colour', '')),
            '#f3dbff',
        )

        self.name_label.setText(name)
        self.name_label.setStyleSheet(
            f'font-size: 16px; font-weight: 700; color: {name_color}; border: none;'
        )
        self.title_label.setText(title)
        self.title_label.setVisible(bool(title))
        self.description_label.setText(description or 'No description yet.')
        self._set_avatar(str(character.get('avatar_path', '')).strip(), fallback_text=f'{name}\n\nNo image found')

    def _set_avatar(self, avatar_path: str, *, fallback_text: str) -> None:
        if not avatar_path:
            self._pixmap = QPixmap()
            self.avatar_label.setPixmap(QPixmap())
            self.avatar_label.setText(fallback_text)
            return

        file_path = Path(avatar_path).expanduser()
        if not file_path.exists():
            self._pixmap = QPixmap()
            self.avatar_label.setPixmap(QPixmap())
            self.avatar_label.setText(fallback_text)
            return

        pixmap = QPixmap(str(file_path))
        if pixmap.isNull():
            self._pixmap = QPixmap()
            self.avatar_label.setPixmap(QPixmap())
            self.avatar_label.setText(fallback_text)
            return

        self._pixmap = pixmap
        self.avatar_label.setText('')
        self._apply_pixmap()

    def _apply_pixmap(self) -> None:
        if self._pixmap.isNull():
            return
        rect = self.avatar_label.contentsRect()
        target = rect.size()
        if target.width() <= 0 or target.height() <= 0:
            return
        scaled = self._pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.avatar_label.setPixmap(scaled)


class ChatWindow(QMainWindow):
    chat_closed = Signal()

    def __init__(
        self,
        *,
        settings_manager,
        model_manager,
        chat_storage,
        model_entry: dict[str, Any],
        character: dict[str, Any],
        generation_settings: dict[str, Any],
        chat_session: dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.model_manager = model_manager
        self.chat_storage = chat_storage
        self.model_entry = model_entry
        self.character = dict(character)
        self.generation_settings = generation_settings
        self.chat_engine = ChatEngine(settings_manager)
        self.character_manager = CharacterManager()
        self.prompt_loader = PromptAssetLoader()
        self.memory_store = MemoryStore()
        self.chat_session = chat_session
        self.messages: list[dict[str, Any]] = []
        self.user_display_name = self._resolve_user_display_name(chat_session)
        self.participants: list[dict[str, Any]] = []
        self.story_location_city = str(self.settings_manager.get('story_location_city', '') or '').strip()
        self.story_location_country = str(self.settings_manager.get('story_location_country', '') or '').strip()
        self.rolling_summary = ''
        self.rolling_summary_message_count = 0
        self.scene_state_machine = SceneStateMachine(default_location=self._story_location_text())
        self._streaming_base_html = ''
        self._streaming_preview_text = ''

        self.transcript: QTextEdit | None = None
        self.input_box: QTextEdit | None = None
        self.send_button: QPushButton | None = None
        self.cancel_button: QPushButton | None = None
        self.retry_button: QPushButton | None = None
        self.waiting_label: QLabel | None = None
        self.waiting_bar: QProgressBar | None = None
        self.error_label: QLabel | None = None
        self.chat_title_label: QLabel | None = None

        self.sidebar_scroll: QScrollArea | None = None
        self.sidebar_cards_container: QWidget | None = None
        self.sidebar_cards_layout: QVBoxLayout | None = None

        self._request_counter = 0
        self._active_request_id: int | None = None
        self._pending_threads: dict[int, QThread] = {}
        self._pending_workers: dict[int, ChatWorker] = {}
        self._canceled_requests: set[int] = set()
        self._retry_available = False

        self._developer_window: DeveloperWindow | None = None

        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(1180, 780)
        self._build_ui()
        self._load_or_initialize_chat()
        self._refresh_sidebar_cards()
        self._set_waiting_state(False, '')
        self._set_retry_state(False, '')
        self._sync_developer_window_visibility()
        self._refresh_developer_window()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        outer = QHBoxLayout(central)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        sidebar = QFrame()
        sidebar.setStyleSheet(
            'QFrame { background-color: #0f1423; border: 1px solid #30395b; border-radius: 18px; }'
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 14)
        sidebar_layout.setSpacing(12)

        sidebar_title = QLabel('Characters')
        sidebar_title.setObjectName('pageTitle')
        sidebar_layout.addWidget(sidebar_title)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.sidebar_cards_container = QWidget()
        self.sidebar_cards_layout = QVBoxLayout(self.sidebar_cards_container)
        self.sidebar_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_cards_layout.setSpacing(10)
        self.sidebar_cards_layout.addStretch(1)

        self.sidebar_scroll.setWidget(self.sidebar_cards_container)
        sidebar_layout.addWidget(self.sidebar_scroll, stretch=1)

        content = QFrame()
        content.setStyleSheet(
            'QFrame { background-color: #0f1423; border: 1px solid #30395b; border-radius: 18px; }'
        )
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        self.chat_title_label = QLabel('Chat')
        self.chat_title_label.setObjectName('pageTitle')
        self.chat_title_label.setWordWrap(True)
        content_layout.addWidget(self.chat_title_label)

        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setAcceptRichText(True)
        self.transcript.setStyleSheet(
            'QTextEdit { background-color: #0a1020; color: #ece7ff; border: 1px solid #30395b; '
            'border-radius: 16px; selection-background-color: #5b4da0; padding: 10px; }'
        )
        content_layout.addWidget(self.transcript, stretch=1)

        waiting_row = QHBoxLayout()
        waiting_row.setSpacing(10)

        self.waiting_label = QLabel('')
        self.waiting_label.setStyleSheet('color: #f0f0ff; font-weight: bold;')
        waiting_row.addWidget(self.waiting_label)

        self.waiting_bar = QProgressBar()
        self.waiting_bar.setRange(0, 0)
        self.waiting_bar.setTextVisible(False)
        self.waiting_bar.setFixedHeight(10)
        self.waiting_bar.setStyleSheet(
            'QProgressBar { background-color: #1a2030; border: 1px solid #49527b; border-radius: 6px; } '
            'QProgressBar::chunk { background-color: #8d6bf0; border-radius: 6px; }'
        )
        waiting_row.addWidget(self.waiting_bar, 1)

        self.cancel_button = QPushButton('Cancel Waiting')
        self.cancel_button.clicked.connect(self._cancel_active_request)
        waiting_row.addWidget(self.cancel_button)
        content_layout.addLayout(waiting_row)

        self.error_label = QLabel('')
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #ff6578; font-weight: bold;')
        content_layout.addWidget(self.error_label)

        self.input_box = QTextEdit()
        self.input_box.setFixedHeight(118)
        self.input_box.setPlaceholderText(f'Type your message as {self.user_display_name}...')
        self.input_box.setStyleSheet(
            'QTextEdit { background-color: #1a2030; color: #f4f1ff; border: 1px solid #49527b; '
            'border-radius: 16px; selection-background-color: #6c5dd3; padding: 10px; }'
        )
        content_layout.addWidget(self.input_box)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        clear_button = QPushButton('Clear Input')
        clear_button.clicked.connect(self._clear_input)
        button_row.addWidget(clear_button)

        exit_button = QPushButton('Exit Chat')
        exit_button.clicked.connect(self.close)
        button_row.addWidget(exit_button)

        self.retry_button = QPushButton('Retry Last Reply')
        self.retry_button.clicked.connect(self._retry_last_reply)
        button_row.addWidget(self.retry_button)

        button_row.addStretch(1)

        self.send_button = QPushButton('Send')
        self.send_button.clicked.connect(self.on_send_clicked)
        button_row.addWidget(self.send_button)
        content_layout.addLayout(button_row)

        outer.addWidget(sidebar, stretch=1)
        outer.addWidget(content, stretch=2)

    def _resolve_user_display_name(self, chat_session: dict[str, Any] | None) -> str:
        if isinstance(chat_session, dict):
            stored_name = str(chat_session.get('user_name', '') or '').strip()
            if stored_name:
                return stored_name
        current_name = str(self.settings_manager.get('user_name', '') or '').strip()
        return current_name or 'You'

    def _personalize_text(self, text: str) -> str:
        result = str(text or '')
        replacements = {
            '{{user_name}}': self.user_display_name,
            '{user_name}': self.user_display_name,
            '[[user_name]]': self.user_display_name,
            '<<user_name>>': self.user_display_name,
        }
        for token, value in replacements.items():
            result = result.replace(token, value)
        return result

    def _chat_title_text(self) -> str:
        name = str(self.character.get('name', 'Character')).strip() or 'Character'
        if len(self.participants) > 1:
            others = [
                str(item.get('name', '')).strip()
                for item in self.participants
                if str(item.get('id', '')).strip() != str(self.character.get('id', '')).strip()
            ]
            others = [item for item in others if item]
            if others:
                preview = ', '.join(others[:2])
                if len(others) > 2:
                    preview = f'{preview}, +{len(others) - 2} more'
                return f'{name} — story with {preview}'
        title = str(self.character.get('title', '')).strip()
        if title:
            return f'{name} — {title}'
        return name

    def _normalize_participants(self, participants: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        candidate_list = participants if isinstance(participants, list) else []

        for item in candidate_list:
            if not isinstance(item, dict):
                continue
            character_id = str(item.get('id', '')).strip()
            key = character_id or str(item.get('name', '')).strip().lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            normalized.append(dict(item))

        if not normalized:
            normalized.append(dict(self.character))

        primary_id = str(self.character.get('id', '')).strip()
        primary = None
        for item in normalized:
            if str(item.get('id', '')).strip() == primary_id:
                primary = item
                break
        if primary is None:
            normalized.insert(0, dict(self.character))
        else:
            normalized = [primary] + [item for item in normalized if str(item.get('id', '')).strip() != primary_id]
        return normalized

    def _story_location_text(self) -> str:
        city = self.story_location_city.strip()
        country = self.story_location_country.strip()
        if city and country:
            return f'{city}, {country}'
        return city or country

    def _speaker_profile_text(self, speaker: str) -> str:
        target = str(speaker or '').strip().casefold()
        if not target:
            return ''
        for participant in self.participants:
            participant_name = str(participant.get('name', '')).strip()
            if participant_name.casefold() != target:
                continue
            raw = participant.get('raw') if isinstance(participant.get('raw'), dict) else {}
            identity = raw.get('identity') if isinstance(raw.get('identity'), dict) else {}
            pieces = [
                str(participant.get('title', '') or '').strip(),
                str(participant.get('description', '') or '').strip(),
                str(raw.get('role', '') or '').strip(),
                str(raw.get('story_role', '') or '').strip(),
                str(identity.get('public_summary', '') or '').strip(),
            ]
            return ' '.join(piece for piece in pieces if piece)
        return ''

    def _narration_pronouns_for_speaker(self, speaker: str) -> tuple[str, str]:
        profile_text = self._speaker_profile_text(speaker).casefold()
        female_markers = (' she ', ' her ', ' hers ', ' woman', ' girl', ' female', ' girlfriend', ' sister')
        male_markers = (' he ', ' him ', ' his ', ' man', ' boy', ' male', ' boyfriend', ' brother')
        padded = f' {profile_text} '
        if any(marker in padded for marker in female_markers):
            return 'She', 'Her'
        if any(marker in padded for marker in male_markers):
            return 'He', 'His'
        return 'They', 'Their'

    def _naturalize_leading_speaker_references(
        self,
        text: str,
        *,
        speaker: str = '',
        role: str = '',
        message_format: str = '',
    ) -> str:
        cleaned = str(text or '').strip()
        normalized_speaker = str(speaker or '').strip()
        if not cleaned or not normalized_speaker or role in {'user', 'system'} or message_format == 'scenario':
            return cleaned

        subject_pronoun, possessive_pronoun = self._narration_pronouns_for_speaker(normalized_speaker)
        escaped_speaker = re.escape(normalized_speaker)

        cleaned = re.sub(
            rf"(?mi)^\s*{escaped_speaker}(?:[’']s?)?\.?\s*$",
            '',
            cleaned,
        )
        cleaned = re.sub(
            rf"(?mi)^(?P<prefix>\s*){escaped_speaker}[’']s\b",
            lambda match: f"{match.group('prefix')}{possessive_pronoun}",
            cleaned,
        )
        cleaned = re.sub(
            rf'(?mi)^(?P<prefix>\s*){escaped_speaker}\b(?=\s+[a-z])',
            lambda match: f"{match.group('prefix')}{subject_pronoun}",
            cleaned,
        )
        while '\n\n\n' in cleaned:
            cleaned = cleaned.replace('\n\n\n', '\n\n')
        return cleaned.strip()

    @staticmethod
    def _clean_fact_snippet(value: str, *, limit: int = 220) -> str:
        cleaned = re.sub(r'\s+', ' ', str(value or '')).strip(' -|')
        if len(cleaned) > limit:
            return cleaned[: limit - 1].rstrip() + '…'
        return cleaned

    def _participant_canon_lines(self) -> list[str]:
        lines = ['Canonical participant facts from the character files. Treat these as ground truth and check them before every reply:']
        for participant in self.participants:
            name = str(participant.get('name', 'Character')).strip() or 'Character'
            # Built-in/discover characters carry the full card dict under
            # 'raw'. User-created characters store everything flat on the
            # participant dict itself, so fall back to that when 'raw' is
            # missing or empty.
            raw_candidate = participant.get('raw')
            raw = raw_candidate if isinstance(raw_candidate, dict) and raw_candidate else participant
            if not isinstance(raw, dict):
                raw = {}
            identity = raw.get('identity') if isinstance(raw.get('identity'), dict) else {}
            knowledge = raw.get('knowledge') if isinstance(raw.get('knowledge'), dict) else {}

            facts: list[str] = []
            candidates: list[str] = [
                str(raw.get('role') or participant.get('title') or '').strip(),
                str(raw.get('story_role') or '').strip(),
                str(identity.get('public_summary') or participant.get('description') or '').strip(),
            ]
            for fact in knowledge.get('known_facts', []):
                text = str(fact).strip()
                if text:
                    candidates.append(text)
            lore = str(participant.get('world_lore_notes', '') or '').strip()
            if lore:
                candidates.append(lore)

            seen: set[str] = set()
            for candidate in candidates:
                cleaned = self._clean_fact_snippet(candidate)
                key = cleaned.casefold()
                if cleaned and key not in seen:
                    facts.append(cleaned)
                    seen.add(key)
                if len(facts) >= 6:
                    break

            if facts:
                lines.append(f'- {name}: ' + ' | '.join(facts))
            else:
                lines.append(f'- {name}: No extra canon facts provided.')
        return lines

    def _participant_memory_lines(self) -> list[str]:
        lines = ['Current participant memory and relationship state. Treat this as mutable session context and keep it consistent unless the scene clearly changes it:']
        for participant in self.participants:
            lines.extend(build_memory_prompt_lines(participant))
        return lines

    def _participant_voice_lines(self) -> list[str]:
        """Render each participant's voice, traits, values, fears, goals,
        boundaries, age, and private truths so the model can actually
        differentiate how they speak and what they will and won't do.

        Reads from participant['raw'] (the original character card dict).
        Every field is optional; missing pieces are skipped silently so
        older cards still work.
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

        def _join(values: list[str], limit: int = 6) -> str:
            trimmed = [self._clean_fact_snippet(v, limit=160) for v in values[:limit]]
            trimmed = [t for t in trimmed if t]
            return ', '.join(trimmed)

        header = (
            'Voice, values, and limits for each participant. Use these to shape HOW each '
            'character speaks and what they will or will not do. Do not quote this block; '
            'let it influence cadence, word choice, and in-scene reactions naturally.'
        )
        lines: list[str] = [header]

        for participant in self.participants:
            name = str(participant.get('name', 'Character')).strip() or 'Character'
            # Built-in/discover characters carry the original card dict under
            # 'raw'. User-created characters are stored flat, so fall back to
            # the participant dict itself when 'raw' is missing or empty.
            raw_candidate = participant.get('raw')
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

            bits: list[str] = []

            # Age — accept either age_band or age, numeric or string.
            age_band = identity.get('age_band', identity.get('age', ''))
            age_text = str(age_band).strip()
            if age_text:
                bits.append(f'age: {age_text}')

            # Voice: tone / cadence / favored / avoid.
            tone = str(voice.get('tone', '') or '').strip()
            cadence = str(voice.get('cadence', '') or '').strip()
            if tone:
                bits.append(f'tone: {self._clean_fact_snippet(tone, limit=160)}')
            if cadence:
                bits.append(f'cadence: {self._clean_fact_snippet(cadence, limit=160)}')
            favored = _join(_as_list(voice.get('favored_patterns')))
            if favored:
                bits.append(f'favored phrases: {favored}')
            avoid = _join(_as_list(voice.get('avoid_patterns')))
            if avoid:
                bits.append(f'avoid: {avoid}')

            # Optional example dialogue — great signal for voice matching
            # on small local models. Clipped to avoid blowing the context.
            example_dialogue = str(raw.get('example_dialogue', '') or '').strip()
            if example_dialogue:
                snippet = self._clean_fact_snippet(example_dialogue, limit=320)
                if snippet:
                    bits.append(f'example phrasing: {snippet}')

            # Identity: core traits, values, fears.
            traits = _join(_as_list(identity.get('core_traits')))
            if traits:
                bits.append(f'core traits: {traits}')
            values = _join(_as_list(identity.get('values')))
            if values:
                bits.append(f'values: {values}')
            fears = _join(_as_list(identity.get('fears')))
            if fears:
                bits.append(f'fears: {fears}')

            # Goals — flatten short/mid/long term if present.
            goal_bits: list[str] = []
            for horizon_key, horizon_label in (
                ('short_term', 'short-term'),
                ('mid_term', 'mid-term'),
                ('long_term', 'long-term'),
            ):
                horizon_items = _as_list(goals.get(horizon_key))
                horizon_text = _join(horizon_items, limit=3)
                if horizon_text:
                    goal_bits.append(f'{horizon_label}: {horizon_text}')
            if goal_bits:
                bits.append('goals: ' + '; '.join(goal_bits))

            # Boundaries — hard are inviolable, soft are preferences.
            hard = _join(_as_list(boundaries.get('hard')))
            if hard:
                bits.append(f'hard limits (will not cross): {hard}')
            soft = _join(_as_list(boundaries.get('soft')))
            if soft:
                bits.append(f'soft preferences: {soft}')

            # Private truths — internal, not to be blurted out, but they
            # should colour reactions and subtext.
            private_truths = _join(_as_list(identity.get('private_truths')))
            if private_truths:
                bits.append(
                    f'private truths (known only to the character, not stated outright unless the scene truly earns it): {private_truths}'
                )

            if bits:
                lines.append(f'- {name}: ' + ' | '.join(bits))

        # If no participant contributed anything, drop the header so we
        # don't push an empty "Voice, values, and limits" section into
        # the prompt.
        if len(lines) <= 1:
            return []
        return lines

    @staticmethod
    def _character_identity_key(character: dict[str, Any]) -> str:
        character_id = str(character.get('id', '')).strip()
        if character_id:
            return f'id:{character_id}'
        name = str(character.get('name', '')).strip().lower()
        if name:
            return f'name:{name}'
        return 'unknown'

    def _sync_primary_character_from_participants(self) -> None:
        primary_key = self._character_identity_key(self.character)
        match = next((item for item in self.participants if self._character_identity_key(item) == primary_key), None)
        if match is not None:
            self.character = dict(match)

    def _should_update_character_memory(self, participant: dict[str, Any], *, text: str, role: str, speaker: str, mentioned_any: bool) -> bool:
        if role == 'system':
            return False
        participant_name = str(participant.get('name', '')).strip()
        if not participant_name:
            return False
        if role == 'assistant' and speaker.strip().casefold() == participant_name.casefold():
            return True
        if self._message_mentions_character(participant, text):
            return True
        primary_key = self._character_identity_key(self.character)
        participant_key = self._character_identity_key(participant)
        if participant_key == primary_key and role == 'user' and (len(self.participants) == 1 or not mentioned_any):
            return True
        return False

    def _record_memory_development(self, text: str, *, role: str, speaker: str = '') -> None:
        cleaned = str(text or '').strip()
        if not cleaned:
            return
        mentioned_any = any(self._message_mentions_character(participant, cleaned) for participant in self.participants)
        refreshed: list[dict[str, Any]] = []
        for participant in self.participants:
            if self._should_update_character_memory(participant, text=cleaned, role=role, speaker=speaker, mentioned_any=mentioned_any):
                refreshed.append(apply_message_to_character_memory(
                    participant,
                    text=cleaned,
                    role=role,
                    speaker=speaker,
                    user_name=self.user_display_name,
                ))
            else:
                refreshed.append(dict(participant))
        self.participants = self._normalize_participants(refreshed)
        self._sync_primary_character_from_participants()
        self._refresh_sidebar_cards()

    @staticmethod
    def _normalize_inline_timestamps(text: str) -> str:
        prepared = str(text or '').replace('\r\n', '\n').replace('\xa0', ' ')
        return INLINE_TIMESTAMP_RE.sub(r'\n\1', prepared)

    def _role_and_speaker_from_header(self, speaker_text: str) -> tuple[str, str, str]:
        speaker = str(speaker_text or '').strip().strip("\"'")
        lowered = speaker.casefold()
        if lowered == 'scene':
            return 'scene', 'Scene', 'scenario'
        if lowered == 'system':
            return 'system', 'System', ''
        if lowered == str(self.user_display_name).strip().casefold():
            return 'user', self.user_display_name, ''
        return 'assistant', speaker or str(self.character.get('name', 'Character')), ''

    def _split_embedded_transcript_entries(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        base = dict(message)
        content = self._normalize_inline_timestamps(str(base.get('content', '')))
        matches = list(TIMESTAMP_HEADER_RE.finditer(content))
        if not matches:
            base['content'] = content
            return [base]

        role = str(base.get('role', '')).strip() or 'assistant'
        speaker = str(base.get('speaker', '')).strip()
        message_format = str(base.get('format', '')).strip()
        entries: list[dict[str, Any]] = []

        def append_entry(entry_role: str, entry_speaker: str, entry_content: str, entry_format: str = '') -> None:
            cleaned_content = str(entry_content or '').strip()
            if not cleaned_content:
                return
            entry = dict(base)
            entry['role'] = entry_role
            entry['speaker'] = entry_speaker
            entry['content'] = cleaned_content
            if entry_format:
                entry['format'] = entry_format
            else:
                entry.pop('format', None)
            entries.append(entry)

        leading = content[:matches[0].start()].strip()
        parsed_blocks: list[tuple[str, str, str, str]] = []
        for index, match in enumerate(matches):
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            block_text = content[match.end():next_start].strip()
            parsed_role, parsed_speaker, parsed_format = self._role_and_speaker_from_header(match.group(2))
            parsed_blocks.append((parsed_role, parsed_speaker, block_text, parsed_format))

        if role == 'assistant':
            assistant_blocks = [item for item in parsed_blocks if item[0] == 'assistant']
            if assistant_blocks:
                for parsed_role, parsed_speaker, block_text, parsed_format in assistant_blocks:
                    append_entry(parsed_role, parsed_speaker, block_text, parsed_format)
                return entries or [base]
            append_entry(role, speaker or str(self.character.get('name', 'Character')), leading, message_format)
            return entries or [base]

        if role == 'scene':
            append_entry('scene', 'Scene', leading, 'scenario')
            for parsed_role, parsed_speaker, block_text, parsed_format in parsed_blocks:
                if parsed_role == 'assistant':
                    append_entry(parsed_role, parsed_speaker, block_text, parsed_format)
                elif parsed_role == 'scene':
                    append_entry(parsed_role, parsed_speaker, block_text, parsed_format)
            return entries or [base]

        append_entry(
            role,
            speaker or (self.user_display_name if role == 'user' else str(self.character.get('name', 'Character'))),
            leading,
            message_format,
        )
        return entries or [base]

    def _normalize_message_sequence(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        previous_key: tuple[str, str, str, str] | None = None
        for message in messages:
            if not isinstance(message, dict):
                continue
            for entry in self._split_embedded_transcript_entries(message):
                role = str(entry.get('role', '')).strip() or 'assistant'
                speaker = str(entry.get('speaker', '')).strip()
                message_format = str(entry.get('format', '')).strip()
                if role == 'system':
                    cleaned_content = str(entry.get('content', '')).strip()
                else:
                    cleaned_content = self._sanitize_display_text(
                        str(entry.get('content', '')),
                        speaker=speaker,
                        role=role,
                        message_format=message_format,
                    )
                if not cleaned_content:
                    continue
                normalized_entry = dict(entry)
                normalized_entry['content'] = cleaned_content
                if not speaker:
                    if role == 'user':
                        normalized_entry['speaker'] = self.user_display_name
                    elif role == 'scene':
                        normalized_entry['speaker'] = 'Scene'
                    else:
                        normalized_entry['speaker'] = str(self.character.get('name', 'Character'))
                key = (
                    str(normalized_entry.get('role', '')).strip(),
                    str(normalized_entry.get('speaker', '')).strip(),
                    str(normalized_entry.get('format', '')).strip(),
                    cleaned_content,
                )
                if key == previous_key:
                    continue
                normalized.append(normalized_entry)
                previous_key = key
        return normalized

    def _latest_user_message_text(self) -> str:
        for message in reversed(self.messages):
            if str(message.get('role', '')).strip() == 'user':
                return str(message.get('content', '')).strip()
        return ''

    def _recent_exchange_text(self, limit: int = 4) -> str:
        recent: list[str] = []
        for message in self._context_messages_without_system()[-limit:]:
            role = str(message.get('role', '')).strip()
            speaker = str(message.get('speaker', '')).strip()
            if not speaker:
                speaker = self.user_display_name if role == 'user' else str(self.character.get('name', 'Character'))
            content = self._clip_text(str(message.get('content', '')).strip(), 220)
            if content:
                recent.append(f'{speaker}: {content}')
        return ' | '.join(recent)

    def _character_state_text(self) -> str:
        lines: list[str] = []
        for participant in self.participants[:3]:
            lines.extend(build_memory_prompt_lines(participant, max_stable=1, max_episodic=2, max_threads=1))
        return '\n'.join(lines[:8])

    def _retrieval_augmented_lines(self) -> list[str]:
        if self.chat_session is None:
            return []
        query = self._latest_user_message_text() or self._recent_exchange_text(limit=2)
        if not query:
            return []
        participant_ids = [str(item.get('id', '')).strip() or str(item.get('name', '')).strip().lower() for item in self.participants]
        results = self.memory_store.search(
            chat_id=str(self.chat_session.get('id', '')).strip(),
            query=query,
            participant_ids=participant_ids,
            limit=5,
        )
        if not results:
            return []
        lines = ['Retrieved supporting context from the local memory store. Prefer these details when they are relevant:']
        for item in results:
            label = item.speaker or item.source_type
            lines.append(f"- [{item.source_type}] {label}: {self._clip_text(item.content, 220)}")
        return lines

    def _build_system_prompt(self) -> str:
        assets = self.prompt_loader.load_for_character(self.character)
        base_prompt = self._personalize_text(str(self.character.get('system_prompt', '')).strip())
        character_name = str(self.character.get('name', 'The character')).strip() or 'The character'
        identity_line = (
            f"The user's preferred name is {self.user_display_name}. Address them by that name when it feels natural."
        )
        narration_line = (
            f"Write all actions, narration, and scene description in third person using '{character_name}' "
            'or the appropriate third-person name form, never first person.'
        )
        natural_flow_line = (
            'Keep the output natural and in-scene. Do not add meta lines, separator lines, or stage directions for the UI.'
        )
        speaker_label_line = (
            'The UI already shows the speaker name. In narration, do not keep repeating the full character name at the '
            'start of every paragraph when a natural pronoun or shorter phrasing would read better.'
        )
        no_meta_line = (
            'Never ask the user how to proceed, and never add numbered fragments, timestamps, or speaker labels inside the reply body.'
        )
        no_reasoning_leak_line = (
            'Never expose internal reasoning, numbered observations, choice lists, ranked alternatives, or incomplete sentence fragments. '
            'Output only the final in-world narration and dialogue.'
        )
        continuity_line = (
            'Before every reply, silently review the canonical participant facts below. Do not contradict them, do not '
            'replace established relationships, and do not invent a new roommate, best friend, partner, or companion when '
            'the character files already identify one.'
        )
        thought_style_line = (
            'When a character has a private thought, wrap only the thought text in single asterisks so the UI can render it in italics. '
            'Do not use markdown bold anywhere in replies.'
        )
        ending_line = (
            'End naturally on dialogue, action, or atmosphere. Do not append setup instructions, binary choice prompts, '
            'or a prompt for the next turn.'
        )
        no_choice_prompt_line = (
            'Do not end the reply with option prompts or suggested next moves. Let the scene stand on its own.'
        )
        no_echo_line = (
            'Do not repeat, paraphrase, or restart the opening greeting or scene intro on later turns. '
            'The scene has already begun; each reply must advance what just happened.'
        )

        scene_lines = [
            'This is an unfolding story scene, not an isolated single-message answer.',
            f'Current focal character: {character_name}.',
            "Do not decide the user's actions, dialogue, feelings, or internal thoughts for them."
        ]
        story_location = self._story_location_text()
        if story_location:
            scene_lines.append(
                f'The default story location for this chat is {story_location}. Keep environmental details broadly consistent with that location unless the user clearly moves the scene somewhere else.'
            )
        starting_scenario = self._personalize_text(str(self.character.get('starting_scenario', '')).strip())
        # Only embed the opening scenario in the system prompt when it is NOT already
        # present as a 'scene' message in the conversation history. Otherwise the
        # greeting/scenario gets fed to the model twice (once here, once as an
        # assistant/scene turn) and small local models will echo it verbatim on
        # later turns.
        scenario_in_history = any(
            str(m.get('role', '')).strip() == 'scene'
            and str(m.get('format', '')).strip() == 'scenario'
            for m in self.messages
            if isinstance(m, dict)
        )
        if starting_scenario and not scenario_in_history:
            scene_lines.append(f'Opening scene context: {starting_scenario}')
        if len(self.participants) > 1:
            scene_lines.append(
                'Other scene participants are present. Keep them consistent with the profile details below.'
            )
            scene_lines.append(
                'If it helps continuity, you may mention their visible actions or dialogue, but do not invent extra named participants.'
            )
        if self.rolling_summary:
            scene_lines.append('Earlier conversation summary:')
            scene_lines.append(self.rolling_summary)

        rendered_scene_template = self.prompt_loader.render_scene_template(
            assets.scene_template,
            scene_summary=self.rolling_summary or starting_scenario or 'Scene just started.',
            character_state=self._character_state_text(),
            recent_exchange=self._recent_exchange_text(),
            user_message=self._latest_user_message_text(),
        )
        if rendered_scene_template:
            scene_lines.append('Rendered scene template context:')
            scene_lines.append(rendered_scene_template)

        participant_lines = ['Scene participants:']
        for participant in self.participants:
            name = str(participant.get('name', 'Character')).strip() or 'Character'
            summary_bits: list[str] = []
            title = str(participant.get('title', '')).strip()
            description = str(participant.get('description', '')).strip()
            lore = str(participant.get('world_lore_notes', '')).strip().replace('\n', ' ')
            if title:
                summary_bits.append(title)
            if description:
                summary_bits.append(description)
            if lore:
                summary_bits.append(lore[:260])
            summary_text = ' | '.join(bit for bit in summary_bits if bit)
            participant_lines.append(f'- {name}: {summary_text or "No extra details established yet."}')

        canon_lines = self._participant_canon_lines()
        memory_lines = self._participant_memory_lines()
        voice_lines = self._participant_voice_lines()
        retrieval_lines = self._retrieval_augmented_lines()
        scene_state_lines = self.scene_state_machine.prompt_lines()

        parts = [part for part in [base_prompt, assets.system_rules, assets.output_format, assets.character_rules, identity_line, narration_line, natural_flow_line, speaker_label_line, no_meta_line, no_reasoning_leak_line, continuity_line, thought_style_line, ending_line, no_choice_prompt_line, no_echo_line] if part]
        parts.append('\n'.join(scene_lines))
        parts.append('\n'.join(scene_state_lines))
        parts.append('\n'.join(participant_lines))
        parts.append('\n'.join(canon_lines))
        if voice_lines:
            parts.append('\n'.join(voice_lines))
        parts.append('\n'.join(memory_lines))
        if retrieval_lines:
            parts.append('\n'.join(retrieval_lines))
        return '\n\n'.join(parts)

    def _ensure_starting_scenario_message(self) -> None:
        starting_scenario = self._personalize_text(str(self.character.get('starting_scenario', '')).strip())
        if not starting_scenario:
            return
        for message in self.messages:
            if str(message.get('role', '')).strip() == 'scene' and str(message.get('format', '')).strip() == 'scenario':
                return
        insert_index = 1 if self.messages and str(self.messages[0].get('role', '')).strip() == 'system' else 0
        self.messages.insert(insert_index, {
            'role': 'scene',
            'content': starting_scenario,
            'speaker': 'Scene',
            'format': 'scenario',
            'timestamp': datetime.now().replace(microsecond=0).isoformat(),
        })

    def _ensure_system_prompt_message(self, force_insert: bool = False) -> None:
        prompt = self._build_system_prompt()
        if self.messages and self.messages[0].get('role') == 'system' and not force_insert:
            self.messages[0]['content'] = prompt
            return
        if self.messages and self.messages[0].get('role') == 'system':
            self.messages.pop(0)
        self.messages.insert(0, {'role': 'system', 'content': prompt})

    def _load_or_initialize_chat(self) -> None:
        if self.chat_session is None:
            self.chat_session = self.chat_storage.create_chat_session(
                character=dict(self.character),
                model_entry=self.model_entry,
                generation_settings=self.generation_settings,
                user_name=self.user_display_name,
            )

        self.chat_session['user_name'] = self.user_display_name
        self.story_location_city = str(self.chat_session.get('story_location_city', self.story_location_city) or '').strip()
        self.story_location_country = str(self.chat_session.get('story_location_country', self.story_location_country) or '').strip()
        self.character = dict(self.chat_session.get('character', self.character))
        self.participants = self._normalize_participants(self.chat_session.get('participants', [self.character]))
        self.setWindowTitle(self.chat_session.get('title', f"Chat with {self.character.get('name', 'Character')}"))

        self.rolling_summary = str(self.chat_session.get('rolling_summary', '') or '').strip()
        self.rolling_summary_message_count = max(0, int(self.chat_session.get('rolling_summary_message_count', 0) or 0))
        self.scene_state_machine = SceneStateMachine(self.chat_session.get('scene_state'), default_location=self._story_location_text())
        self.scene_state_machine.set_participants(self.participants)
        self.memory_store.upsert_character_context(str(self.chat_session.get('id', '')).strip(), self.participants)

        stored_messages = list(self.chat_session.get('messages', []))
        if stored_messages:
            self.messages = self._normalize_message_sequence([dict(message) for message in stored_messages if isinstance(message, dict)])
            self._ensure_starting_scenario_message()
            self._update_rolling_summary()
            self._ensure_system_prompt_message()
            self.messages = self._normalize_message_sequence(self.messages)
            self._render_existing_transcript(self.messages)
            for message in self.messages:
                role = str(message.get('role', '')).strip()
                if role == 'system':
                    continue
                speaker = str(message.get('speaker', '')).strip() or (self.user_display_name if role == 'user' else str(self.character.get('name', 'Character')))
                self.scene_state_machine.apply_message(text=str(message.get('content', '')).strip(), role=role, speaker=speaker)
                self.memory_store.add_message_memory(
                    chat_id=str(self.chat_session.get('id', '')).strip() if isinstance(self.chat_session, dict) else '',
                    participants=self.participants,
                    role=role,
                    speaker=speaker,
                    content=str(message.get('content', '')).strip(),
                )
            self._persist_current_messages()
            return

        self._ensure_system_prompt_message(force_insert=True)
        init_timestamp = datetime.now().replace(microsecond=0).isoformat()
        starting_scenario = self._personalize_text(str(self.character.get('starting_scenario', '')).strip())
        if starting_scenario:
            self.messages.append({
                'role': 'scene',
                'content': starting_scenario,
                'speaker': 'Scene',
                'format': 'scenario',
                'timestamp': init_timestamp,
            })
        greeting = self._personalize_text(str(self.character.get('greeting', '')).strip())
        if greeting:
            self.messages.append({
                'role': 'assistant',
                'content': greeting,
                'speaker': self.character.get('name', 'Character'),
                'timestamp': init_timestamp,
            })
        self._persist_current_messages()
        if starting_scenario:
            self._append_message(
                'Scene',
                starting_scenario,
                message_format='scenario',
                role='scene',
                timestamp=init_timestamp,
            )
        if greeting:
            self._append_message(
                str(self.character.get('name', 'Character')),
                greeting,
                role='assistant',
                timestamp=init_timestamp,
            )

    def _clear_sidebar_cards(self) -> None:
        if self.sidebar_cards_layout is None:
            return
        while self.sidebar_cards_layout.count():
            item = self.sidebar_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_sidebar_cards(self) -> None:
        self._clear_sidebar_cards()
        if self.sidebar_cards_layout is None:
            return

        for participant in self.participants:
            card = CharacterInfoCard()
            card.set_character(participant)
            self.sidebar_cards_layout.addWidget(card)

        self.sidebar_cards_layout.addStretch(1)

        if self.chat_title_label is not None:
            self.chat_title_label.setText(self._chat_title_text())

    def _render_existing_transcript(self, stored_messages: list[dict[str, Any]]) -> None:
        if self.transcript is None:
            return
        self.transcript.clear()
        for message in stored_messages:
            role = str(message.get('role', 'user'))
            if role == 'system':
                continue
            content = str(message.get('content', ''))
            speaker = str(message.get('speaker', '')).strip()
            if not speaker:
                if role == 'user':
                    speaker = self.user_display_name
                elif role == 'scene':
                    speaker = 'Scene'
                else:
                    speaker = str(self.character.get('name', 'Character'))
            self._append_message(
                speaker,
                content,
                message_format=str(message.get('format', '')).strip(),
                role=role,
                timestamp=str(message.get('timestamp', '')).strip(),
            )

    def _persist_current_messages(self) -> None:
        if self.chat_session is None:
            return
        self.messages = self._normalize_message_sequence(self.messages)
        self._update_rolling_summary()
        self._ensure_system_prompt_message()
        self.chat_session['messages'] = [dict(message) for message in self.messages]
        self.chat_session['generation_settings'] = dict(self.generation_settings)
        self.chat_session['user_name'] = self.user_display_name
        self.chat_session['model'] = dict(self.model_entry)
        self.chat_session['character'] = dict(self.character)
        self.chat_session['participants'] = [dict(item) for item in self.participants]
        self.chat_session['story_location_city'] = self.story_location_city
        self.chat_session['story_location_country'] = self.story_location_country
        self.chat_session['story_mode'] = 'group' if len(self.participants) > 1 else 'single'
        self.chat_session['rolling_summary'] = self.rolling_summary
        self.chat_session['rolling_summary_message_count'] = self.rolling_summary_message_count
        self.chat_session['scene_state'] = self.scene_state_machine.snapshot()
        self.memory_store.upsert_character_context(str(self.chat_session.get('id', '')).strip(), self.participants)
        self.chat_session = self.chat_storage.save_chat(self.chat_session)
        self.character = dict(self.chat_session.get('character', self.character))
        self.participants = self._normalize_participants(self.chat_session.get('participants', [self.character]))
        self.setWindowTitle(self.chat_session.get('title', self.windowTitle()))
        self._refresh_sidebar_cards()

    def _context_tail_message_count(self) -> int:
        context_size = max(1024, int(self.generation_settings.get('context_size', 4096) or 4096))
        scaled = context_size // 512
        return max(CONTEXT_MESSAGE_TAIL_MIN, min(CONTEXT_MESSAGE_TAIL_MAX, scaled + 2))

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        cleaned = str(text or '').strip()
        if not cleaned:
            return 0
        word_estimate = len(re.findall(r'\S+', cleaned))
        char_estimate = max(1, len(cleaned) // 4)
        return max(word_estimate, char_estimate)

    def _estimate_message_tokens(self, message: dict[str, Any]) -> int:
        role = str(message.get('role', '')).strip()
        content = str(message.get('content', '')).strip()
        return 4 + self._estimate_text_tokens(role) + self._estimate_text_tokens(content)

    def _count_request_tokens(self, messages: list[dict[str, str]]) -> int:
        return self.chat_engine.count_message_tokens(
            model_entry=self.model_entry,
            messages=messages,
            n_ctx=int(self.generation_settings.get('context_size', 4096)),
            n_threads=int(self.generation_settings.get('threads', 4)),
            n_gpu_layers=int(self.generation_settings.get('n_gpu_layers', 0)),
        )

    def _context_prompt_budget(self) -> int:
        context_size = max(1024, int(self.generation_settings.get('context_size', 4096) or 4096))
        reply_budget = max(MIN_REPLY_MAX_TOKENS, int(self.generation_settings.get('max_tokens', 512) or 512))
        budget = context_size - reply_budget - CONTEXT_PROMPT_SAFETY_TOKENS
        return max(512, budget)

    def _context_messages_without_system(self) -> list[dict[str, Any]]:
        return [
            dict(message)
            for message in self.messages
            if isinstance(message, dict) and str(message.get('role', '')).strip() != 'system'
        ]

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        return re.sub(r'\s+', ' ', str(text or '')).strip()

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        cleaned = str(text or '').strip()
        if len(cleaned) <= limit:
            return cleaned
        clipped = cleaned[: max(0, limit - 1)].rstrip(' ,;:-')
        return f'{clipped}…' if clipped else cleaned[:limit]

    def _summarize_message_for_context(self, message: dict[str, Any]) -> str:
        role = str(message.get('role', '')).strip().lower()
        speaker = str(message.get('speaker', '')).strip()
        if not speaker:
            if role == 'user':
                speaker = self.user_display_name
            elif role == 'scene':
                speaker = 'Scene'
            else:
                speaker = str(self.character.get('name', 'Character')).strip() or 'Character'
        cleaned = self._sanitize_display_text(
            str(message.get('content', '')),
            speaker=speaker,
            role=role,
            message_format=str(message.get('format', '')).strip(),
        )
        flattened = self._collapse_whitespace(cleaned)
        if not flattened:
            return ''
        flattened = self._clip_text(flattened, CONTEXT_SUMMARY_LINE_CHARS)
        if role == 'scene':
            prefix = 'Scene'
        elif role == 'user':
            prefix = speaker or 'User'
        else:
            prefix = speaker or 'Assistant'
        return f'- {prefix}: {flattened}'

    def _compress_summary_lines(self, lines: list[str]) -> str:
        compact = [str(line).strip() for line in lines if str(line).strip()]
        if not compact:
            return ''
        if len(compact) <= CONTEXT_SUMMARY_MAX_LINES:
            return '\n'.join(compact)
        preserved_tail = compact[-(CONTEXT_SUMMARY_MAX_LINES - 1):]
        earlier = ' '.join(line[2:] if line.startswith('- ') else line for line in compact[: -(CONTEXT_SUMMARY_MAX_LINES - 1)])
        earlier = self._clip_text(self._collapse_whitespace(earlier), CONTEXT_SUMMARY_FUSED_CHARS)
        fused = f'- Earlier in the chat: {earlier}' if earlier else '- Earlier in the chat: continuity established.'
        return '\n'.join([fused, *preserved_tail])

    def _extend_rolling_summary_to(self, target_count: int) -> None:
        conversation = self._context_messages_without_system()
        bounded_target = max(0, min(int(target_count), len(conversation)))
        current_count = max(0, min(self.rolling_summary_message_count, len(conversation)))
        if bounded_target <= current_count:
            return

        summary_lines = [line for line in self.rolling_summary.splitlines() if line.strip()]
        new_lines: list[str] = []
        for message in conversation[current_count:bounded_target]:
            line = self._summarize_message_for_context(message)
            if line:
                new_lines.append(line)
        if new_lines:
            self.rolling_summary = self._compress_summary_lines([*summary_lines, *new_lines])
        self.rolling_summary_message_count = bounded_target

    def _update_rolling_summary(self) -> None:
        conversation = self._context_messages_without_system()
        tail_count = self._context_tail_message_count()
        cutoff = max(0, len(conversation) - tail_count)
        before = self.rolling_summary_message_count
        self._extend_rolling_summary_to(cutoff)
        if self.rolling_summary_message_count != before:
            logger.debug(
                'Updated rolling summary for chat %s: summarized=%s retained_recent=%s',
                str(self.chat_session.get('id', '')) if isinstance(self.chat_session, dict) else '',
                self.rolling_summary_message_count,
                len(conversation) - self.rolling_summary_message_count,
            )

    def _select_recent_messages_with_budget(
        self,
        conversation: list[dict[str, str]],
        system_message: dict[str, str],
    ) -> tuple[list[dict[str, str]], int, int]:
        budget = self._context_prompt_budget()
        selected: list[dict[str, str]] = []
        used = self._count_request_tokens([system_message])

        if used > budget:
            logger.warning(
                'System prompt alone exceeds the request budget for chat %s: prompt_tokens=%s budget=%s',
                str(self.chat_session.get('id', '')) if isinstance(self.chat_session, dict) else '',
                used,
                budget,
            )
            return [], used, budget

        for message in reversed(conversation):
            candidate = [system_message, message, *selected]
            candidate_tokens = self._count_request_tokens(candidate)
            if candidate_tokens > budget:
                break
            selected.insert(0, message)
            used = candidate_tokens

        return selected, used, budget

    def _build_request_messages(self) -> list[dict[str, str]]:
        self._update_rolling_summary()

        conversation: list[dict[str, str]] = []
        for message in self._context_messages_without_system():
            role = str(message.get('role', '')).strip().lower()
            if role not in {'user', 'assistant'}:
                continue
            content = str(message.get('content', '')).strip()
            if not content:
                continue
            conversation.append({'role': role, 'content': content})

        selected: list[dict[str, str]] = []
        used = 0
        budget = self._context_prompt_budget()
        for _ in range(3):
            self._ensure_system_prompt_message()
            system_message = dict(self.messages[0]) if self.messages and str(self.messages[0].get('role', '')).strip() == 'system' else {
                'role': 'system',
                'content': self._build_system_prompt(),
            }
            selected, used, budget = self._select_recent_messages_with_budget(conversation, system_message)
            omitted_count = max(0, len(conversation) - len(selected))
            if omitted_count <= self.rolling_summary_message_count:
                request_messages = [system_message, *selected]
                logger.debug(
                    'Built request context for chat %s: total_messages=%s selected_messages=%s summarized_messages=%s estimated_prompt_tokens=%s budget=%s',
                    str(self.chat_session.get('id', '')) if isinstance(self.chat_session, dict) else '',
                    len(conversation),
                    len(selected),
                    self.rolling_summary_message_count,
                    used,
                    budget,
                )
                return request_messages
            self._extend_rolling_summary_to(omitted_count)

        self._ensure_system_prompt_message()
        system_message = dict(self.messages[0]) if self.messages and str(self.messages[0].get('role', '')).strip() == 'system' else {
            'role': 'system',
            'content': self._build_system_prompt(),
        }
        selected, used, budget = self._select_recent_messages_with_budget(conversation, system_message)
        request_messages = [system_message, *selected]
        logger.debug(
            'Built request context for chat %s after capped passes: total_messages=%s selected_messages=%s summarized_messages=%s estimated_prompt_tokens=%s budget=%s',
            str(self.chat_session.get('id', '')) if isinstance(self.chat_session, dict) else '',
            len(conversation),
            len(selected),
            self.rolling_summary_message_count,
            used,
            budget,
        )
        return request_messages

    @staticmethod
    def _strip_trailing_choice_prompt(text: str) -> str:
        cleaned = str(text or '').strip()
        if not cleaned:
            return cleaned

        prompt_pattern = re.compile(
            r'(?:\n\s*\n|^)(?P<line>(?:Do you want to|Would you like to|Do you wanna|Or maybe)\b[^\n!?]*'
            r'(?:\?|instead\?))\s*$',
            flags=re.IGNORECASE,
        )
        while True:
            match = prompt_pattern.search(cleaned)
            if match is None:
                break
            line = match.group('line').strip()
            if ' or ' not in line.lower() and not line.lower().startswith('or maybe'):
                break
            cleaned = cleaned[:match.start()].rstrip()
        return cleaned

    @staticmethod
    def _remove_standalone_artifact_lines(text: str) -> str:
        cleaned = str(text or '')
        cleaned = re.sub(r'(?m)^\s*[.]{1,3}\s*$', '', cleaned)
        cleaned = re.sub(r'(?m)^\s*[.…]{2,}\s*$', '', cleaned)
        cleaned = re.sub(r'(?m)^\s*[-•*]+\s*$', '', cleaned)
        while '\n\n\n' in cleaned:
            cleaned = cleaned.replace('\n\n\n', '\n\n')
        return cleaned.strip()

    @staticmethod
    def _looks_like_numbered_artifact_line(text: str) -> bool:
        stripped = str(text or '').strip()
        if not stripped:
            return False
        if re.fullmatch(r'(?:\d{1,3}[.,:]?\s*){3,}', stripped):
            return True
        if re.fullmatch(r'(?:\d{1,3}[.,:]?\s+[A-Za-z][^\n]{0,40}\s*){3,}', stripped):
            return True
        return False

    @staticmethod
    def _strip_inline_numbered_artifacts(text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in str(text or '').splitlines():
            line = raw_line.rstrip()
            if ChatWindow._looks_like_numbered_artifact_line(line):
                continue

            matches = list(re.finditer(r'(?<!\w)(?:\(?\d{1,2}\)?[.,:])(?=\s+[A-Z])', line))
            if len(matches) >= 2:
                line = line[:matches[0].start()].rstrip()

            line = re.sub(r'\s+(?:\(?\d{1,2}\)?[.,:])(?:\s+\(?\d{1,2}\)?[.,:])+\s*$', '', line)
            line = re.sub(r'(?<!\w)(?:\(?\d{1,2}\)?[.,:])\s*(?=\(?\d{1,2}\)?[.,:])', '', line)

            if ChatWindow._looks_like_numbered_artifact_line(line):
                continue
            if line.strip():
                cleaned_lines.append(line)

        cleaned = '\n'.join(cleaned_lines)
        cleaned = re.sub(r'(?m)^\s*\(?\d{1,2}\)?[.,:]\s*$', '', cleaned)
        while '\n\n\n' in cleaned:
            cleaned = cleaned.replace('\n\n\n', '\n\n')
        return cleaned.strip()

    def _sanitize_display_text(self, text: str, *, speaker: str = '', role: str = '', message_format: str = '') -> str:
        cleaned = self._normalize_inline_timestamps(text)
        cleaned = re.sub(r'[ \t]+\n', '\n', cleaned)
        cleaned = cleaned.strip()
        if role != 'user':
            cleaned = re.sub(r'(?:^|\n)\s*[-*_]{3,}\s*(?=\n|$)', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'(?:^|\n)\s*continue the scene\.?\s*$', '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
            cleaned = re.sub(
                r'(?:^|\n)+\s*(?:to proceed\b|please tell\b|tell (?:maya|her|him|them)\b|how do you respond\b|what do you do next\b).*$',
                '',
                cleaned,
                flags=re.IGNORECASE | re.DOTALL,
            )
            cleaned = re.sub(r'(?:^|\n)\s*no system prompting\s*(?=\n|$)', '\n', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'(?:^|\n)\s*\[[0-9]{1,2}:[0-9]{2}\]\s*(?:scene|system)\b[^\n]*(?=\n|$)', '\n', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'(?<=\S)\s+[0-9]{1,2}\s*$', '', cleaned)
            cleaned = re.sub(r'\n\s*[0-9]{1,2}\s*$', '', cleaned)
            cleaned = self._strip_inline_numbered_artifacts(cleaned)
            cleaned = self._strip_trailing_choice_prompt(cleaned)
            cleaned = self._remove_standalone_artifact_lines(cleaned)
            cleaned = self._strip_inline_numbered_artifacts(cleaned)
            if speaker:
                escaped_speaker = re.escape(str(speaker).strip())
                if escaped_speaker:
                    cleaned = re.sub(rf'^(?:{escaped_speaker}[:：]\s*)+', '', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(rf'(?:^|\n)\s*\[[0-9]{{1,2}}:[0-9]{{2}}\]\s*{escaped_speaker}\s*(?=\n|$)', '\n', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(rf"(?:^|\n)\s*{escaped_speaker}[’'\"]?\s*(?=\n|$)", '\n', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(rf'(?:^|\n)\s*{escaped_speaker}\s*[:：-]\s*', '\n', cleaned, flags=re.IGNORECASE)
            cleaned = cleaned.strip()
            cleaned = self._naturalize_leading_speaker_references(
                cleaned,
                speaker=speaker,
                role=role,
                message_format=message_format,
            )
        while '\n\n\n' in cleaned:
            cleaned = cleaned.replace('\n\n\n', '\n\n')
        return cleaned.strip()

    @staticmethod
    def _stable_palette_index(value: str, palette_size: int) -> int:
        normalized = str(value or '').strip().casefold()
        if not normalized or palette_size <= 0:
            return 0
        return sum(ord(char) for char in normalized) % palette_size

    def _speaker_character_color(self, speaker: str) -> str:
        normalized_speaker = str(speaker or '').strip()
        if not normalized_speaker:
            return ''

        primary_name = str(self.character.get('name', '')).strip()
        if primary_name and normalized_speaker.casefold() == primary_name.casefold():
            color = _safe_character_chat_color(
                self.character.get('name_color', self.character.get('name_colour', ''))
            )
            if color:
                return color

        for participant in self.participants:
            participant_name = str(participant.get('name', '')).strip()
            if not participant_name or participant_name.casefold() != normalized_speaker.casefold():
                continue
            color = _safe_character_chat_color(
                participant.get('name_color', participant.get('name_colour', ''))
            )
            if color:
                return color
        return ''

    def _speaker_color(self, speaker: str, role: str, message_format: str = '') -> str:
        normalized_role = str(role or '').strip().lower()
        normalized_speaker = str(speaker or '').strip()
        if message_format == 'scenario' or normalized_role == 'scene' or normalized_speaker.casefold() == 'scene':
            return '#ece7ff'
        if normalized_role == 'user':
            return '#f4f1ff'
        if normalized_role == 'system' or normalized_speaker.casefold() == 'system':
            return '#c4bedf'
        explicit_color = self._speaker_character_color(normalized_speaker)
        if explicit_color:
            return explicit_color
        palette_index = self._stable_palette_index(normalized_speaker, len(CHARACTER_COLOR_PALETTE))
        return CHARACTER_COLOR_PALETTE[palette_index]

    @staticmethod
    def _html_with_breaks(text: str) -> str:
        return html.escape(str(text or '')).replace('\n\n', '<br><br>').replace('\n', '<br>')

    def _render_inline_markup(self, text: str) -> str:
        escaped = self._html_with_breaks(text)

        def italic_replacement(match: re.Match[str]) -> str:
            inner = match.group(1).strip()
            if not inner:
                return match.group(0)
            return f'<i>{inner}</i>'

        escaped = re.sub(r'(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)', italic_replacement, escaped)
        escaped = re.sub(r'(?<!_)_(?!_)([^_\n]+?)(?<!_)_(?!_)', italic_replacement, escaped)
        return escaped

    def _render_scene_dialogue_markup(self, text: str, *, dialogue_color: str, scene_color: str = '#ffffff') -> str:
        content = str(text or '')
        if not content:
            return ''

        def dialogue_spans(value: str) -> list[tuple[int, int]]:
            spans: list[tuple[int, int]] = []
            opening_quotes = {'"', '“'}
            closing_quotes = {'"', '”'}
            index = 0
            length = len(value)

            while index < length:
                char = value[index]
                if char not in opening_quotes:
                    index += 1
                    continue

                start_index = index
                end_index = None
                scan = index + 1
                while scan < length:
                    if value[scan] in closing_quotes:
                        end_index = scan + 1
                        break
                    scan += 1

                if end_index is None:
                    spans.append((start_index, length))
                    break

                spans.append((start_index, end_index))
                index = end_index

            return spans

        parts: list[str] = []
        last_end = 0
        for start_index, end_index in dialogue_spans(content):
            if start_index > last_end:
                scene_text = content[last_end:start_index]
                if scene_text:
                    parts.append(f'<span style="color: {scene_color};">{self._html_with_breaks(scene_text)}</span>')
            dialogue_text = content[start_index:end_index]
            if dialogue_text:
                parts.append(f'<span style="color: {dialogue_color};">{self._html_with_breaks(dialogue_text)}</span>')
            last_end = end_index
        if last_end < len(content):
            tail = content[last_end:]
            if tail:
                parts.append(f'<span style="color: {scene_color};">{self._html_with_breaks(tail)}</span>')
        return ''.join(parts) or f'<span style="color: {scene_color};">{self._html_with_breaks(content)}</span>'

    def _render_assistant_story_markup(self, text: str, *, speaker_color: str, scene_color: str = '#ffffff') -> str:
        content = str(text or '')
        if not content:
            return ''

        # Split on inline [SpeakerName] markers so each segment can be coloured
        # with that speaker's name_color from their character JSON.
        # Pattern: [Name] at any position in the text (not timestamp headers).
        inline_speaker_re = re.compile(r'\[([^\]\d][^\]]*?)\]')

        # Build ordered list of (start, end, speaker_name) for each [Name] tag
        # that resolves to a known participant or 'Scene'.
        segments: list[tuple[int, int, str]] = []
        for m in inline_speaker_re.finditer(content):
            candidate = m.group(1).strip()
            if not candidate:
                continue
            # Resolve against known participants
            resolved = ''
            if candidate.casefold() == 'scene':
                resolved = 'Scene'
            else:
                for participant in self.participants:
                    pname = str(participant.get('name', '')).strip()
                    if pname and pname.casefold() == candidate.casefold():
                        resolved = pname
                        break
            if resolved:
                segments.append((m.start(), m.end(), resolved))

        if not segments:
            # No multi-speaker markers — render normally
            return self._render_single_speaker_markup(content, speaker_color=speaker_color, scene_color=scene_color)

        parts: list[str] = []
        pos = 0
        # Prepend any text before the first marker using the original speaker_color
        for i, (seg_start, seg_end, seg_speaker) in enumerate(segments):
            if seg_start > pos:
                chunk = content[pos:seg_start]
                if chunk.strip():
                    parts.append(self._render_single_speaker_markup(chunk, speaker_color=speaker_color, scene_color=scene_color))

            # Determine the end of this segment (start of next marker or end of string)
            next_start = segments[i + 1][0] if i + 1 < len(segments) else len(content)
            body = content[seg_end:next_start]

            # Pick the colour for this segment's speaker
            if seg_speaker == 'Scene':
                seg_color = scene_color
            else:
                seg_color = self._speaker_character_color(seg_speaker) or speaker_color

            if body.strip():
                parts.append(self._render_single_speaker_markup(body, speaker_color=seg_color, scene_color=scene_color))

            pos = next_start

        if pos < len(content):
            tail = content[pos:]
            if tail.strip():
                parts.append(self._render_single_speaker_markup(tail, speaker_color=speaker_color, scene_color=scene_color))

        return ''.join(part for part in parts if part)

    def _render_single_speaker_markup(self, text: str, *, speaker_color: str, scene_color: str = '#ffffff') -> str:
        """Render a single-speaker text block with italic thoughts and dialogue colouring."""
        content = str(text or '')
        if not content:
            return ''
        parts: list[str] = []
        last_end = 0
        thought_pattern = re.compile(r'(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)([^_\n]+?)(?<!_)_(?!_)')
        for match in thought_pattern.finditer(content):
            if match.start() > last_end:
                parts.append(
                    self._render_scene_dialogue_markup(
                        content[last_end:match.start()],
                        dialogue_color=speaker_color,
                        scene_color=scene_color,
                    )
                )
            thought_text = (match.group(1) or match.group(2) or '').strip()
            if thought_text:
                parts.append(
                    f'<span style="color: {scene_color};"><i>{self._html_with_breaks(thought_text)}</i></span>'
                )
            last_end = match.end()
        if last_end < len(content):
            parts.append(
                self._render_scene_dialogue_markup(
                    content[last_end:],
                    dialogue_color=speaker_color,
                    scene_color=scene_color,
                )
            )
        return ''.join(part for part in parts if part)

    def _streaming_block_html(self, speaker: str, text: str) -> str:
        if not text:
            return ''
        speaker_color = self._speaker_color(speaker, 'assistant', '')
        escaped_speaker = html.escape(str(speaker))
        sanitized_text = self._sanitize_display_text(text, speaker=speaker, role='assistant')
        rendered_text = self._render_assistant_story_markup(sanitized_text, speaker_color=speaker_color)
        return (
            f'<div style="margin: 0; opacity: 0.92;">'
            f'<div style="margin: 0 0 8px 0; line-height: 1.35; color: {speaker_color};">[typing] {escaped_speaker}</div>'
            f'<div style="margin: 0; line-height: 1.6;">{rendered_text}</div>'
            f'<div style="height: 16px;"></div>'
            f'</div>'
        )

    def _detect_partial_speaker(self, partial_text: str) -> str:
        """Detect which participant is speaking from a partial (streaming) reply.

        Checks for a timestamp header ``[HH:MM] Speaker Name`` on the first
        line, then falls back to the first inline ``[SpeakerName]`` marker that
        resolves to a known participant.  Returns the primary character's name
        when nothing is found so existing behaviour is preserved.
        """
        default = str(self.character.get('name', 'Character'))
        text = str(partial_text or '').lstrip()
        if not text:
            return default

        # 1. Timestamp-header format: [HH:MM] Speaker Name
        header_match = TIMESTAMP_HEADER_RE.match(text)
        if header_match:
            candidate = header_match.group(2).strip().strip("\"'")
            if candidate and candidate.casefold() not in {'scene', 'system'}:
                for participant in self.participants:
                    pname = str(participant.get('name', '')).strip()
                    if pname and pname.casefold() == candidate.casefold():
                        return pname
                # Not yet a known participant but name is plausible — use it so
                # the colour lookup can fall back to the palette.
                if candidate:
                    return candidate

        # 2. Inline marker format: [SpeakerName] anywhere in the text
        inline_re = re.compile(r'\[([^\]\d][^\]]*?)\]')
        for m in inline_re.finditer(text):
            candidate = m.group(1).strip()
            if not candidate or candidate.casefold() == 'scene':
                continue
            for participant in self.participants:
                pname = str(participant.get('name', '')).strip()
                if pname and pname.casefold() == candidate.casefold():
                    return pname

        return default

    @Slot(int, str)
    def _on_worker_partial(self, request_id: int, partial_text: str) -> None:
        if request_id != self._active_request_id or self.transcript is None:
            return
        self._streaming_preview_text = partial_text
        speaker = self._detect_partial_speaker(partial_text)
        self.transcript.setHtml(self._streaming_base_html + self._streaming_block_html(speaker, partial_text))
        scrollbar = self.transcript.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_streaming_preview(self) -> None:
        if self.transcript is not None and self._streaming_preview_text:
            self.transcript.setHtml(self._streaming_base_html)
            scrollbar = self.transcript.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        self._streaming_preview_text = ''
        self._streaming_base_html = self.transcript.toHtml() if self.transcript is not None else ''

    @staticmethod
    def _format_display_timestamp(raw: str) -> str:
        """Return an HH:MM label for a stored ISO timestamp, falling back to now."""
        text = str(raw or '').strip()
        if text:
            try:
                parsed = datetime.fromisoformat(text)
                return parsed.strftime('%H:%M')
            except ValueError:
                # Stored value isn't full ISO — accept an already-formatted HH:MM.
                match = re.match(r'^(\d{1,2}):(\d{2})$', text)
                if match:
                    return f'{int(match.group(1)):02d}:{match.group(2)}'
        return datetime.now().strftime('%H:%M')

    def _append_message(self, speaker: str, text: str, *, message_format: str = '', role: str = '', timestamp: str = '') -> None:
        timestamp = self._format_display_timestamp(timestamp)
        if self.transcript is not None:
            display_text = self._sanitize_display_text(text, speaker=speaker, role=role, message_format=message_format)
            if not display_text:
                return

            speaker_color = self._speaker_color(speaker, role, message_format)
            escaped_speaker = html.escape(str(speaker))
            if role == 'assistant' and message_format != 'scenario':
                rendered_text = self._render_assistant_story_markup(display_text, speaker_color=speaker_color)
                body_html = rendered_text
                spacer_height = '16px'
            else:
                rendered_text = self._render_inline_markup(display_text)
                if message_format == 'scenario':
                    body_html = f'<span style="font-weight: 700; color: #ffffff;">{rendered_text}</span>'
                    spacer_height = '20px'
                else:
                    body_html = f'<span style="color: {speaker_color};">{rendered_text}</span>'
                    spacer_height = '16px'

            block_html = (
                f'<div style="margin: 0;">'
                f'<div style="margin: 0 0 8px 0; line-height: 1.35; color: {speaker_color};">[{timestamp}] {escaped_speaker}</div>'
                f'<div style="margin: 0; line-height: 1.6;">{body_html}</div>'
                f'<div style="height: {spacer_height};"></div>'
                f'</div>'
            )

            cursor = self.transcript.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertHtml(block_html)
            self.transcript.setTextCursor(cursor)
            scrollbar = self.transcript.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _set_waiting_state(self, waiting: bool, message: str) -> None:
        if self.waiting_label is not None:
            self.waiting_label.setText(message)
            self.waiting_label.setVisible(waiting or bool(message))
        if self.waiting_bar is not None:
            self.waiting_bar.setVisible(waiting)
        if self.cancel_button is not None:
            self.cancel_button.setVisible(waiting)
        if self.send_button is not None:
            self.send_button.setEnabled(not waiting)
        if self.input_box is not None:
            self.input_box.setEnabled(not waiting)

    def _set_retry_state(self, enabled: bool, message: str) -> None:
        self._retry_available = enabled
        if self.retry_button is not None:
            self.retry_button.setVisible(enabled)
            self.retry_button.setEnabled(enabled)
        if self.error_label is not None:
            self.error_label.setText(message)
            self.error_label.setVisible(enabled and bool(message))

    def _strip_echoed_context(self, reply: str) -> str:
        """Remove any conversation-history echo the model appended to its reply.

        _recent_exchange_text() joins entries as 'Speaker: text | Speaker: text …'.
        Small local models sometimes reproduce this verbatim after their actual reply.
        We detect the first ' | Name:' or ' | Name:' pattern whose name matches a
        known participant or the user and truncate everything from that point.
        """
        text = str(reply or '')
        if ' | ' not in text:
            return text

        names: list[str] = [str(self.user_display_name or '').strip()]
        for participant in self.participants:
            name = str(participant.get('name', '')).strip()
            if name:
                names.append(name)

        for name in names:
            if not name:
                continue
            marker = f' | {name}:'
            idx = text.find(marker)
            if idx != -1:
                text = text[:idx].strip()
        return text

    def _response_stop_sequences(self) -> list[str]:
        base = [
            '\n---',
            '\nContinue the scene',
            '\nTo proceed',
            '\nPlease tell',
            '\nTell Maya',
            '\nTell her',
            '\nHow do you respond',
            '\nWhat do you do next',
            '\nNo system prompting',
        ]
        # Prevent the model echoing back the recent-exchange context block.
        # _recent_exchange_text() joins entries with " | Speaker:" so we add
        # a stop for every known participant name as well as the user name.
        user = str(self.user_display_name or '').strip()
        if user:
            base.append(f' | {user}:')
        for participant in self.participants:
            name = str(participant.get('name', '')).strip()
            if name:
                base.append(f' | {name}:')
        return base

    def _launch_generation(self, request_messages: list[dict[str, str]], *, retrying: bool = False) -> None:
        self._request_counter += 1
        request_id = self._request_counter
        self._active_request_id = request_id
        self._set_retry_state(False, '')
        self._set_waiting_state(True, 'Retrying last reply…' if retrying else 'Waiting for reply…')
        self._streaming_base_html = self.transcript.toHtml() if self.transcript is not None else ''
        self._streaming_preview_text = ''

        thread = QThread(self)
        worker = ChatWorker(
            request_id=request_id,
            chat_engine=self.chat_engine,
            model_entry=self.model_entry,
            messages=request_messages,
            generation_settings=dict(self.generation_settings),
            stop_sequences=self._response_stop_sequences(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_worker_finished)
        worker.partial.connect(self._on_worker_partial)
        worker.error.connect(self._on_worker_error)
        # Tell the thread to exit its event loop when the worker is done.
        # Cleanup happens on thread.finished so we never call .wait() on the thread
        # that is currently executing the slot.
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda rid=request_id: self._finalize_request_thread(rid))

        self._pending_threads[request_id] = thread
        self._pending_workers[request_id] = worker
        thread.start()

    def _name_in_text(self, name: str, text: str) -> bool:
        cleaned_name = str(name).strip()
        cleaned_text = str(text).strip()
        if not cleaned_name or not cleaned_text:
            return False
        return re.search(rf'(?<!\w){re.escape(cleaned_name)}(?!\w)', cleaned_text, flags=re.IGNORECASE) is not None

    def _message_mentions_character(self, character: dict[str, Any], text: str) -> bool:
        if self._name_in_text(str(character.get('name', '')), text):
            return True
        raw = character.get('raw') if isinstance(character.get('raw'), dict) else {}
        slug = str(character.get('slug', '') or raw.get('slug', '')).strip()
        if slug and self._name_in_text(slug.replace('_', ' '), text):
            return True
        return False

    def _load_template_payload(self) -> dict[str, Any]:
        template_path = get_data_dir() / 'template.json'
        fallback = {
            'id': '',
            'name': '{name}',
            'title': 'Story participant',
            'description': 'A character who emerged during the story.',
            'system_prompt': 'You are {name}. Stay consistent with details that emerge in the story.',
            'avatar_path': '',
            'greeting': '',
            'example_dialogue': '',
            'world_lore_notes': '',
            'tags': ['story-generated'],
            'folder': 'Story',
            'is_favorite': False,
        }
        if not template_path.exists():
            return fallback
        try:
            loaded = json.loads(template_path.read_text(encoding='utf-8'))
        except Exception as exc:
            logger.warning('Failed to load story character template from %s: %s', template_path, exc)
            return fallback
        if not isinstance(loaded, dict):
            return fallback
        data = deepcopy(fallback)
        data.update(loaded)
        return data

    def _replace_template_tokens(self, value: Any, name: str, introduction_text: str) -> Any:
        if isinstance(value, str):
            result = value
            replacements = {
                '{name}': name,
                '{{name}}': name,
                '[[name]]': name,
                '<<name>>': name,
                '{character_name}': name,
                '{{character_name}}': name,
                '[[character_name]]': name,
                '<<character_name>>': name,
                '{introduction_text}': introduction_text,
                '{{introduction_text}}': introduction_text,
                '[[introduction_text]]': introduction_text,
                '<<introduction_text>>': introduction_text,
            }
            for token, replacement in replacements.items():
                result = result.replace(token, replacement)
            return result
        if isinstance(value, list):
            return [self._replace_template_tokens(item, name, introduction_text) for item in value]
        if isinstance(value, dict):
            return {key: self._replace_template_tokens(item, name, introduction_text) for key, item in value.items()}
        return value

    def _create_story_character_from_template(self, name: str, introduction_text: str) -> dict[str, Any]:
        template = self._replace_template_tokens(self._load_template_payload(), name, introduction_text)
        generated_id = self._generate_story_character_id(name)
        return {
            'id': generated_id,
            'slug': generated_id.removeprefix('story_'),
            'name': str(template.get('name', name)).strip() or name,
            'title': str(template.get('title', '')).strip(),
            'description': str(template.get('description', '')).strip(),
            'system_prompt': str(template.get('system_prompt', '')).strip(),
            'avatar_path': str(template.get('avatar_path', '')).strip(),
            'greeting': str(template.get('greeting', '')).strip(),
            'example_dialogue': str(template.get('example_dialogue', '')).strip(),
            'world_lore_notes': str(template.get('world_lore_notes', '')).strip() or introduction_text.strip(),
            'tags': template.get('tags', ['story-generated']),
            'folder': str(template.get('folder', 'Story')).strip() or 'Story',
            'is_favorite': bool(template.get('is_favorite', False)),
            'source': 'story',
        }

    def _generate_story_character_id(self, name: str) -> str:
        slug = ''.join(ch.lower() if ch.isalnum() else '_' for ch in name).strip('_')
        slug = '_'.join(part for part in slug.split('_') if part) or 'character'
        candidate = f'story_{slug}'
        used = {str(item.get('id', '')).strip() for item in self.participants}
        counter = 2
        while candidate in used:
            candidate = f'story_{slug}_{counter}'
            counter += 1
        return candidate

    def _append_story_development(self, character: dict[str, Any], text: str) -> dict[str, Any]:
        if not text.strip():
            return character
        updated = dict(character)
        existing_notes = str(updated.get('world_lore_notes', '')).strip()
        addition = text.strip()
        if addition and addition not in existing_notes:
            updated['world_lore_notes'] = f'{existing_notes}\n{addition}'.strip()
        return updated

    def _maybe_add_scene_participants(self, user_text: str) -> list[dict[str, Any]]:
        added: list[dict[str, Any]] = []
        existing_keys = {
            (str(item.get('id', '')).strip() or str(item.get('name', '')).strip().lower())
            for item in self.participants
        }

        builtin_characters = self.character_manager.list_builtin_characters()

        for candidate in builtin_characters:
            candidate_id = str(candidate.get('id', '')).strip()
            key = candidate_id or str(candidate.get('name', '')).strip().lower()
            if not key or key in existing_keys:
                continue
            if self._message_mentions_character(candidate, user_text):
                self.participants.append(dict(candidate))
                existing_keys.add(key)
                added.append(dict(candidate))

        for match in INTRO_PATTERNS.findall(user_text):
            candidate_name = ' '.join(part for part in str(match).split() if part)
            if not candidate_name:
                continue
            if any(self._name_in_text(str(item.get('name', '')), candidate_name) for item in added):
                continue
            existing = next(
                (
                    item for item in self.participants
                    if str(item.get('name', '')).strip().lower() == candidate_name.lower()
                ),
                None,
            )
            if existing is not None:
                continue

            preset = next(
                (
                    item for item in builtin_characters
                    if str(item.get('name', '')).strip().lower() == candidate_name.lower()
                ),
                None,
            )
            if preset is not None:
                key = str(preset.get('id', '')).strip() or candidate_name.lower()
                if key not in existing_keys:
                    self.participants.append(dict(preset))
                    existing_keys.add(key)
                    added.append(dict(preset))
                continue

            story_character = self._create_story_character_from_template(candidate_name, user_text)
            key = str(story_character.get('id', '')).strip() or candidate_name.lower()
            if key not in existing_keys:
                self.participants.append(dict(story_character))
                existing_keys.add(key)
                added.append(dict(story_character))

        if added:
            self.scene_state_machine.register_joined_participants([str(item.get('name', '')).strip() for item in added])
            self._ensure_system_prompt_message()
            self._refresh_sidebar_cards()
        return added

    def _record_story_development(self, text: str) -> None:
        if not text.strip():
            return
        refreshed: list[dict[str, Any]] = []
        for participant in self.participants:
            participant_id = str(participant.get('id', '')).strip()
            if participant_id.startswith('story_') and self._message_mentions_character(participant, text):
                refreshed.append(self._append_story_development(participant, text))
            else:
                refreshed.append(dict(participant))
        self.participants = self._normalize_participants(refreshed)
        self._refresh_sidebar_cards()

    @Slot(int, str)
    def _on_worker_finished(self, request_id: int, reply: str) -> None:
        canceled = request_id in self._canceled_requests
        is_active = request_id == self._active_request_id
        if canceled or not is_active:
            return

        reply = self._strip_echoed_context(reply)
        assistant_entries = self._normalize_message_sequence([
            {
                'role': 'assistant',
                'content': reply,
                'speaker': str(self.character.get('name', 'Character')),
            }
        ])
        if not assistant_entries:
            fallback_reply = self._sanitize_display_text(
                reply,
                speaker=str(self.character.get('name', 'Character')),
                role='assistant',
            )
            if fallback_reply:
                assistant_entries = [{
                    'role': 'assistant',
                    'content': fallback_reply,
                    'speaker': str(self.character.get('name', 'Character')),
                }]

        self._clear_streaming_preview()
        reply_timestamp = datetime.now().replace(microsecond=0).isoformat()
        for entry in assistant_entries:
            clean_reply = str(entry.get('content', '')).strip()
            if not clean_reply:
                continue
            speaker = str(entry.get('speaker', self.character.get('name', 'Character'))).strip() or str(self.character.get('name', 'Character'))
            stored_entry = dict(entry)
            stored_entry.setdefault('timestamp', reply_timestamp)
            self.messages.append(stored_entry)
            self.scene_state_machine.apply_message(text=clean_reply, role=str(entry.get('role', 'assistant')).strip(), speaker=speaker)
            self.memory_store.add_message_memory(
                chat_id=str(self.chat_session.get('id', '')).strip() if isinstance(self.chat_session, dict) else '',
                participants=self.participants,
                role=str(entry.get('role', 'assistant')).strip(),
                speaker=speaker,
                content=clean_reply,
            )
            self._record_story_development(clean_reply)
            self._record_memory_development(clean_reply, role=str(entry.get('role', 'assistant')).strip(), speaker=speaker)
            self._append_message(
                speaker,
                clean_reply,
                role=str(entry.get('role', 'assistant')).strip(),
                message_format=str(entry.get('format', '')).strip(),
                timestamp=str(stored_entry.get('timestamp', '')).strip(),
            )
        self._persist_current_messages()
        self._active_request_id = None
        self._clear_streaming_preview()
        self._set_waiting_state(False, '')
        self._set_retry_state(False, '')

        # Push the new reply into the developer popup if it is open.
        try:
            latest_reply_text = ''
            for entry in reversed(assistant_entries):
                text = str(entry.get('content', '')).strip()
                if text:
                    latest_reply_text = text
                    break
            if latest_reply_text:
                self._refresh_developer_window(last_reply_text=latest_reply_text)
            else:
                self._refresh_developer_window()
        except Exception as exc:  # noqa: BLE001
            logger.debug('Developer refresh after reply failed: %s', exc)

    @Slot(int, str)
    def _on_worker_error(self, request_id: int, error_text: str) -> None:
        canceled = request_id in self._canceled_requests
        is_active = request_id == self._active_request_id
        if canceled or not is_active:
            return

        self._active_request_id = None
        self._clear_streaming_preview()
        self._set_waiting_state(False, '')
        self._set_retry_state(True, f'Last reply failed: {error_text}')
        QMessageBox.warning(self, 'Generation failed', error_text)

    def _finalize_request_thread(self, request_id: int) -> None:
        # This runs on the main thread after thread.finished fires, so the
        # QThread event loop has already exited. Avoid calling quit()/wait()
        # from inside a worker-signal slot, which triggers
        # "QThread::wait: Thread tried to wait on itself".
        thread = self._pending_threads.pop(request_id, None)
        worker = self._pending_workers.pop(request_id, None)
        self._canceled_requests.discard(request_id)
        if thread is not None:
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()

    def _cancel_active_request(self) -> None:
        if self._active_request_id is None:
            return
        request_id = self._active_request_id
        self._canceled_requests.add(request_id)
        self._active_request_id = None
        self._clear_streaming_preview()
        self._set_waiting_state(False, '')
        self._set_retry_state(True, 'Waiting was canceled. You can retry the last user message.')

    def _retry_last_reply(self) -> None:
        if not self._retry_available:
            return
        if not self.messages or self.messages[-1].get('role') == 'assistant':
            return
        request_messages = self._build_request_messages()
        self._launch_generation(request_messages, retrying=True)

    def _clear_input(self) -> None:
        if self.input_box is not None:
            self.input_box.clear()
            self.input_box.setFocus()

    def on_send_clicked(self) -> None:
        if self.input_box is None or self.send_button is None:
            return
        user_text = self.input_box.toPlainText().strip()
        if not user_text:
            return
        if self._active_request_id is not None:
            QMessageBox.information(
                self,
                'Generation in progress',
                'Wait for the current reply to finish or cancel it.',
            )
            return

        self._maybe_add_scene_participants(user_text)

        self.messages.append({
            'role': 'user',
            'content': user_text,
            'speaker': self.user_display_name,
            'timestamp': datetime.now().replace(microsecond=0).isoformat(),
        })
        self.scene_state_machine.apply_message(text=user_text, role='user', speaker=self.user_display_name)
        self.memory_store.add_message_memory(
            chat_id=str(self.chat_session.get('id', '')).strip() if isinstance(self.chat_session, dict) else '',
            participants=self.participants,
            role='user',
            speaker=self.user_display_name,
            content=user_text,
        )
        self._record_story_development(user_text)
        self._record_memory_development(user_text, role='user', speaker=self.user_display_name)
        self._ensure_system_prompt_message()
        self._append_message(
            self.user_display_name,
            user_text,
            role='user',
            timestamp=str(self.messages[-1].get('timestamp', '')).strip() if self.messages else '',
        )
        self.input_box.clear()
        self._persist_current_messages()
        self._refresh_developer_window(last_user_text=user_text)
        request_messages = self._build_request_messages()
        self._launch_generation(request_messages, retrying=False)

    def _sync_developer_window_visibility(self) -> None:
        """Create/show/hide the developer popup based on the current
        Developer Mode setting. Safe to call repeatedly."""
        try:
            enabled = bool(self.settings_manager.is_developer_mode())
        except Exception as exc:  # noqa: BLE001 - defensive; never block UI
            logger.debug('developer_mode lookup failed: %s', exc)
            enabled = False

        if enabled:
            if self._developer_window is None:
                try:
                    self._developer_window = DeveloperWindow(parent=self)
                except Exception as exc:  # noqa: BLE001
                    logger.warning('Could not create DeveloperWindow: %s', exc)
                    self._developer_window = None
                    return
            if self._developer_window is not None and not self._developer_window.isVisible():
                self._developer_window.show()
                self._developer_window.raise_()
        else:
            if self._developer_window is not None and self._developer_window.isVisible():
                self._developer_window.hide()

    def _refresh_developer_window(
        self,
        *,
        last_user_text: str | None = None,
        last_reply_text: str | None = None,
    ) -> None:
        """Push the current participant state into the developer popup."""
        # Re-check the setting on every refresh so toggling it in Settings
        # takes effect without requiring a chat restart.
        self._sync_developer_window_visibility()
        if self._developer_window is None or not self._developer_window.isVisible():
            return
        try:
            scene_flags: dict[str, Any] = {}
            try:
                # SceneStateMachine may expose current flags; fall back to {}.
                getter = getattr(self.scene_state_machine, 'current_flags', None)
                if callable(getter):
                    maybe_flags = getter()
                    if isinstance(maybe_flags, dict):
                        scene_flags = maybe_flags
            except Exception:  # noqa: BLE001
                scene_flags = {}
            # Merge per-participant scene_flags so the popup shows at least
            # the static flags from character memory if the scene machine
            # does not expose them.
            for participant in self.participants:
                flags = participant.get('scene_flags') if isinstance(participant, dict) else None
                if isinstance(flags, dict):
                    for k, v in flags.items():
                        scene_flags.setdefault(k, v)

            self._developer_window.update_snapshot(
                participants=self.participants,
                user_display_name=self.user_display_name,
                scene_flags=scene_flags,
                last_user_text=last_user_text,
                last_reply_text=last_reply_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning('Developer window refresh failed: %s', exc)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_request_id is not None:
            QMessageBox.information(
                self,
                'Reply still generating',
                'Cancel the wait first if you want to close the chat now. Late replies are discarded after cancel.',
            )
            event.ignore()
            return
        try:
            self.chat_closed.emit()
        except Exception:
            pass
        # Tear down the developer window so it does not leak when the chat
        # is torn down (WA_DeleteOnClose is set on self).
        try:
            if self._developer_window is not None:
                self._developer_window.hide()
                self._developer_window.deleteLater()
                self._developer_window = None
        except Exception as exc:  # noqa: BLE001
            logger.debug('Developer window teardown warning: %s', exc)
        super().closeEvent(event)
