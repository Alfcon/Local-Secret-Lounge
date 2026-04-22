from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QFrame, QLabel, QStackedWidget, QSizePolicy,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.character_manager import CharacterManager
from core.chat_storage import ChatStorage
from core.lm_studio_client import LMStudioClient, LMStudioError
from core.model_manager import ModelManager
from core.settings_manager import SettingsManager

from ui.windows.discover_page import DiscoverPage
from ui.windows.my_characters_page import MyCharactersPage
from ui.windows.my_chats_page import MyChatsPage
from ui.windows.settings_page import SettingsPage
from ui.windows.chat_window import ChatWindow

logger = logging.getLogger(__name__)

NAV_ITEMS = [
    ("discover",       "🔍  Discover",      "Discover Characters"),
    ("my_characters",  "👤  My Characters", "My Character Library"),
    ("my_chats",       "💬  My Chats",      "My Chats"),
    ("settings",       "⚙  Settings",      "Settings"),
]

PAGE_INDEX = {key: idx for idx, (key, _, _) in enumerate(NAV_ITEMS)}
# Chat window lives at index 4
CHAT_PAGE_INDEX = len(NAV_ITEMS)


class NavButton(QPushButton):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("nav_btn")
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        font = QFont()
        font.setPointSize(12)
        self.setFont(font)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings_manager: SettingsManager,
        model_manager: ModelManager,
        character_manager: CharacterManager,
        chat_storage: ChatStorage,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.model_manager = model_manager
        self.character_manager = character_manager
        self.chat_storage = chat_storage

        self.setWindowTitle("Local Secret Lounge")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        self._nav_buttons: dict[str, NavButton] = {}
        self._chat_window: ChatWindow | None = None

        self._build_ui()
        self._navigate_to(settings_manager.get("startup_page", "discover") or "discover")

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ── Sidebar ───────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(190)
        sidebar.setMaximumWidth(260)
        sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(4)
        sidebar_layout.setContentsMargins(8, 16, 8, 16)

        # App title
        app_title = QLabel("Local Secret Lounge")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        app_title.setFont(font)
        app_title.setStyleSheet("color: #e94560; padding: 8px 8px 16px 8px;")
        app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(app_title)

        # Nav buttons
        for key, label, _ in NAV_ITEMS:
            btn = NavButton(label)
            btn.clicked.connect(lambda checked, k=key: self._navigate_to(k))
            sidebar_layout.addWidget(btn)
            self._nav_buttons[key] = btn

        sidebar_layout.addStretch()

        # Version / info label
        info = QLabel("Local Offline\nAdult Fantasy Chat")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #a8a8c8; font-size: 10px; font-weight: bold;")
        info.setWordWrap(True)
        sidebar_layout.addWidget(info)

        root_layout.addWidget(sidebar)

        # ── Page stack ────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 0: Discover
        self._discover_page = DiscoverPage(self.character_manager)
        self._discover_page.chat_requested.connect(self._open_chat)
        self._stack.addWidget(self._discover_page)

        # 1: My Characters
        self._my_chars_page = MyCharactersPage(self.character_manager, settings_manager=self.settings_manager)
        self._my_chars_page.chat_requested.connect(self._open_chat)
        self._stack.addWidget(self._my_chars_page)

        # 2: My Chats
        self._my_chats_page = MyChatsPage(self.chat_storage)
        self._my_chats_page.resume_chat_requested.connect(self._resume_chat)
        self._stack.addWidget(self._my_chats_page)

        # 3: Settings
        self._settings_page = SettingsPage(self.settings_manager, self.model_manager)
        self._settings_page.settings_changed.connect(self._on_settings_changed)
        self._stack.addWidget(self._settings_page)

        # 4: Chat window placeholder (replaced dynamically)
        self._chat_placeholder = QWidget()
        self._stack.addWidget(self._chat_placeholder)

        root_layout.addWidget(self._stack)

    # ── Navigation ────────────────────────────────────────────────────────

    def _navigate_to(self, page_key: str) -> None:
        # Uncheck all nav buttons
        for btn in self._nav_buttons.values():
            btn.setChecked(False)

        if page_key in PAGE_INDEX:
            self._stack.setCurrentIndex(PAGE_INDEX[page_key])
            if page_key in self._nav_buttons:
                self._nav_buttons[page_key].setChecked(True)
        elif page_key == "chat":
            self._stack.setCurrentIndex(CHAT_PAGE_INDEX)
        else:
            # Default to discover
            self._stack.setCurrentIndex(0)
            self._nav_buttons.get("discover", list(self._nav_buttons.values())[0]).setChecked(True)

    # ── Model / generation resolution ─────────────────────────────────────

    def _resolve_model_entry(self) -> dict[str, Any] | None:
        """Resolve the active model entry based on the chat backend preference.

        Returns None (after showing a QMessageBox) if no model can be resolved.
        """
        backend = self.settings_manager.get_chat_backend_preference()

        if backend == 'lm_studio':
            try:
                client = LMStudioClient.from_settings(self.settings_manager)
                preferred = str(self.settings_manager.get('lm_studio_model_id', '') or '').strip()
                return client.resolve_model(preferred or None)
            except LMStudioError as exc:
                QMessageBox.warning(
                    self,
                    'LM Studio not available',
                    f'Could not connect to LM Studio:\n\n{exc}\n\n'
                    'Open Settings to verify the base URL, start the LM Studio Local '
                    'Server, and load a model — or switch the backend to "Local".',
                )
                return None
            except Exception as exc:  # noqa: BLE001 - defensive catch-all
                logger.exception('Unexpected LM Studio resolution failure: %s', exc)
                QMessageBox.warning(
                    self,
                    'LM Studio error',
                    f'Unexpected error while contacting LM Studio:\n\n{exc}',
                )
                return None

        # Local backend
        default_id = self.settings_manager.get('default_model_id')
        model_entry: dict[str, Any] | None = None
        if default_id:
            model_entry = self.model_manager.get_model(str(default_id))

        if model_entry is None:
            models = self.model_manager.list_models()
            if models:
                model_entry = models[0]

        if model_entry is None:
            QMessageBox.warning(
                self,
                'No model configured',
                'No local model is registered yet. Open Settings → Models to import '
                'a .gguf model before starting a chat, or enable the LM Studio backend.',
            )
            return None

        return model_entry

    def _build_generation_settings(self, model_entry: dict[str, Any]) -> dict[str, Any]:
        model_id = str(model_entry.get('id', '')) if isinstance(model_entry, dict) else ''
        perf = self.model_manager.get_model_performance_settings(model_id or None)
        temperature = self.settings_manager.get('last_temperature', 0.8)
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            temperature = 0.8
        n_gpu_layers = self.settings_manager.get('n_gpu_layers', 0)
        try:
            n_gpu_layers = int(n_gpu_layers)
        except (TypeError, ValueError):
            n_gpu_layers = 0
        return {
            'temperature': temperature,
            'context_size': int(perf.get('context_size', 4096)),
            'threads': int(perf.get('threads', 4)),
            'max_tokens': int(perf.get('max_tokens', 512)),
            'n_gpu_layers': n_gpu_layers,
        }

    # ── Chat management ───────────────────────────────────────────────────

    def _open_chat(self, character: dict[str, Any]) -> None:
        if not isinstance(character, dict) or not character:
            QMessageBox.warning(self, 'Start Chat Failed', 'Character data is missing or invalid.')
            return
        self._replace_chat_window(character=character, chat_session=None)

    def _resume_chat(self, chat_id: str) -> None:
        # Load the full chat session (not just the character) from storage
        try:
            chat_session = self.chat_storage.load_chat(chat_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Resume Failed', str(exc))
            return

        character = chat_session.get('character') if isinstance(chat_session, dict) else None
        if not isinstance(character, dict) or not character:
            QMessageBox.warning(self, 'Resume Failed', 'Could not find character data in this chat.')
            return

        self._replace_chat_window(character=character, chat_session=chat_session)

    def _replace_chat_window(
        self,
        character: dict[str, Any],
        chat_session: dict[str, Any] | None,
    ) -> None:
        model_entry = self._resolve_model_entry()
        if model_entry is None:
            return

        generation_settings = self._build_generation_settings(model_entry)

        # Remove old chat window from stack if present
        if self._chat_window is not None:
            old = self._chat_window
            self._stack.removeWidget(old)
            old.deleteLater()
            self._chat_window = None

        try:
            chat_win = ChatWindow(
                settings_manager=self.settings_manager,
                model_manager=self.model_manager,
                chat_storage=self.chat_storage,
                model_entry=model_entry,
                character=character,
                generation_settings=generation_settings,
                chat_session=chat_session,
                parent=self,
            )
        except Exception as exc:  # noqa: BLE001 - surface construction errors to the user
            logger.exception('Failed to construct ChatWindow: %s', exc)
            QMessageBox.critical(self, 'Start Chat Failed', f'Could not open chat window:\n\n{exc}')
            # Restore placeholder so the stack index stays valid
            placeholder = QWidget()
            self._stack.removeWidget(self._stack.widget(CHAT_PAGE_INDEX))
            self._stack.insertWidget(CHAT_PAGE_INDEX, placeholder)
            return

        # Connect the chat_closed signal if the ChatWindow exposes one
        if hasattr(chat_win, 'chat_closed'):
            try:
                chat_win.chat_closed.connect(self._on_chat_closed)
            except Exception as exc:  # noqa: BLE001 - defensive
                logger.warning('Could not connect chat_closed signal: %s', exc)
        self._chat_window = chat_win

        # Replace placeholder at index CHAT_PAGE_INDEX
        self._stack.removeWidget(self._stack.widget(CHAT_PAGE_INDEX))
        self._stack.insertWidget(CHAT_PAGE_INDEX, chat_win)

        self._navigate_to("chat")

    def _on_chat_closed(self) -> None:
        # Navigate back to My Chats so users can see their history
        self._chat_window = None
        # Put a fresh placeholder back so the stack index remains valid
        placeholder = QWidget()
        self._stack.removeWidget(self._stack.widget(CHAT_PAGE_INDEX))
        self._stack.insertWidget(CHAT_PAGE_INDEX, placeholder)
        self._navigate_to("my_chats")
        try:
            self._my_chats_page.refresh()
        except Exception as exc:  # noqa: BLE001
            logger.warning('My Chats refresh failed: %s', exc)

    # ── Settings changes ──────────────────────────────────────────────────

    def _on_settings_changed(self) -> None:
        logger.info("Settings saved — reloading models and characters.")
        try:
            self.model_manager.reload_registry()
        except Exception as exc:
            logger.error("Model reload failed: %s", exc)
        try:
            self._discover_page.refresh()
            self._my_chars_page.refresh()
        except Exception as exc:
            logger.error("Page refresh failed: %s", exc)
        # If a chat is active, react to a Developer Mode toggle without
        # requiring the user to close and reopen the chat.
        try:
            if self._chat_window is not None and hasattr(self._chat_window, '_sync_developer_window_visibility'):
                self._chat_window._sync_developer_window_visibility()
                if hasattr(self._chat_window, '_refresh_developer_window'):
                    self._chat_window._refresh_developer_window()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Developer window visibility sync failed: %s", exc)
