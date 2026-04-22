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

        def add_section(title: str):
            lbl = QLabel(title)
            lbl.setStyleSheet("font-weight: bold; margin-top: 10px; color: #a8a8c8;")
            form.addRow(lbl)

        add_section("--- Basic ---")
        self.name_edit = QLineEdit()
        form.addRow("Name *", self.name_edit)

        self.title_edit = QLineEdit()
        form.addRow("Title / Role", self.title_edit)

        self.story_role_edit = QLineEdit()
        form.addRow("Story Role", self.story_role_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setMinimumHeight(60)
        form.addRow("Description", self.description_edit)

        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setMinimumHeight(80)
        form.addRow("System Prompt", self.system_prompt_edit)

        self.greeting_edit = QTextEdit()
        self.greeting_edit.setMinimumHeight(60)
        form.addRow("Greeting", self.greeting_edit)

        self.scenario_edit = QTextEdit()
        self.scenario_edit.setMinimumHeight(60)
        form.addRow("Starting Scenario", self.scenario_edit)

        self.example_dialogue_edit = QTextEdit()
        self.example_dialogue_edit.setMinimumHeight(60)
        form.addRow("Example Dialogue", self.example_dialogue_edit)

        self.world_lore_edit = QTextEdit()
        self.world_lore_edit.setMinimumHeight(60)
        form.addRow("World Lore Notes", self.world_lore_edit)

        add_section("--- Identity ---")
        self.age_edit = QLineEdit()
        form.addRow("Age", self.age_edit)

        self.age_band_edit = QLineEdit()
        form.addRow("Age Band", self.age_band_edit)

        self.public_summary_edit = QTextEdit()
        self.public_summary_edit.setMinimumHeight(60)
        form.addRow("Public Summary", self.public_summary_edit)

        self.private_truths_edit = QTextEdit()
        self.private_truths_edit.setMinimumHeight(60)
        self.private_truths_edit.setPlaceholderText("One per line")
        form.addRow("Private Truths", self.private_truths_edit)

        self.core_traits_edit = QLineEdit()
        self.core_traits_edit.setPlaceholderText("Comma-separated")
        form.addRow("Core Traits", self.core_traits_edit)

        self.values_edit = QLineEdit()
        self.values_edit.setPlaceholderText("Comma-separated")
        form.addRow("Values", self.values_edit)

        self.fears_edit = QLineEdit()
        self.fears_edit.setPlaceholderText("Comma-separated")
        form.addRow("Fears", self.fears_edit)

        self.goals_short_edit = QTextEdit()
        self.goals_short_edit.setMinimumHeight(50)
        self.goals_short_edit.setPlaceholderText("One per line")
        form.addRow("Goals (Short Term)", self.goals_short_edit)

        self.goals_mid_edit = QTextEdit()
        self.goals_mid_edit.setMinimumHeight(50)
        self.goals_mid_edit.setPlaceholderText("One per line")
        form.addRow("Goals (Mid Term)", self.goals_mid_edit)

        self.goals_long_edit = QTextEdit()
        self.goals_long_edit.setMinimumHeight(50)
        self.goals_long_edit.setPlaceholderText("One per line")
        form.addRow("Goals (Long Term)", self.goals_long_edit)

        self.boundaries_hard_edit = QTextEdit()
        self.boundaries_hard_edit.setMinimumHeight(50)
        self.boundaries_hard_edit.setPlaceholderText("One per line")
        form.addRow("Boundaries (Hard)", self.boundaries_hard_edit)

        self.boundaries_soft_edit = QTextEdit()
        self.boundaries_soft_edit.setMinimumHeight(50)
        self.boundaries_soft_edit.setPlaceholderText("One per line")
        form.addRow("Boundaries (Soft)", self.boundaries_soft_edit)

        add_section("--- Voice ---")
        self.voice_tone_edit = QLineEdit()
        form.addRow("Tone", self.voice_tone_edit)

        self.voice_cadence_edit = QLineEdit()
        form.addRow("Cadence", self.voice_cadence_edit)

        self.voice_favored_edit = QTextEdit()
        self.voice_favored_edit.setMinimumHeight(50)
        self.voice_favored_edit.setPlaceholderText("One per line")
        form.addRow("Favored Patterns", self.voice_favored_edit)

        self.voice_avoid_edit = QTextEdit()
        self.voice_avoid_edit.setMinimumHeight(50)
        self.voice_avoid_edit.setPlaceholderText("One per line")
        form.addRow("Avoid Patterns", self.voice_avoid_edit)

        add_section("--- Knowledge ---")
        self.known_facts_edit = QTextEdit()
        self.known_facts_edit.setMinimumHeight(60)
        self.known_facts_edit.setPlaceholderText("One per line")
        form.addRow("Known Facts", self.known_facts_edit)

        add_section("--- Meta ---")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Comma-separated tags")
        form.addRow("Tags", self.tags_edit)

        avatar_row = QHBoxLayout()
        self.avatar_path_edit = QLineEdit()
        self.avatar_path_edit.setPlaceholderText("Path to avatar image (optional)")
        avatar_row.addWidget(self.avatar_path_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.setStyleSheet("font-size: 11px;")
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
        self.story_role_edit.setText(str(c.get("story_role", "")))
        self.description_edit.setPlainText(str(c.get("description", "") or ""))
        self.system_prompt_edit.setPlainText(str(c.get("system_prompt", "") or ""))
        self.greeting_edit.setPlainText(str(c.get("greeting", "") or ""))
        self.scenario_edit.setPlainText(str(c.get("starting_scenario", "") or ""))
        self.example_dialogue_edit.setPlainText(str(c.get("example_dialogue", "") or ""))
        self.world_lore_edit.setPlainText(
            str(c.get("world_lore_notes", "") or c.get("world_lore", "") or "")
        )

        identity = c.get("identity", {})
        if not isinstance(identity, dict): identity = {}
        self.age_edit.setText(str(identity.get("age", "")))
        self.age_band_edit.setText(str(identity.get("age_band", "")))
        self.public_summary_edit.setPlainText(str(identity.get("public_summary", "")))
        self.private_truths_edit.setPlainText("\n".join(str(x) for x in identity.get("private_truths", [])))
        self.core_traits_edit.setText(", ".join(str(x) for x in identity.get("core_traits", [])))
        self.values_edit.setText(", ".join(str(x) for x in identity.get("values", [])))
        self.fears_edit.setText(", ".join(str(x) for x in identity.get("fears", [])))
        
        goals = identity.get("goals", {})
        if not isinstance(goals, dict): goals = {}
        self.goals_short_edit.setPlainText("\n".join(str(x) for x in goals.get("short_term", [])))
        self.goals_mid_edit.setPlainText("\n".join(str(x) for x in goals.get("mid_term", [])))
        self.goals_long_edit.setPlainText("\n".join(str(x) for x in goals.get("long_term", [])))

        boundaries = identity.get("boundaries", {})
        if not isinstance(boundaries, dict): boundaries = {}
        self.boundaries_hard_edit.setPlainText("\n".join(str(x) for x in boundaries.get("hard", [])))
        self.boundaries_soft_edit.setPlainText("\n".join(str(x) for x in boundaries.get("soft", [])))

        voice = c.get("voice", {})
        if not isinstance(voice, dict): voice = {}
        self.voice_tone_edit.setText(str(voice.get("tone", "")))
        self.voice_cadence_edit.setText(str(voice.get("cadence", "")))
        self.voice_favored_edit.setPlainText("\n".join(str(x) for x in voice.get("favored_patterns", [])))
        self.voice_avoid_edit.setPlainText("\n".join(str(x) for x in voice.get("avoid_patterns", [])))

        knowledge = c.get("knowledge", {})
        if not isinstance(knowledge, dict): knowledge = {}
        self.known_facts_edit.setPlainText("\n".join(str(x) for x in knowledge.get("known_facts", [])))

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

        def _split_comma(text: str) -> list[str]:
            return [t.strip() for t in text.split(",") if t.strip()]

        def _split_lines(text: str) -> list[str]:
            return [t.strip() for t in text.split("\n") if t.strip()]

        tags = _split_comma(self.tags_edit.text())

        try:
            age_val = int(self.age_edit.text().strip())
        except ValueError:
            age_val = 0

        updated = dict(self._character)
        updated.update({
            "name": name,
            "title": self.title_edit.text().strip(),
            "role": self.title_edit.text().strip(),
            "story_role": self.story_role_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "system_prompt": self.system_prompt_edit.toPlainText().strip(),
            "greeting": self.greeting_edit.toPlainText().strip(),
            "starting_scenario": self.scenario_edit.toPlainText().strip(),
            "example_dialogue": self.example_dialogue_edit.toPlainText().strip(),
            "world_lore_notes": self.world_lore_edit.toPlainText().strip(),
            "identity": {
                "age": age_val,
                "age_band": self.age_band_edit.text().strip(),
                "public_summary": self.public_summary_edit.toPlainText().strip(),
                "private_truths": _split_lines(self.private_truths_edit.toPlainText()),
                "core_traits": _split_comma(self.core_traits_edit.text()),
                "values": _split_comma(self.values_edit.text()),
                "fears": _split_comma(self.fears_edit.text()),
                "goals": {
                    "short_term": _split_lines(self.goals_short_edit.toPlainText()),
                    "mid_term": _split_lines(self.goals_mid_edit.toPlainText()),
                    "long_term": _split_lines(self.goals_long_edit.toPlainText()),
                },
                "boundaries": {
                    "hard": _split_lines(self.boundaries_hard_edit.toPlainText()),
                    "soft": _split_lines(self.boundaries_soft_edit.toPlainText()),
                }
            },
            "voice": {
                "tone": self.voice_tone_edit.text().strip(),
                "cadence": self.voice_cadence_edit.text().strip(),
                "favored_patterns": _split_lines(self.voice_favored_edit.toPlainText()),
                "avoid_patterns": _split_lines(self.voice_avoid_edit.toPlainText()),
            },
            "knowledge": {
                "known_facts": _split_lines(self.known_facts_edit.toPlainText()),
            },
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
        detail_layout = QHBoxLayout(self.detail_widget)
        detail_layout.setSpacing(16)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        # Left column: Character image (33%)
        left_col = QVBoxLayout()
        left_col.setSpacing(0)
        left_col.setContentsMargins(0, 0, 0, 0)
        self.avatar = CharacterImage(minimum_size=(192, 192))
        self.avatar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_col.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignTop)
        left_col.addStretch()

        # Right column: Character details (67%)
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.setContentsMargins(0, 0, 0, 0)

        self.name_label = QLabel("")
        font = QFont()
        font.setBold(True)
        font.setPointSize(16)
        self.name_label.setFont(font)
        right_col.addWidget(self.name_label)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: #d8d8f0; font-size: 12px; font-weight: bold;")
        right_col.addWidget(self.title_label)

        self.story_role_label = QLabel("")
        self.story_role_label.setStyleSheet("color: #d8d8f0; font-size: 12px; font-weight: bold;")
        self.story_role_label.setWordWrap(True)
        right_col.addWidget(self.story_role_label)

        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color: #a8a8c8; font-size: 11px;")
        right_col.addWidget(self.source_label)

        self.desc_heading = QLabel("Description")
        self.desc_heading.setObjectName("section_label")
        right_col.addWidget(self.desc_heading)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #f0f0ff; font-size: 12px; line-height: 1.5;")
        right_col.addWidget(self.desc_label)

        self.prompt_heading = QLabel("System Prompt")
        self.prompt_heading.setObjectName("section_label")
        right_col.addWidget(self.prompt_heading)

        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setMinimumHeight(80)
        self.prompt_preview.setStyleSheet(
            "background-color: #12122a; color: #e0e0f8; "
            "border: 1px solid #3a3a5a; border-radius: 6px; font-size: 11px;"
        )
        right_col.addWidget(self.prompt_preview)

        self.tags_row = QHBoxLayout()
        self.tags_row.setSpacing(6)
        right_col.addLayout(self.tags_row)

        right_col.addStretch()

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

        right_col.addLayout(btn_row)

        # Add columns to main detail layout
        detail_layout.addLayout(left_col, 1)
        detail_layout.addLayout(right_col, 2)

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
        name = character.get("name", "Unknown")
        self.name_label.setText(f"Name: {name}")
        self.name_label.setStyleSheet(f"color: {name_color}; font-size: 16px; font-weight: bold;")

        title = str(character.get("title", "") or character.get("role", "") or "").strip()
        if title:
            self.title_label.setText(f"Title / Role: {title}")
            self.title_label.show()
        else:
            self.title_label.hide()

        story_role = str(character.get("story_role", "")).strip()
        if story_role:
            self.story_role_label.setText(f"Story Role: {story_role}")
            self.story_role_label.show()
        else:
            self.story_role_label.hide()

        source = str(character.get("source", "user"))
        self.source_label.setText(f"Source: {source}")

        desc = str(character.get("description", "") or "").strip()
        self.desc_label.setText(desc)
        if desc:
            self.desc_heading.show()
            self.desc_label.show()
        else:
            self.desc_heading.hide()
            self.desc_label.hide()

        sys_prompt = str(character.get("system_prompt", "") or "").strip()
        self.prompt_preview.setPlainText(sys_prompt)
        if sys_prompt:
            self.prompt_heading.show()
            self.prompt_preview.show()
        else:
            self.prompt_heading.hide()
            self.prompt_preview.hide()

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

    def __init__(self, character_manager: CharacterManager, parent: QWidget | None = None, settings_manager=None) -> None:
        super().__init__(parent)
        self.character_manager = character_manager
        self.chat_storage = ChatStorage()
        self._characters: list[dict[str, Any]] = []
        self.settings_manager = settings_manager
        self._splitter = None
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
        self._splitter = splitter

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

        # Restore splitter ratio from settings if available
        sizes = None
        if self.settings_manager:
            ratio = self.settings_manager.get("my_characters_splitter_ratio", None)
            if isinstance(ratio, (list, tuple)) and len(ratio) == 2:
                sizes = ratio
        if sizes:
            splitter.setSizes(sizes)
        else:
            splitter.setSizes([280, 780])

        splitter.splitterMoved.connect(self._on_splitter_moved)

        layout.addWidget(splitter)

    def _on_splitter_moved(self, pos, index):
        if self.settings_manager and self._splitter:
            sizes = self._splitter.sizes()
            self.settings_manager.set("my_characters_splitter_ratio", sizes)

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
