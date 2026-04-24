from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QSpinBox, QCheckBox,
    QScrollArea, QGroupBox, QFormLayout, QTabWidget,
    QSizePolicy, QMessageBox, QFileDialog, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView,
)
from PySide6.QtCore import Qt, Signal

from core.settings_manager import SettingsManager
from core.model_manager import ModelManager
from ui.widgets.system_info_widget import SystemInfoWidget
from ui.widgets.collapsible_section import CollapsibleSection

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """Settings page: user profile, backend selection, model management, LM Studio."""

    settings_changed = Signal()

    def __init__(
        self,
        settings_manager: SettingsManager,
        model_manager: ModelManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.model_manager = model_manager
        self._build_ui()
        self._load_values()

        try:
            self.model_manager.add_default_changed_listener(
                self._on_default_model_changed
            )
        except AttributeError:
            logger.debug(
                "ModelManager has no add_default_changed_listener; "
                "model list will not auto-refresh on default change."
            )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Top bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #16213e; border-bottom: 1px solid #2a2a4a;")
        top_bar.setFixedHeight(60)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 8, 20, 8)
        heading = QLabel("Settings")
        heading.setObjectName("heading")
        top_layout.addWidget(heading)
        top_layout.addStretch()
        save_btn = QPushButton("💾  Save Settings")
        save_btn.setFixedHeight(34)
        save_btn.clicked.connect(self._save_all)
        top_layout.addWidget(save_btn)
        outer.addWidget(top_bar)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background-color: #1a1a2e;")
        layout = QVBoxLayout(content)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 24, 0, 32)

        # ── User Profile ──────────────────────────────────────────────────
        profile_section = CollapsibleSection("User Profile")
        profile_form = QFormLayout()
        profile_form.setHorizontalSpacing(24)
        profile_form.setVerticalSpacing(12)

        self.user_name_input = QLineEdit()
        self.user_name_input.setPlaceholderText("Your name (used by characters)")
        self.user_name_input.setFixedHeight(34)
        profile_form.addRow("Your Name:", self.user_name_input)

        self.user_sex_combo = QComboBox()
        self.user_sex_combo.addItems(["Male", "Female", "Other"])
        self.user_sex_combo.setFixedHeight(34)
        profile_form.addRow("Your Sex:", self.user_sex_combo)

        profile_widget = QWidget()
        profile_widget.setLayout(profile_form)
        profile_section.set_content_widget(profile_widget)
        layout.addWidget(profile_section)

        # ── Story / Scene context ─────────────────────────────────────────
        story_section = CollapsibleSection("Story Location (Optional)")
        story_form = QFormLayout()
        story_form.setHorizontalSpacing(24)
        story_form.setVerticalSpacing(12)

        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("e.g. London")
        self.city_input.setFixedHeight(34)
        story_form.addRow("City:", self.city_input)

        self.country_input = QLineEdit()
        self.country_input.setPlaceholderText("e.g. United Kingdom")
        self.country_input.setFixedHeight(34)
        story_form.addRow("Country:", self.country_input)

        story_widget = QWidget()
        story_widget.setLayout(story_form)
        story_section.set_content_widget(story_widget)
        layout.addWidget(story_section)

        # ── Local LLM Server ──────────────────────────────────────────────
        local_llm_section = CollapsibleSection("Local LLM Server")
        local_llm_layout = QVBoxLayout()
        local_llm_layout.setSpacing(16)

        # ── LM Studio ────────────────────────────────────────────────────
        self.lm_section = CollapsibleSection("LM Studio Local Server", checkable=True)
        lm_form = QFormLayout()
        lm_form.setHorizontalSpacing(24)
        lm_form.setVerticalSpacing(12)

        self.lm_url_input = QLineEdit()
        self.lm_url_input.setPlaceholderText("http://127.0.0.1:1234/v1")
        self.lm_url_input.setFixedHeight(34)
        lm_form.addRow("Base URL:", self.lm_url_input)

        self.lm_api_key_input = QLineEdit()
        self.lm_api_key_input.setPlaceholderText("Leave blank if not required")
        self.lm_api_key_input.setFixedHeight(34)
        lm_form.addRow("API Key:", self.lm_api_key_input)

        self.lm_model_input = QLineEdit()
        self.lm_model_input.setPlaceholderText("Optional preferred model id")
        self.lm_model_input.setFixedHeight(34)
        lm_form.addRow("Model ID:", self.lm_model_input)

        self.lm_timeout_spin = QSpinBox()
        self.lm_timeout_spin.setRange(0, 3600)
        self.lm_timeout_spin.setSuffix(" s  (0 = no limit)")
        self.lm_timeout_spin.setFixedHeight(34)
        lm_form.addRow("Timeout:", self.lm_timeout_spin)

        # Active model ID — shown only when lm_studio backend is selected
        self.lm_active_model_label = QLabel("")
        self.lm_active_model_label.setWordWrap(True)
        self.lm_active_model_label.setStyleSheet(
            "color: #4caf50; font-size: 11px; padding: 4px 0px;"
        )
        self.lm_active_model_label.setVisible(False)
        lm_form.addRow("Active Model:", self.lm_active_model_label)

        test_btn = QPushButton("Test LM Studio Connection")
        test_btn.setObjectName("secondary_btn")
        test_btn.setFixedHeight(32)
        test_btn.clicked.connect(self._test_lm_studio)
        lm_form.addRow("", test_btn)

        lm_widget = QWidget()
        lm_widget.setLayout(lm_form)
        self.lm_section.set_content_widget(lm_widget)
        local_llm_layout.addWidget(self.lm_section)

        # ── Ollama ────────────────────────────────────────────────────────
        self.ollama_section = CollapsibleSection("Ollama Local Server", checkable=True)
        ollama_form = QFormLayout()
        ollama_form.setHorizontalSpacing(24)
        ollama_form.setVerticalSpacing(12)

        self.ollama_url_input = QLineEdit()
        self.ollama_url_input.setPlaceholderText("http://127.0.0.1:11434/v1")
        self.ollama_url_input.setFixedHeight(34)
        self.ollama_url_input.editingFinished.connect(lambda: self._refresh_ollama_models(silent=True))
        ollama_form.addRow("Base URL:", self.ollama_url_input)

        self.ollama_api_key_input = QLineEdit()
        self.ollama_api_key_input.setPlaceholderText("Leave blank if not required")
        self.ollama_api_key_input.setFixedHeight(34)
        ollama_form.addRow("API Key:", self.ollama_api_key_input)

        ollama_model_layout = QHBoxLayout()
        ollama_model_layout.setContentsMargins(0, 0, 0, 0)
        self.ollama_model_input = QLineEdit()
        self.ollama_model_input.setPlaceholderText("Optional preferred model id")
        self.ollama_model_input.setFixedHeight(34)
        ollama_model_layout.addWidget(self.ollama_model_input)

        self.ollama_refresh_models_btn = QPushButton("↻ Refresh")
        self.ollama_refresh_models_btn.setFixedHeight(34)
        self.ollama_refresh_models_btn.clicked.connect(self._refresh_ollama_models)
        ollama_model_layout.addWidget(self.ollama_refresh_models_btn)

        ollama_form.addRow("Model ID:", ollama_model_layout)

        self.ollama_model_list = QComboBox()
        self.ollama_model_list.setFixedHeight(34)
        self.ollama_model_list.addItem("— select an installed model —")
        self.ollama_model_list.currentIndexChanged.connect(self._on_ollama_model_selected)
        ollama_form.addRow("Available:", self.ollama_model_list)

        self.ollama_timeout_spin = QSpinBox()
        self.ollama_timeout_spin.setRange(0, 3600)
        self.ollama_timeout_spin.setSuffix(" s  (0 = no limit)")
        self.ollama_timeout_spin.setFixedHeight(34)
        ollama_form.addRow("Timeout:", self.ollama_timeout_spin)

        self.ollama_active_model_label = QLabel("")
        self.ollama_active_model_label.setWordWrap(True)
        self.ollama_active_model_label.setStyleSheet(
            "color: #4caf50; font-size: 11px; padding: 4px 0px;"
        )
        self.ollama_active_model_label.setVisible(False)
        ollama_form.addRow("Active Model:", self.ollama_active_model_label)

        ollama_test_btn = QPushButton("Connect & Set Active Model")
        ollama_test_btn.setObjectName("secondary_btn")
        ollama_test_btn.setFixedHeight(32)
        ollama_test_btn.clicked.connect(self._test_ollama)
        ollama_form.addRow("", ollama_test_btn)

        ollama_widget = QWidget()
        ollama_widget.setLayout(ollama_form)
        self.ollama_section.set_content_widget(ollama_widget)
        local_llm_layout.addWidget(self.ollama_section)


        # ── System & Model Advisor ────────────────────────────────────────
        # Small card above the Local GGUF Models section that shows the
        # user's CPU / RAM / GPU (VRAM) and recommended settings based on
        # their hardware and the currently-default model.
        advisor_section = CollapsibleSection("System & Model Advisor")
        self.system_info_widget = SystemInfoWidget(model_manager=self.model_manager)
        advisor_section.set_content_widget(self.system_info_widget)
        layout.addWidget(advisor_section)

        # ── Local Models ──────────────────────────────────────────────────
        self.models_section = CollapsibleSection("Local GGUF Models", checkable=True)
        models_layout = QVBoxLayout()
        models_layout.setSpacing(10)

        self.models_table = QTableWidget()
        self.models_table.setColumnCount(3)
        self.models_table.setHorizontalHeaderLabels(["Name", "Size (MB)", "Status"])
        self.models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.models_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.models_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.models_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.models_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.models_table.verticalHeader().setVisible(False)
        self.models_table.itemSelectionChanged.connect(self._on_model_selection_changed)
        self.models_table.setFixedHeight(200)
        models_layout.addWidget(self.models_table)

        models_btn_row = QHBoxLayout()
        import_btn = QPushButton("Import GGUF Model…")
        import_btn.setObjectName("secondary_btn")
        import_btn.setFixedHeight(32)
        import_btn.clicked.connect(self._import_model)
        models_btn_row.addWidget(import_btn)

        self.set_default_model_btn = QPushButton("Set Default")
        self.set_default_model_btn.setObjectName("secondary_btn")
        self.set_default_model_btn.setFixedHeight(32)
        self.set_default_model_btn.setEnabled(False)
        self.set_default_model_btn.clicked.connect(self._set_selected_model_default)
        models_btn_row.addWidget(self.set_default_model_btn)

        self.delete_model_btn = QPushButton("Delete")
        self.delete_model_btn.setObjectName("danger_btn")
        self.delete_model_btn.setFixedHeight(32)
        self.delete_model_btn.setEnabled(False)
        self.delete_model_btn.clicked.connect(self._delete_selected_model)
        models_btn_row.addWidget(self.delete_model_btn)

        refresh_models_btn = QPushButton("↻ Refresh Models")
        refresh_models_btn.setObjectName("secondary_btn")
        refresh_models_btn.setFixedHeight(32)
        refresh_models_btn.clicked.connect(self._refresh_models)
        models_btn_row.addWidget(refresh_models_btn)
        models_layout.addLayout(models_btn_row)

        models_widget = QWidget()
        models_widget.setLayout(models_layout)
        self.models_section.set_content_widget(models_widget)
        local_llm_layout.addWidget(self.models_section)

        local_llm_widget = QWidget()
        local_llm_widget.setLayout(local_llm_layout)
        local_llm_section.set_content_widget(local_llm_widget)
        layout.addWidget(local_llm_section)


        # ── Generation Defaults ───────────────────────────────────────────
        gen_section = CollapsibleSection("Default Generation Settings")
        gen_form = QFormLayout()
        gen_form.setHorizontalSpacing(24)
        gen_form.setVerticalSpacing(12)

        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(256, 131072)
        self.ctx_spin.setSingleStep(256)
        self.ctx_spin.setFixedHeight(34)
        gen_form.addRow("Context Size:", self.ctx_spin)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 64)
        self.threads_spin.setFixedHeight(34)
        gen_form.addRow("CPU Threads:", self.threads_spin)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(32, 8192)
        self.max_tokens_spin.setSingleStep(64)
        self.max_tokens_spin.setFixedHeight(34)
        gen_form.addRow("Max Tokens:", self.max_tokens_spin)

        gen_widget = QWidget()
        gen_widget.setLayout(gen_form)
        gen_section.set_content_widget(gen_widget)
        layout.addWidget(gen_section)

        # ── Appearance ────────────────────────────────────────────────────
        appearance_section = CollapsibleSection("Appearance")
        appearance_form = QFormLayout()
        appearance_form.setHorizontalSpacing(24)
        appearance_form.setVerticalSpacing(12)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(9, 28)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setFixedHeight(34)
        self.font_size_spin.setToolTip(
            "Base font size for the entire application. Takes effect immediately "
            "when Save Settings is pressed."
        )
        appearance_form.addRow("Font Size:", self.font_size_spin)

        appearance_widget = QWidget()
        appearance_widget.setLayout(appearance_form)
        appearance_section.set_content_widget(appearance_widget)
        layout.addWidget(appearance_section)

        # ── Startup ───────────────────────────────────────────────────────
        startup_section = CollapsibleSection("Startup")
        startup_form = QFormLayout()
        startup_form.setHorizontalSpacing(24)
        startup_form.setVerticalSpacing(12)

        self.startup_combo = QComboBox()
        self.startup_combo.addItems(["discover", "my_characters", "my_chats"])
        self.startup_combo.setFixedHeight(34)
        startup_form.addRow("Open on launch:", self.startup_combo)

        self.offline_check = QCheckBox("Offline Mode (disable all network features)")
        startup_form.addRow("", self.offline_check)

        self.developer_mode_check = QCheckBox(
            "Developer Mode (show live character-state popup during chat)"
        )
        self.developer_mode_check.setToolTip(
            "When enabled, a floating window opens alongside the chat and shows the "
            "active character's emotional baseline, relationship stats, scene flags, "
            "recent memory, and a derived reaction summary. Useful for debugging "
            "character behaviour and prompt tuning."
        )
        startup_form.addRow("", self.developer_mode_check)

        startup_widget = QWidget()
        startup_widget.setLayout(startup_form)
        startup_section.set_content_widget(startup_widget)
        layout.addWidget(startup_section)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _load_values(self) -> None:
        sm = self.settings_manager

        self.user_name_input.setText(sm.get_user_name())
        sex = sm.get_user_sex()
        idx = self.user_sex_combo.findText(sex, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.user_sex_combo.setCurrentIndex(idx)

        self.city_input.setText(str(sm.get("story_location_city", "") or ""))
        self.country_input.setText(str(sm.get("story_location_country", "") or ""))

        self.lm_url_input.setText(str(sm.get("lm_studio_base_url", "http://127.0.0.1:1234/v1") or ""))
        self.lm_api_key_input.setText(str(sm.get("lm_studio_api_key", "") or ""))
        self.lm_model_input.setText(str(sm.get("lm_studio_model_id", "") or ""))
        self.lm_timeout_spin.setValue(int(sm.get("lm_studio_timeout_seconds", 0) or 0))

        self.ollama_url_input.setText(str(sm.get("ollama_base_url", "http://127.0.0.1:11434/v1") or ""))
        self.ollama_api_key_input.setText(str(sm.get("ollama_api_key", "") or ""))
        self.ollama_model_input.setText(str(sm.get("ollama_model_id", "") or ""))
        self.ollama_timeout_spin.setValue(int(sm.get("ollama_timeout_seconds", 0) or 0))
        self._refresh_ollama_models(silent=True)

        self.ctx_spin.setValue(int(sm.get("default_context_size", 4096) or 4096))
        self.threads_spin.setValue(int(sm.get("default_threads", 4) or 4))
        self.max_tokens_spin.setValue(int(sm.get("default_max_tokens", 384) or 384))

        startup = str(sm.get("startup_page", "discover") or "discover")
        idx = self.startup_combo.findText(startup, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.startup_combo.setCurrentIndex(idx)

        self.offline_check.setChecked(bool(sm.is_offline_mode()))

        self.developer_mode_check.setChecked(bool(sm.is_developer_mode()))

        try:
            font_size = int(sm.get("ui_font_size", 13) or 13)
        except (TypeError, ValueError):
            font_size = 13
        # Clamp to spinbox range to avoid Qt warnings on out-of-range values.
        font_size = max(9, min(28, font_size))
        self.font_size_spin.setValue(font_size)

        self._refresh_models()
        self._refresh_backend_status()

    def _save_all(self) -> None:
        sm = self.settings_manager
        new_font_size = int(self.font_size_spin.value())
        sm.update({
            "user_name": self.user_name_input.text().strip(),
            "user_sex": self.user_sex_combo.currentText(),
            "story_location_city": self.city_input.text().strip(),
            "story_location_country": self.country_input.text().strip(),
            "lm_studio_base_url": self.lm_url_input.text().strip() or "http://127.0.0.1:1234/v1",
            "lm_studio_api_key": self.lm_api_key_input.text().strip(),
            "lm_studio_model_id": self.lm_model_input.text().strip(),
            "lm_studio_timeout_seconds": self.lm_timeout_spin.value(),
            "ollama_base_url": self.ollama_url_input.text().strip() or "http://127.0.0.1:11434/v1",
            "ollama_api_key": self.ollama_api_key_input.text().strip(),
            "ollama_model_id": self.ollama_model_input.text().strip(),
            "ollama_timeout_seconds": self.ollama_timeout_spin.value(),
            "default_context_size": self.ctx_spin.value(),
            "default_threads": self.threads_spin.value(),
            "default_max_tokens": self.max_tokens_spin.value(),
            "startup_page": self.startup_combo.currentText(),
            "offline_mode": self.offline_check.isChecked(),
            "developer_mode": self.developer_mode_check.isChecked(),
            "ui_font_size": new_font_size,
        })

        # Re-apply the global stylesheet so the new font size is visible
        # immediately, without requiring a restart.
        try:
            from PySide6.QtWidgets import QApplication
            from ui.theme import apply_theme
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, font_size=new_font_size)
        except Exception as exc:  # noqa: BLE001 - defensive; never block save
            logger.warning("Live font-size re-apply failed: %s", exc)

        self.settings_changed.emit()
        QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")

    def _on_default_model_changed(self, model_id: str | None = None) -> None:  # noqa: ARG002
        """Invoked by ModelManager whenever the default local model changes.

        Refreshes the backend status card so the user sees the new model
        reflected immediately, and repaints the model list so the '[default]'
        marker moves without a manual Refresh click.
        """
        try:
            self._refresh_backend_status()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Backend auto-refresh failed: %s", exc)
        try:
            # Re-render list so the [default] marker and advisor follow along.
            self._refresh_models()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Model list auto-refresh failed: %s", exc)

    def _refresh_backend_status(self) -> None:
        try:
            from core.chat_backend import get_chat_backend_preference, get_preferred_chat_model
            backend = get_chat_backend_preference(self.settings_manager)
            if backend == "lm_studio":
                model_entry, err = get_preferred_chat_model(
                    self.settings_manager, self.model_manager
                )
                if model_entry is not None:
                    active_id = str(
                        model_entry.get("lm_studio_model_id")
                        or model_entry.get("name", "")
                    )
                    self.lm_active_model_label.setText(active_id)
                    self.lm_active_model_label.setStyleSheet(
                        "color: #4caf50; font-size: 11px; padding: 4px 0px;"
                    )
                else:
                    self.lm_active_model_label.setText(err or "No model loaded")
                    self.lm_active_model_label.setStyleSheet(
                        "color: #e94560; font-size: 11px; padding: 4px 0px;"
                    )
                self.lm_active_model_label.setVisible(True)
                self.ollama_active_model_label.setVisible(False)
            elif backend == "ollama":
                model_entry, err = get_preferred_chat_model(
                    self.settings_manager, self.model_manager
                )
                if model_entry is not None:
                    active_id = str(
                        model_entry.get("ollama_model_id")
                        or model_entry.get("name", "")
                    )
                    self.ollama_active_model_label.setText(active_id)
                    self.ollama_active_model_label.setStyleSheet(
                        "color: #4caf50; font-size: 11px; padding: 4px 0px;"
                    )
                else:
                    self.ollama_active_model_label.setText(err or "No model loaded")
                    self.ollama_active_model_label.setStyleSheet(
                        "color: #e94560; font-size: 11px; padding: 4px 0px;"
                    )
                self.ollama_active_model_label.setVisible(True)
                self.lm_active_model_label.setVisible(False)
            else:
                self.lm_active_model_label.setVisible(False)
                self.ollama_active_model_label.setVisible(False)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).debug("LM Studio active model label refresh failed: %s", exc)
            self.lm_active_model_label.setVisible(False)

    def _refresh_models(self) -> None:
        try:
            models = self.model_manager.reload_registry()
        except Exception as exc:
            logger.error("Model refresh failed: %s", exc)
            models = []
            
        self.models_table.setRowCount(0)
        self.models_table.setRowCount(len(models))
        
        for row, m in enumerate(models):
            status = str(m.get("status", ""))
            status_icon = "✓" if status == "available" else "✗"
            name = m.get('name', 'Unknown')
            default_mark = " [default]" if m.get("is_default") else ""
            
            name_item = QTableWidgetItem(f"{name}{default_mark}")
            name_item.setData(Qt.UserRole, m.get("id"))
            
            size_mb = int(m.get("size_bytes", 0) or 0) // (1024 * 1024)
            size_item = QTableWidgetItem(f"{size_mb}")
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            status_item = QTableWidgetItem(status_icon)
            status_item.setTextAlignment(Qt.AlignCenter)
            
            self.models_table.setItem(row, 0, name_item)
            self.models_table.setItem(row, 1, size_item)
            self.models_table.setItem(row, 2, status_item)

        self.models_table.clearSelection()
        self._on_model_selection_changed()

        # Refresh the System & Model Advisor so recommendations reflect the
        # current default model (or the first available model as a fallback).
        self._refresh_system_advisor(models)

    def _on_model_selection_changed(self) -> None:
        has_selection = len(self.models_table.selectedItems()) > 0
        self.set_default_model_btn.setEnabled(has_selection)
        self.delete_model_btn.setEnabled(has_selection)

    def _set_selected_model_default(self) -> None:
        selected = self.models_table.selectedItems()
        if not selected:
            return
            
        row = selected[0].row()
        item = self.models_table.item(row, 0)
        model_id = str(item.data(Qt.UserRole))
        
        try:
            self.model_manager.set_default_model(model_id)
            self._refresh_models()
        except Exception as exc:
            logger.error("Failed to set default model: %s", exc)
            QMessageBox.warning(self, "Error", f"Failed to set default model:\n{exc}")

    def _delete_selected_model(self) -> None:
        selected = self.models_table.selectedItems()
        if not selected:
            return
            
        row = selected[0].row()
        item = self.models_table.item(row, 0)
        model_id = str(item.data(Qt.UserRole))
        
        reply = QMessageBox.question(
            self,
            "Delete Model",
            f"Are you sure you want to delete the model:\n{item.text()}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.model_manager.remove_model(model_id, delete_file=True, allow_external_delete=True)
                self._refresh_models()
            except Exception as exc:
                logger.error("Failed to delete model: %s", exc)
                QMessageBox.warning(self, "Error", f"Failed to delete model:\n{exc}")

    def _refresh_system_advisor(self, models: list[dict[str, Any]] | None = None) -> None:
        """Push the default model's id into the System & Model Advisor."""
        if getattr(self, "system_info_widget", None) is None:
            return
        if models is None:
            try:
                models = self.model_manager.list_models()
            except Exception:
                models = []

        target_id: str | None = None
        for m in models or []:
            if m.get("is_default") and str(m.get("status", "")) == "available":
                target_id = str(m.get("id")) if m.get("id") else None
                break
        if target_id is None:
            for m in models or []:
                if str(m.get("status", "")) == "available" and m.get("id"):
                    target_id = str(m.get("id"))
                    break

        try:
            self.system_info_widget.update_for_model(target_id)
        except Exception as exc:
            logger.warning("System advisor refresh failed: %s", exc)

    def _import_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GGUF Model File", "", "GGUF Models (*.gguf)"
        )
        if not path:
            return
        from pathlib import Path
        display_name = Path(path).stem
        try:
            self.model_manager.import_local_model(
                source_path=path,
                display_name=display_name,
                copy_to_managed_storage=False,
                set_default=True,
            )
            self._refresh_models()
            QMessageBox.information(self, "Model Imported", f"'{display_name}' was imported and set as default.")
        except Exception as exc:
            QMessageBox.warning(self, "Import Failed", str(exc))

    def _test_lm_studio(self) -> None:
        from core.lm_studio_client import LMStudioClient, LMStudioError
        url = self.lm_url_input.text().strip() or "http://127.0.0.1:1234/v1"
        api_key = self.lm_api_key_input.text().strip()
        try:
            client = LMStudioClient(base_url=url, api_key=api_key or None)
            models = client.list_models()
            names = [str(m.get("id", "")) for m in models[:5]]
            QMessageBox.information(
                self,
                "LM Studio Connected",
                f"Connection successful!\n\nAvailable models:\n" + "\n".join(names or ["(none loaded)"]),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Connection Failed", str(exc))

    def _test_ollama(self) -> None:
        from core.ollama_client import OllamaClient, OllamaError
        url = self.ollama_url_input.text().strip() or "http://127.0.0.1:11434/v1"
        api_key = self.ollama_api_key_input.text().strip()
        preferred_model = self.ollama_model_input.text().strip()
        try:
            client = OllamaClient(base_url=url, api_key=api_key or None)
            model_entry = client.resolve_model(preferred_model or None)
            active_model_id = str(model_entry.get("ollama_model_id", ""))

            # Persist the resolved model and activate the Ollama backend
            self.settings_manager.update({
                "ollama_base_url": url,
                "ollama_api_key": api_key,
                "ollama_model_id": active_model_id,
                "ollama_enabled": True,
                "chat_backend_preference": "ollama",
            })

            # Sync the UI to reflect the now-active model and backend
            self.ollama_model_input.setText(active_model_id)
            self._current_backend = "ollama"
            self._on_backend_changed("ollama")

            self.ollama_active_model_label.setText(active_model_id)
            self.ollama_active_model_label.setStyleSheet(
                "color: #4caf50; font-size: 11px; padding: 4px 0px;"
            )
            self.ollama_active_model_label.setVisible(True)

            # Highlight the active model in the dropdown
            self._refresh_ollama_models(silent=True)

            self.settings_changed.emit()
            QMessageBox.information(
                self,
                "Ollama Connected",
                f"Connection successful!\n\nActive model set to:\n{active_model_id}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Connection Failed", str(exc))

    def _on_ollama_model_selected(self, index: int) -> None:
        text = self.ollama_model_list.itemText(index)
        if text and not text.startswith("—"):
            self.ollama_model_input.setText(text)

    def _refresh_ollama_models(self, silent: bool = False) -> None:
        from core.ollama_client import OllamaClient
        url = self.ollama_url_input.text().strip() or "http://127.0.0.1:11434/v1"
        api_key = self.ollama_api_key_input.text().strip()
        try:
            client = OllamaClient(base_url=url, api_key=api_key or None, timeout_seconds=5.0)
            models = client.list_models()
            names = [str(m.get("id", "")) for m in models if m.get("id")]

            self.ollama_model_list.blockSignals(True)
            self.ollama_model_list.clear()
            if names:
                self.ollama_model_list.addItem("— select an installed model —")
                self.ollama_model_list.addItems(names)
                # If the current model ID is in the list, highlight it
                current = self.ollama_model_input.text().strip()
                if current in names:
                    self.ollama_model_list.setCurrentIndex(names.index(current) + 1)
            else:
                self.ollama_model_list.addItem("— no models found —")
            self.ollama_model_list.blockSignals(False)

            if not silent:
                model_list = "\n".join(names) if names else "(none found)"
                QMessageBox.information(
                    self,
                    "Ollama Models Refreshed",
                    f"Found {len(names)} model(s):\n\n{model_list}",
                )
        except Exception as exc:
            logger.debug("Ollama model refresh failed: %s", exc)
            if not silent:
                QMessageBox.warning(self, "Refresh Failed", f"Could not fetch models from Ollama:\n{exc}")
