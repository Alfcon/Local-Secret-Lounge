from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QLineEdit,
    QMessageBox, QInputDialog, QFileDialog, QTextEdit, QDialog,
    QDialogButtonBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from core.chat_storage import ChatStorage

logger = logging.getLogger(__name__)


# ── Chat Preview Dialog (last 10 messages) ───────────────────────────────────

class ChatPreviewDialog(QDialog):
    """Shows the last 10 messages of a chat as they appear in the conversation."""

    def __init__(self, chat: dict[str, Any], chat_storage: ChatStorage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Preview — {chat.get('title', 'Chat')}")
        self.setMinimumSize(640, 520)
        self.setModal(True)
        self._build_ui(chat, chat_storage)

    def _build_ui(self, chat: dict[str, Any], chat_storage: ChatStorage) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        heading = QLabel(f"Last 10 messages — {chat.get('title', 'Chat')}")
        heading.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        layout.addWidget(heading)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet(
            "background-color: #12122a; color: #f0f0ff; "
            "border: 1px solid #3a3a5a; border-radius: 6px; font-size: 12px;"
        )
        layout.addWidget(self.text_area)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # Load last 10 messages
        try:
            full_chat = chat_storage.load_chat(str(chat.get("id", "")))
            messages = [
                m for m in full_chat.get("messages", [])
                if m.get("role") != "system"
            ]
            last_10 = messages[-10:]
            char_name = str(full_chat.get("character", {}).get("name", "Character"))
            user_name = str(full_chat.get("user_name", "") or "You").strip() or "You"
            lines = []
            for msg in last_10:
                role = str(msg.get("role", "user"))
                speaker = str(msg.get("speaker", "")).strip()
                if not speaker:
                    speaker = user_name if role == "user" else char_name
                content = str(msg.get("content", "")).strip()
                lines.append(f"[{speaker}]\n{content}\n")
            self.text_area.setPlainText("\n".join(lines) if lines else "No messages yet.")
        except Exception as exc:
            self.text_area.setPlainText(f"Could not load messages: {exc}")


# ── Chat List Item ────────────────────────────────────────────────────────────

class ChatListItem(QFrame):
    """Custom widget for a chat entry in the list."""

    def __init__(self, chat: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 10, 12, 10)

        title_row = QHBoxLayout()
        title_lbl = QLabel(str(chat.get("title", "Chat")))
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        date = str(chat.get("updated_at", "")).replace("T", " ")[:16]
        date_lbl = QLabel(date)
        date_lbl.setStyleSheet("color: #a8a8c8; font-size: 11px;")
        title_row.addWidget(date_lbl)
        layout.addLayout(title_row)

        meta_row = QHBoxLayout()
        char_name = str(chat.get("character_name", ""))
        msg_count = int(chat.get("message_count", 0))

        meta_lbl = QLabel(f"{char_name}  ·  {msg_count} messages")
        meta_lbl.setStyleSheet("color: #c8c8e0; font-size: 11px;")
        meta_row.addWidget(meta_lbl)
        meta_row.addStretch()
        layout.addLayout(meta_row)

        # Preview: show last message snippet
        preview_raw = str(chat.get("preview", "") or "")
        if preview_raw:
            snippet = preview_raw[:120] + ("…" if len(preview_raw) > 120 else "")
            preview_lbl = QLabel(snippet)
            preview_lbl.setStyleSheet("color: #b8b8d8; font-size: 11px; font-style: italic;")
            preview_lbl.setWordWrap(True)
            layout.addWidget(preview_lbl)


# ── My Chats Page ─────────────────────────────────────────────────────────────

class MyChatsPage(QWidget):
    """My Chats page — lists saved chats with action buttons."""

    resume_chat_requested = Signal(str)

    def __init__(self, chat_storage: ChatStorage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chat_storage = chat_storage
        self._chats: list[dict[str, Any]] = []
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

        heading = QLabel("My Chats")
        heading.setObjectName("heading")
        top_layout.addWidget(heading)
        top_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search chats…")
        self.search_input.setMinimumWidth(160)
        self.search_input.setMaximumWidth(320)
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._apply_filter)
        top_layout.addWidget(self.search_input)

        layout.addWidget(top_bar)

        # Chat list
        self.chat_list = QListWidget()
        self.chat_list.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_list.setSpacing(2)
        self.chat_list.setStyleSheet(
            "QListWidget { background-color: #1a1a2e; border: none; }"
            "QListWidget::item { background-color: transparent; border-bottom: 1px solid #2a2a4a; }"
            "QListWidget::item:selected { background-color: #0f3460; }"
            "QListWidget::item:hover { background-color: #1e1e40; }"
        )
        self.chat_list.itemDoubleClicked.connect(self._on_double_click)
        self.chat_list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.chat_list)

        # Action bar — Refresh, Open, Rename, Edit (preview), Export, Delete
        action_bar = QFrame()
        action_bar.setStyleSheet("background-color: #16213e; border-top: 1px solid #2a2a4a;")
        action_bar.setFixedHeight(52)
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(16, 8, 16, 8)
        action_layout.setSpacing(8)

        self.refresh_btn = QPushButton("↻  Refresh")
        self.refresh_btn.setObjectName("secondary_btn")
        self.refresh_btn.setFixedHeight(34)
        self.refresh_btn.clicked.connect(self.refresh)
        action_layout.addWidget(self.refresh_btn)

        self.open_btn = QPushButton("▶  Open")
        self.open_btn.setFixedHeight(34)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._on_open)
        action_layout.addWidget(self.open_btn)

        self.rename_btn = QPushButton("✎  Rename")
        self.rename_btn.setObjectName("secondary_btn")
        self.rename_btn.setFixedHeight(34)
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._on_rename)
        action_layout.addWidget(self.rename_btn)

        self.preview_btn = QPushButton("👁  Edit")
        self.preview_btn.setObjectName("secondary_btn")
        self.preview_btn.setFixedHeight(34)
        self.preview_btn.setEnabled(False)
        self.preview_btn.clicked.connect(self._on_preview)
        action_layout.addWidget(self.preview_btn)

        self.export_btn = QPushButton("⬇  Export")
        self.export_btn.setObjectName("secondary_btn")
        self.export_btn.setFixedHeight(34)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        action_layout.addWidget(self.export_btn)

        action_layout.addStretch()

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setObjectName("danger_btn")
        self.delete_btn.setFixedHeight(34)
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        action_layout.addWidget(self.delete_btn)

        layout.addWidget(action_bar)

        # Empty state
        self.empty_label = QLabel("No saved chats yet.\n\nStart a chat from the Discover Characters page.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #c8c8e0; font-size: 14px; padding: 40px;")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)
        self.empty_label.hide()

    def refresh(self) -> None:
        try:
            self._chats = self.chat_storage.list_chats()
        except Exception as exc:
            logger.error("Failed to load chats: %s", exc)
            self._chats = []
        self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        if q:
            filtered = [
                c for c in self._chats
                if q in str(c.get("title", "")).lower()
                or q in str(c.get("character_name", "")).lower()
                or q in str(c.get("preview", "")).lower()
            ]
        else:
            filtered = list(self._chats)
        self._populate_list(filtered)

    def _populate_list(self, chats: list[dict[str, Any]]) -> None:
        self.chat_list.clear()
        self._filtered = chats

        if not chats:
            self.empty_label.show()
            self._set_buttons_enabled(False)
            return

        self.empty_label.hide()
        for chat in chats:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, chat)
            widget = ChatListItem(chat)
            item.setSizeHint(widget.sizeHint())
            self.chat_list.addItem(item)
            self.chat_list.setItemWidget(item, widget)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn in (self.open_btn, self.rename_btn, self.preview_btn,
                    self.export_btn, self.delete_btn):
            btn.setEnabled(enabled)

    def _on_selection_changed(self, row: int) -> None:
        self._set_buttons_enabled(row >= 0)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        chat = item.data(Qt.ItemDataRole.UserRole)
        if chat:
            self.resume_chat_requested.emit(str(chat.get("id", "")))

    def _on_open(self) -> None:
        item = self.chat_list.currentItem()
        if item:
            chat = item.data(Qt.ItemDataRole.UserRole)
            if chat:
                self.resume_chat_requested.emit(str(chat.get("id", "")))

    def _on_rename(self) -> None:
        item = self.chat_list.currentItem()
        if not item:
            return
        chat = item.data(Qt.ItemDataRole.UserRole)
        if not chat:
            return
        current_title = str(chat.get("title", ""))
        new_title, ok = QInputDialog.getText(
            self, "Rename Chat", "New title:", text=current_title
        )
        if ok and new_title.strip():
            try:
                self.chat_storage.rename_chat(str(chat.get("id", "")), new_title.strip())
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Rename Failed", str(exc))

    def _on_preview(self) -> None:
        """Open preview dialog showing the last 10 messages."""
        item = self.chat_list.currentItem()
        if not item:
            return
        chat = item.data(Qt.ItemDataRole.UserRole)
        if not chat:
            return
        dlg = ChatPreviewDialog(chat, self.chat_storage, parent=self)
        dlg.exec()

    def _on_export(self) -> None:
        """Export the selected chat as a .md file."""
        item = self.chat_list.currentItem()
        if not item:
            return
        chat = item.data(Qt.ItemDataRole.UserRole)
        if not chat:
            return
        title = str(chat.get("title", "chat")).strip()
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip()
        default_name = f"{safe_title or 'chat'}.md"
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chat as Markdown",
            str(Path.home() / default_name),
            "Markdown Files (*.md);;All Files (*)",
        )
        if not export_path:
            return
        if not export_path.lower().endswith(".md"):
            export_path += ".md"
        try:
            self.chat_storage.export_transcript(
                str(chat.get("id", "")),
                export_path,
                format="md",
            )
            QMessageBox.information(self, "Export Complete", f"Chat exported to:\n{export_path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))

    def _on_delete(self) -> None:
        item = self.chat_list.currentItem()
        if not item:
            return
        chat = item.data(Qt.ItemDataRole.UserRole)
        if not chat:
            return
        title = str(chat.get("title", "this chat"))
        reply = QMessageBox.question(
            self,
            "Delete Chat",
            f"Delete '{title}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.chat_storage.delete_chat(str(chat.get("id", "")))
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Delete Failed", str(exc))
