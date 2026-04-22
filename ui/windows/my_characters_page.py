from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QSplitter,
    QTextEdit, QFileDialog, QMessageBox, QLineEdit, QFormLayout,
    QScrollArea, QSizePolicy, QDialog, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from core.character_manager import CharacterManager
from core.chat_storage import ChatStorage
from ui.widgets.avatar_label import AvatarLabel
from ui.widgets.character_image import CharacterImage

logger = logging.getLogger(__name__)


class EditCharacterDialog(QDialog):
    """Full edit dialog for a user-created character."""

    def __init__(
        self,
        character: dict[str, Any],
        character_manager: CharacterManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._character = dict(character)
        self.character_manager = character_manager
        self.setWindowTitle(f"Edit Character — {character.get('name', '')}")
        self.setMinimumSize(680, 700)
        self.setModal(True)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(24, 24, 24, 24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        scroll.setWidget(inner)

        self.name_edit = QLineEdit()
        form.addRow("Name *", self.name_edit)

        self.title_edit = QLineEdit()
        form.addRow("Title / Role", self.title_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setMinimumHeight(80)
        form.addRow("Description", self.description_edit)

        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setMinimumHeight(120)
        form.addRow("System Prompt", self.system_prompt_edit)

        self.greeting_edit = QTextEdit()
        self.greeting_edit.setMinimumHeight(80)
        form.addRow("Greeting", self.greeting_edit)

        self.scenario_edit = QTextEdit()
        self.scenario_edit.setMinimumHeight(80)
        form.addRow("Starting Scenario", self.scenario_edit)

        self.example_dialogue_edit = QTextEdit()
        self.example_dialogue_edit.setMinimumHeight(80)
        form.addRow("Example Dialogue", self.example_dialogue_edit)

        self.world_lore_edit = QTextEdit()
        self.world_lore_edit.setMinimumHeight(80)
        form.addRow("World Lore Notes", self.world_lore_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("comma-separated tags")
        form.addRow("Tags", self.tags_edit)

        avatar_row = QHBoxLayout()
        self.avatar_path_edit = QLineEdit()
        self.avatar_path_edit.setPlaceholderText("Path to avatar image (optional)")
        avatar_row.addWidget(self.avatar_path_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_avatar)
        avatar_row.addWidget(browse_btn)
        form.addRow("Avatar Image", avatar_row)

        self.folder_edit = QLineEdit()
        form.addRow("Folder", self.folder_edit)

        root.addWidget(scroll)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff6578; font-size: 12px; font-weight: bold;")
        root.addWidget(self.error_label)

    def _populate(self) -> None:
        c = self._character
        self.name_edit.setText(str(c.get("name", "")))
        self.title_edit.setText(str(c.get("title", "") or c.get("role", "")))
        self.description_edit.setPlainText(str(c.get("description", "") or ""))
        self.system_prompt_edit.setPlainText(str(c.get("system_prompt", "") or ""))
        self.greeting_edit.setPlainText(str(c.get("greeting", "") or ""))
        self.scenario_edit.setPlainText(str(c.get("starting_scenario", "") or ""))
        self.example_dialogue_edit.setPlainText(str(c.get("example_dialogue", "") or ""))
        self.world_lore_edit.setPlainText(
            str(c.get("world_lore_notes", "") or c.get("world_lore", "") or "")
        )
        tags = c.get("tags", [])
        self.tags_edit.setText(", ".join(str(t) for t in tags))
        self.avatar_path_edit.setText(str(c.get("avatar_path", "") or ""))
        self.folder_edit.setText(str(c.get("folder", "General")))

    def _browse_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Avatar Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            self.avatar_path_edit.setText(path)

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("Character name is required.")
            self.name_edit.setFocus()
            return

        tags_raw = self.tags_edit.text().strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        updated = dict(self._character)
        updated.update({
            "name": name,
            "title": self.title_edit.text().strip(),
            "role": self.title_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "system_prompt": self.system_prompt_edit.toPlainText().strip(),
            "greeting": self.greeting_edit.toPlainText().strip(),
            "starting_scenario": self.scenario_edit.toPlainText().strip(),
            "example_dialogue": self.example_dialogue_edit.toPlainText().strip(),
            "world_lore_notes": self.world_lore_edit.toPlainText().strip(),
            "tags": tags,
            "avatar_path": self.avatar_path_edit.text().strip(),
            "folder": self.folder_edit.text().strip() or "General",
        })

        try:
            self.character_manager.save_character(
                updated,
                copy_avatar_to_managed_storage=bool(self.avatar_path_edit.text().strip()),
            )
            self.accept()
        except Exception as exc:
            self.error_label.setText(str(exc))


class CharacterDetailPanel(QWidget):
    """Right-hand panel showing full character details."""

    chat_requested = Signal(dict)
    edit_requested = Signal(dict)
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._character: dict[str, Any] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        self.empty_label = QLabel("Select a character to view details.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #c8c8e0; font-size: 14px;")
        layout.addWidget(self.empty_label)

        self.detail_widget = QWidget()
        detail_layout = QVBoxLayout(self.detail_widget)
        detail_layout.setSpacing(12)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        # Avatar — scalable rounded square, consistent with the chat window
        # and Discover page. Minimum ensures it is not swallowed by the text
        # column on narrow windows; it grows with the layout beyond that.
        header_row = QHBoxLayout()
        self.avatar = CharacterImage(minimum_size=(192, 192))
        self.avatar.setMaximumHeight(360)
        header_row.addWidget(self.avatar, stretch=0)

        name_col = QVBoxLayout()
        self.name_label = QLabel("")
        font = QFont()
        font.setBold(True)
        font.setPointSize(16)
        self.name_label.setFont(font)
        name_col.addWidget(self.name_label)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: #d8d8f0; font-size: 12px; font-weight: bold;")
        name_col.addWidget(self.title_label)

        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color: #a8a8c8; font-size: 11px;")
        name_col.addWidget(self.source_label)

        name_col.addStretch()
        header_row.addLayout(name_col)
        header_row.addStretch()
        detail_layout.addLayout(header_row)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #f0f0ff; font-size: 12px; line-height: 1.5;")
        detail_layout.addWidget(self.desc_label)

        prompt_heading = QLabel("System Prompt")
        prompt_heading.setObjectName("section_label")
        detail_layout.addWidget(prompt_heading)

        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setMinimumHeight(80)
        self.prompt_preview.setStyleSheet(
            "background-color: #12122a; color: #e0e0f8; "
            "border: 1px solid #3a3a5a; border-radius: 6px; font-size: 11px;"
        )
        detail_layout.addWidget(self.prompt_preview)

        self.tags_row = QHBoxLayout()
        self.tags_row.setSpacing(6)
        detail_layout.addLayout(self.tags_row)

        detail_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.chat_btn = QPushButton("💬  Start Chat")
        self.chat_btn.setFixedHeight(36)
        self.chat_btn.clicked.connect(self._on_chat)
        btn_row.addWidget(self.chat_btn)

        self.edit_btn = QPushButton("✏  Edit")
        self.edit_btn.setObjectName("secondary_btn")
        self.edit_btn.setFixedHeight(36)
        self.edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setObjectName("danger_btn")
        self.delete_btn.setFixedHeight(36)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self.delete_btn)

        detail_layout.addLayout(btn_row)

        layout.addWidget(self.detail_widget)
        self.detail_widget.hide()

    def set_character(self, character: dict[str, Any] | None) -> None:
        self._character = character
        if character is None:
            self.empty_label.show()
            self.detail_widget.hide()
            return

        self.empty_label.hide()
        self.detail_widget.show()

        name_color = str(character.get("name_color", "") or "#ffffff")
        self.avatar.set_character(
            character.get("name", "?"),
            character.get("avatar_path", ""),
            name_color,
        )
        self.name_label.setText(character.get("name", "Unknown"))
        self.name_label.setStyleSheet(f"color: {name_color}; font-size: 16px; font-weight: bold;")

        title = str(character.get("title", "") or character.get("role", "") or "").strip()
        self.title_label.setText(title)

        source = str(character.get("source", "user"))
        self.source_label.setText(f"Source: {source}")

        self.desc_label.setText(str(character.get("description", "") or "").strip())
        self.prompt_preview.setPlainText(str(character.get("system_prompt", "") or "").strip())

        while self.tags_row.count():
            item = self.tags_row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for tag in character.get("tags", [])[:6]:
            tag_lbl = QLabel(str(tag))
            tag_lbl.setStyleSheet(
                "background-color: #1a4a8a; color: #e0f0ff; "
                "border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: bold;"
            )
            self.tags_row.addWidget(tag_lbl)
        self.tags_row.addStretch()

        is_discover = str(character.get("source", "")) == "discover"
        self.edit_btn.setEnabled(not is_discover)
        self.delete_btn.setEnabled(not is_discover)

    def _on_chat(self) -> None:
        if self._character:
            self.chat_requested.emit(self._character)

    def _on_edit(self) -> None:
        if self._character:
            self.edit_requested.emit(self._character)

    def _on_delete(self) -> None:
        if self._character:
            name = self._character.get("name", "this character")
            reply = QMessageBox.question(
                self,
                "Delete Character",
                f"Are you sure you want to delete '{name}'? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.delete_requested.emit(str(self._character.get("id", "")))


class MyCharactersPage(QWidget):
    """My Character Library page — list + detail panel."""

    chat_requested = Signal(dict)

    def __init__(self, character_manager: CharacterManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.character_manager = character_manager
        self.chat_storage = ChatStorage()
        self._characters: list[dict[str, Any]] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #16213e; border-bottom: 1px solid #2a2a4a;")
        top_bar.setFixedHeight(60)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 8, 20, 8)

        heading = QLabel("My Character Library")
        heading.setObjectName("heading")
        top_layout.addWidget(heading)
        top_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search…")
        self.search_input.setMinimumWidth(150)
        self.search_input.setMaximumWidth(280)
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._apply_filter)
        top_layout.addWidget(self.search_input)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setObjectName("secondary_btn")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self.refresh)
        top_layout.addWidget(refresh_btn)

        create_btn = QPushButton("＋ Create Character")
        create_btn.setFixedHeight(32)
        create_btn.clicked.connect(self._on_create_character)
        top_layout.addWidget(create_btn)

        layout.addWidget(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #2a2a4a; }")

        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: #16213e;")
        left_panel.setMinimumWidth(180)
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(0)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.char_list = QListWidget()
        self.char_list.setFrameShape(QFrame.Shape.NoFrame)
        self.char_list.setStyleSheet(
            "QListWidget { background-color: #16213e; border: none; color: #ffffff; }"
            "QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #3a3a5a; color: #ffffff; }"
            "QListWidget::item:selected { background-color: #0f3460; color: #ffffff; }"
        )
        self.char_list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.char_list)

        splitter.addWidget(left_panel)

        self.detail_panel = CharacterDetailPanel()
        self.detail_panel.chat_requested.connect(self.chat_requested.emit)
        self.detail_panel.edit_requested.connect(self._on_edit_character)
        self.detail_panel.delete_requested.connect(self._on_delete_character)
        splitter.addWidget(self.detail_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 780])

        layout.addWidget(splitter)

    def _on_create_character(self) -> None:
        empty_character = {
            "name": "",
            "role": "",
            "story_role": "",
            "system_prompt": "",
            "starting_scenario": "",
            "greeting": "",
            "identity": {
                "age_band": "",
                "public_summary": "",
                "private_truths": [],
                "core_traits": [],
                "values": [],
                "fears": [],
                "goals": {
                    "short_term": [],
                    "mid_term": [],
                    "long_term": []
                },
                "boundaries": {
                    "hard": [],
                    "soft": []
                },
                "age": 0
            },
            "voice": {
                "tone": "",
                "cadence": "",
                "favored_patterns": [],
                "avoid_patterns": []
            },
            "knowledge": {
                "known_facts": []
            },
            "tags": [],
            "folder": "General"
        }
        dialog = EditCharacterDialog(empty_character, self.character_manager, parent=self)
        dialog.setWindowTitle("Create Character")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            # Select the newly created character
            for i in range(self.char_list.count()):
                item = self.char_list.item(i)
                if item:
                    c = item.data(Qt.ItemDataRole.UserRole)
                    if str(c.get("name", "")) == dialog.name_edit.text().strip():
                        self.char_list.setCurrentRow(i)
                        break

    def refresh(self) -> None:
        try:
            all_chars = self.character_manager.list_all_characters()
        except Exception as exc:
            logger.error("Failed to load characters: %s", exc)
            all_chars = []

        # Determine which built-in (discover) character names have an active chat
        builtin_with_chats: set[str] = set()
        try:
            chats = self.chat_storage.list_chats()
            for chat in chats:
                char_name = str(chat.get("character_name", "")).strip().lower()
                if char_name:
                    builtin_with_chats.add(char_name)
        except Exception as exc:
            logger.warning("Could not read chat list for filtering: %s", exc)

        # Keep all user-created characters; keep built-in only if they have a chat
        self._characters = [
            c for c in all_chars
            if str(c.get("source", "")) != "discover"
            or str(c.get("name", "")).strip().lower() in builtin_with_chats
        ]

        self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        if q:
            filtered = [
                c for c in self._characters
                if q in str(c.get("name", "")).lower()
                or any(q in str(t).lower() for t in c.get("tags", []))
            ]
        else:
            filtered = list(self._characters)
        self._populate_list(filtered)

    def _populate_list(self, characters: list[dict[str, Any]]) -> None:
        self.char_list.clear()
        self._filtered = characters
        for char in characters:
            name = str(char.get("name", "Unknown"))
            source = str(char.get("source", ""))
            label = f"{'★ ' if char.get('is_favorite') else ''}{name}"
            if source == "discover":
                label += "  [built-in]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, char)
            self.char_list.addItem(item)
        self.detail_panel.set_character(None)

    def _on_selection_changed(self, row: int) -> None:
        if row < 0:
            self.detail_panel.set_character(None)
            return
        item = self.char_list.item(row)
        if item:
            char = item.data(Qt.ItemDataRole.UserRole)
            self.detail_panel.set_character(char)

    def _on_edit_character(self, character: dict[str, Any]) -> None:
        dialog = EditCharacterDialog(character, self.character_manager, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            # Re-select the edited character
            edited_name = character.get("name", "")
            for i in range(self.char_list.count()):
                item = self.char_list.item(i)
                if item:
                    c = item.data(Qt.ItemDataRole.UserRole)
                    if str(c.get("name", "")) == edited_name:
                        self.char_list.setCurrentRow(i)
                        break

    def _on_delete_character(self, character_id: str) -> None:
        try:
            self.character_manager.delete_character(character_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Delete Failed", str(exc))
