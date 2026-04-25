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

        # Make LM Studio and Ollama sections mutually exclusive in the UI
        self.lm_section.checked.connect(lambda checked: self.ollama_section.set_checked(False) if checked else None)
        self.ollama_section.checked.connect(lambda checked: self.lm_section.set_checked(False) if checked else None)


        local_llm_widget = QWidget()
        local_llm_widget.setLayout(local_llm_layout)
        local_llm_section.set_content_widget(local_llm_widget)
        layout.addWidget(local_llm_section)


        # ── Hardware Advisor ───────────────────────────────────────────
        from ui.widgets.hardware_advisor_widget import HardwareAdvisorWidget
        self.hardware_advisor = HardwareAdvisorWidget(model_manager=self.model_manager, parent=self)
        layout.addWidget(self.hardware_advisor)

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

        # ── Application Updates ───────────────────────────────────────────
        updates_section = CollapsibleSection("Application Updates")
        updates_form = QFormLayout()
        updates_form.setHorizontalSpacing(24)
        updates_form.setVerticalSpacing(12)

        self.update_app_btn = QPushButton("Pull Latest Updates")
        self.update_app_btn.setToolTip("Update the app to the latest version while keeping your user-created character files safe.")
        self.update_app_btn.setFixedHeight(34)
        self.update_app_btn.clicked.connect(self._pull_latest_updates)
        updates_form.addRow("Update App:", self.update_app_btn)

        self.about_app_btn = QPushButton("About Application")
        self.about_app_btn.setFixedHeight(34)
        self.about_app_btn.clicked.connect(self._show_about_dialog)
        updates_form.addRow("About:", self.about_app_btn)

        updates_widget = QWidget()
        updates_widget.setLayout(updates_form)
        updates_section.set_content_widget(updates_widget)
        layout.addWidget(updates_section)

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

        self._refresh_backend_status()

    def _save_all(self) -> None:
        sm = self.settings_manager
        new_font_size = int(self.font_size_spin.value())
        
        backend_preference = "local"
        if self.lm_section.is_checked():
            backend_preference = "lm_studio"
        elif self.ollama_section.is_checked():
            backend_preference = "ollama"

        sm.update({
            "user_name": self.user_name_input.text().strip(),
            "user_sex": self.user_sex_combo.currentText(),
            "lm_studio_base_url": self.lm_url_input.text().strip() or "http://127.0.0.1:1234/v1",
            "lm_studio_api_key": self.lm_api_key_input.text().strip(),
            "lm_studio_model_id": self.lm_model_input.text().strip(),
            "lm_studio_timeout_seconds": self.lm_timeout_spin.value(),
            "ollama_base_url": self.ollama_url_input.text().strip() or "http://127.0.0.1:11434/v1",
            "ollama_api_key": self.ollama_api_key_input.text().strip(),
            "ollama_model_id": self.ollama_model_input.text().strip(),
            "ollama_timeout_seconds": self.ollama_timeout_spin.value(),
            "chat_backend_preference": backend_preference,
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

            # Persist the resolved model
            self.settings_manager.update({
                "ollama_base_url": url,
                "ollama_api_key": api_key,
                "ollama_model_id": active_model_id,
                "ollama_enabled": True,
            })

            # Sync the UI to reflect the now-active model
            self.ollama_model_input.setText(active_model_id)

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

    def _pull_latest_updates(self) -> None:
        import subprocess
        try:
            # Stash any local changes to tracked files (e.g. user characters)
            subprocess.run(["git", "stash", "push", "-m", "Auto stash before update"], check=False, capture_output=True)
            
            # Pull the latest updates via rebase to avoid unnecessary merge commits
            result = subprocess.run(["git", "pull", "--rebase"], check=True, capture_output=True, text=True)
            
            # Try to pop the stashed changes back into the working tree
            subprocess.run(["git", "stash", "pop"], check=False, capture_output=True)
            
            QMessageBox.information(
                self,
                "Update Successful",
                f"Application updated successfully!\n\n{result.stdout.strip()}\n\nPlease restart the application to apply the changes."
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Update failed: %s", exc.stderr)
            
            # Try to restore user changes if pull failed
            subprocess.run(["git", "stash", "pop"], check=False, capture_output=True)
            
            QMessageBox.warning(
                self,
                "Update Failed",
                f"Failed to pull latest updates.\n\n{exc.stderr}"
            )
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "Git Not Found",
                "Git is not installed or not in your system PATH."
            )
        except Exception as exc:
            logger.error("Unexpected error during update: %s", exc)
            QMessageBox.warning(
                self,
                "Update Error",
                f"An unexpected error occurred:\n\n{exc}"
            )

    def _show_about_dialog(self) -> None:
        about_text = (
            "<h3>Local Secret Lounge</h3>"
            "<p><b>Version 1.0.0</b></p>"
            "<p>Local Secret Lounge is an immersive roleplay chat application designed "
            "to connect you with AI characters locally. It features advanced memory "
            "retrieval, narrative scene tracking, persistent multi-user chats, and "
            "real-time streaming powered by your local LLM server (LM Studio or Ollama).</p>"
        )
        QMessageBox.about(self, "About Local Secret Lounge", about_text)

