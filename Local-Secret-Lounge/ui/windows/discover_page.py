from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QGridLayout, QSizePolicy,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont

from core.character_manager import CharacterManager
from ui.widgets.avatar_label import AvatarLabel
from ui.widgets.character_image import CharacterImage

logger = logging.getLogger(__name__)


class CharacterCard(QFrame):
    """Card widget representing a single character in the discover grid."""

    chat_requested = Signal(dict)

    def __init__(self, character: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.character = character
        self.setObjectName("character_card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(220)
        # Expanding both dimensions so cards (and therefore the image inside)
        # scale with the window size — uniform with the chat window's image
        # pane behaviour.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_ui()
        self.setStyleSheet("""
            QFrame#character_card {
                background-color: #16213e;
                border: 1px solid #2a2a4a;
                border-radius: 10px;
                padding: 4px;
            }
            QFrame#character_card:hover {
                border: 1px solid #e94560;
                background-color: #1a1a3e;
            }
        """)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        # Avatar — scalable rounded rectangle that resizes with the card and
        # shows the whole image without cropping.
        avatar_row = QHBoxLayout()
        avatar_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar = CharacterImage(minimum_size=(180, 220))
        # Cap the portrait height so cards stay balanced in the grid even
        # in very wide windows.
        self.avatar.setMaximumHeight(360)
        name_color = str(self.character.get("name_color", "") or "")
        self.avatar.set_character(
            self.character.get("name", "?"),
            self.character.get("avatar_path", ""),
            name_color or "#e94560",
        )
        avatar_row.addWidget(self.avatar, stretch=1)
        layout.addLayout(avatar_row, stretch=1)

        # Name
        name = QLabel(self.character.get("name", "Unknown"))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        name.setFont(font)
        color = str(self.character.get("name_color", "") or "#ffffff")
        name.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(name)

        # Title / role
        title = str(self.character.get("title", "") or self.character.get("role", "") or "").strip()
        if title:
            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet("color: #d8d8f0; font-size: 11px; font-weight: bold;")
            layout.addWidget(title_lbl)

        # Description snippet
        desc = str(self.character.get("description", "") or "").strip()
        if desc:
            snippet = desc[:] 
            desc_lbl = QLabel(snippet)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #f0f0ff; font-size: 11px;")
            desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(desc_lbl)

        layout.addStretch()

        # Chat button
        btn = QPushButton("Chat")
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda: self.chat_requested.emit(self.character))
        layout.addWidget(btn)

    def mouseDoubleClickEvent(self, event) -> None:
        self.chat_requested.emit(self.character)
        super().mouseDoubleClickEvent(event)


class DiscoverPage(QWidget):
    """Discover Characters page — shows built-in and user characters in a grid."""

    chat_requested = Signal(dict)

    # Grid layout parameters
    _GRID_COLS = 4

    def __init__(self, character_manager: CharacterManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.character_manager = character_manager
        self._all_characters: list[dict[str, Any]] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #16213e; border-bottom: 1px solid #2a2a4a;")
        top_bar.setFixedHeight(60)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 8, 20, 8)

        heading = QLabel("Discover Characters")
        heading.setObjectName("heading")
        top_layout.addWidget(heading)

        top_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search characters…")
        self.search_input.setMinimumWidth(160)
        self.search_input.setMaximumWidth(320)
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._apply_filter)
        top_layout.addWidget(self.search_input)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setObjectName("secondary_btn")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self.refresh)
        top_layout.addWidget(refresh_btn)

        layout.addWidget(top_bar)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: #1a1a2e;")

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: #1a1a2e;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setContentsMargins(24, 24, 24, 24)
        # Give every column the same stretch weight so all cards are always
        # the same width, regardless of the aspect ratio of their image.
        for col in range(self._GRID_COLS):
            self.grid_layout.setColumnStretch(col, 1)
        # A sensible minimum column width keeps cards legible even on narrow
        # windows; columns above this minimum expand evenly.
        for col in range(self._GRID_COLS):
            self.grid_layout.setColumnMinimumWidth(col, 220)

        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)

        # Empty state label
        self.empty_label = QLabel("No characters found.\n\nAdd characters to data/discover_characters/ or data/characters/")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #c8c8e0; font-size: 14px;")
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

    def refresh(self) -> None:
        try:
            self._all_characters = self.character_manager.list_all_characters()
        except Exception as exc:
            logger.error("Failed to load characters: %s", exc)
            self._all_characters = []
        self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        if q:
            filtered = [
                c for c in self._all_characters
                if q in str(c.get("name", "")).lower()
                or q in str(c.get("description", "")).lower()
                or q in str(c.get("title", "")).lower()
                or any(q in str(t).lower() for t in c.get("tags", []))
            ]
        else:
            filtered = list(self._all_characters)
        self._render_grid(filtered)

    def _render_grid(self, characters: list[dict[str, Any]]) -> None:
        # Clear existing cards
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not characters:
            self.empty_label.show()
            return

        self.empty_label.hide()
        cols = self._GRID_COLS
        total_rows = (len(characters) + cols - 1) // cols

        # Add all character cards
        for idx, character in enumerate(characters):
            row, col = divmod(idx, cols)
            card = CharacterCard(character)
            card.chat_requested.connect(self.chat_requested.emit)
            self.grid_layout.addWidget(card, row, col)

        # Fill gaps in the last partial row with invisible placeholder widgets
        # so the column stretches on the final row still produce equal-width
        # columns (otherwise empty columns would collapse to zero and the
        # remaining cards would stretch to fill).
        last_row_count = len(characters) % cols
        if last_row_count:
            last_row = total_rows - 1
            for col in range(last_row_count, cols):
                placeholder = QWidget()
                placeholder.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Expanding,
                )
                # Match a card's minimum width so the placeholder reserves the
                # same column share as a real card.
                placeholder.setMinimumWidth(220)
                self.grid_layout.addWidget(placeholder, last_row, col)
