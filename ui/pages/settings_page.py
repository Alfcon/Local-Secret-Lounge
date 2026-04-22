from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.lm_studio_client import LMStudioClient, LMStudioError
from core.paths import get_chats_dir, get_models_dir
from ui.widgets.model_manager_widget import ModelManagerWidget
from ui.widgets.system_info_widget import SystemInfoWidget


class SettingsPage(QWidget):
    settings_changed = Signal()
    models_changed = Signal()

    def __init__(self, settings_manager, model_manager) -> None:
        super().__init__()
        self.settings_manager = settings_manager
        self.model_manager = model_manager

        self.user_name_edit: QLineEdit | None = None
        self.story_city_edit: QLineEdit | None = None
        self.story_country_edit: QLineEdit | None = None
        self.user_sex_combo: QComboBox | None = None
        self.offline_checkbox: QCheckBox | None = None
        self.save_button: QPushButton | None = None
        self.model_manager_widget: ModelManagerWidget | None = None
        self.system_info_widget: SystemInfoWidget | None = None
        self.local_model_checkbox: QCheckBox | None = None
        self.active_local_model_label: QLabel | None = None
        self.lm_studio_checkbox: QCheckBox | None = None
        self.lm_studio_base_url_edit: QLineEdit | None = None
        self.lm_studio_api_key_edit: QLineEdit | None = None
        self.lm_studio_model_id_edit: QLineEdit | None = None
        self.lm_studio_timeout_spin: QSpinBox | None = None
        self.lm_status_label: QLabel | None = None
        self.lm_test_button: QPushButton | None = None

        self.build_ui()
        self.load_settings_into_ui()
        self.connect_signals()
        self.refresh_backend_selection_summary()
        self.refresh_lm_studio_status(show_popup=False)

    def build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(24, 24, 24, 24)
        outer_layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        outer_layout.addWidget(title)

        subtitle = QLabel("Manage your setup details, story location, local models, LM Studio Local Server, storage, and privacy options.")
        subtitle.setStyleSheet("color: #b8b0d7;")
        outer_layout.addWidget(subtitle)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 8)
        content_layout.setSpacing(16)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self.build_user_settings_tab(), 'User Settings')
        tabs.addTab(self.build_models_tab(), 'Models')
        tabs.addTab(self.build_other_options_tab(), 'Other Options')
        content_layout.addWidget(tabs)

        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)

    def build_section_card(self, title_text: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("sectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        return card, layout

    def build_tab_container(self) -> tuple[QWidget, QVBoxLayout]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        return container, layout

    def build_user_settings_tab(self) -> QWidget:
        container, layout = self.build_tab_container()
        layout.addWidget(self.build_general_section())
        layout.addStretch(1)
        return container

    def build_models_tab(self) -> QWidget:
        container, layout = self.build_tab_container()
        layout.addWidget(self.build_backend_section())
        layout.addWidget(self.build_lm_studio_section())
        layout.addWidget(self.build_system_info_section())
        layout.addWidget(self.build_models_section())
        layout.addStretch(1)
        return container

    def build_other_options_tab(self) -> QWidget:
        container, layout = self.build_tab_container()
        layout.addWidget(self.build_storage_section())
        layout.addWidget(self.build_privacy_section())
        layout.addStretch(1)
        return container

    def build_general_section(self) -> QWidget:
        card, layout = self.build_section_card("Setup")

        label = QLabel("Set the alias and sex that should be used for your in-chat identity.")
        label.setWordWrap(True)
        label.setStyleSheet("color: #c4bedf;")
        layout.addWidget(label)

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)

        self.user_name_edit = QLineEdit()
        self.user_name_edit.setPlaceholderText('Your preferred chat name')
        form.addRow('User display name:', self.user_name_edit)

        self.user_sex_combo = QComboBox()
        self.user_sex_combo.addItems(['', 'Male', 'Female', 'Non-binary', 'Other'])
        self.user_sex_combo.setEditable(False)
        form.addRow('Sex:', self.user_sex_combo)

        self.story_city_edit = QLineEdit()
        self.story_city_edit.setPlaceholderText('Town or city for the story setting')
        form.addRow('Story town / city:', self.story_city_edit)

        self.story_country_edit = QLineEdit()
        self.story_country_edit.setPlaceholderText('Country for the story setting')
        form.addRow('Story country:', self.story_country_edit)

        layout.addLayout(form)

        helper = QLabel('Your alias and sex are saved here for chat identity. Story location values are added to the prompt so chats can stay grounded in a chosen setting.')
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #8f98c2;")
        layout.addWidget(helper)

        return card


    def build_backend_section(self) -> QWidget:
        card, layout = self.build_section_card("Chat Backend")

        help_text = QLabel(
            "Choose which backend the app should use when you start chats. "
            "Tick the local option to use the highlighted GGUF model below. Tick LM Studio to use the Local Server."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #c4bedf;")
        layout.addWidget(help_text)

        self.local_model_checkbox = QCheckBox('Use selected local GGUF model for chats')
        layout.addWidget(self.local_model_checkbox)

        self.active_local_model_label = QLabel('Local model: no model selected yet.')
        self.active_local_model_label.setWordWrap(True)
        self.active_local_model_label.setStyleSheet('color: #9fa7d1;')
        layout.addWidget(self.active_local_model_label)

        return card

    def build_lm_studio_section(self) -> QWidget:
        card, layout = self.build_section_card('LM Studio Local Server')

        help_text = QLabel(
            'Enable this to use the LM Studio Local Server instead of the built-in GGUF runtime. '
            'The base URL should normally be http://127.0.0.1:1234/v1.'
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet('color: #c4bedf;')
        layout.addWidget(help_text)

        self.lm_studio_checkbox = QCheckBox('Use LM Studio Local Server for chats')
        layout.addWidget(self.lm_studio_checkbox)

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)

        self.lm_studio_base_url_edit = QLineEdit()
        self.lm_studio_base_url_edit.setPlaceholderText('http://127.0.0.1:1234/v1')
        form.addRow('Base URL:', self.lm_studio_base_url_edit)

        self.lm_studio_api_key_edit = QLineEdit()
        self.lm_studio_api_key_edit.setPlaceholderText('Optional API token')
        form.addRow('API token:', self.lm_studio_api_key_edit)

        self.lm_studio_model_id_edit = QLineEdit()
        self.lm_studio_model_id_edit.setPlaceholderText('Optional model id override')
        form.addRow('Preferred model id:', self.lm_studio_model_id_edit)

        self.lm_studio_timeout_spin = QSpinBox()
        self.lm_studio_timeout_spin.setRange(5, 1800)
        self.lm_studio_timeout_spin.setSingleStep(5)
        self.lm_studio_timeout_spin.setSuffix(' s')
        form.addRow('Timeout:', self.lm_studio_timeout_spin)

        layout.addLayout(form)

        status_row = QHBoxLayout()
        self.lm_status_label = QLabel('Connection status not checked yet.')
        self.lm_status_label.setWordWrap(True)
        self.lm_status_label.setStyleSheet('color: #b8b0d7;')
        status_row.addWidget(self.lm_status_label, stretch=1)

        self.lm_test_button = QPushButton('Test Connection')
        self.lm_test_button.clicked.connect(lambda: self.refresh_lm_studio_status(show_popup=True))
        status_row.addWidget(self.lm_test_button)
        layout.addLayout(status_row)

        return card

    def build_storage_section(self) -> QWidget:
        card, layout = self.build_section_card("Storage Paths")

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)

        models_path = QLabel(str(get_models_dir()))
        chats_path = QLabel(str(get_chats_dir()))
        models_path.setWordWrap(True)
        chats_path.setWordWrap(True)

        form.addRow("Models folder:", models_path)
        form.addRow("Chats folder:", chats_path)
        layout.addLayout(form)

        return card

    def build_system_info_section(self) -> QWidget:
        self.system_info_widget = SystemInfoWidget(model_manager=self.model_manager)
        return self.system_info_widget

    def build_models_section(self) -> QWidget:
        card, layout = self.build_section_card("Local GGUF Models")

        self.model_manager_widget = ModelManagerWidget(
            settings_manager=self.settings_manager,
            model_manager=self.model_manager,
        )
        self.model_manager_widget.models_changed.connect(self.models_changed.emit)
        self.model_manager_widget.table.itemSelectionChanged.connect(self._on_local_model_selection_changed)
        self.model_manager_widget.table.itemSelectionChanged.connect(self._refresh_system_advisor)
        layout.addWidget(self.model_manager_widget)

        return card

    def build_privacy_section(self) -> QWidget:
        card, layout = self.build_section_card("Privacy / Offline Mode")

        row = QHBoxLayout()
        self.offline_checkbox = QCheckBox("Enable offline mode")
        row.addWidget(self.offline_checkbox)
        row.addStretch(1)
        layout.addLayout(row)

        help_text = QLabel(
            "When offline mode is enabled, the app should only use already installed local models and cached resources."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #c4bedf;")
        layout.addWidget(help_text)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(lambda: self.save_ui_to_settings(show_popup=True))
        layout.addWidget(self.save_button)

        return card

    def load_settings_into_ui(self) -> None:
        if self.user_name_edit is not None:
            self.user_name_edit.setText(str(self.settings_manager.get('user_name', '') or ''))
        if self.user_sex_combo is not None:
            saved_sex = str(self.settings_manager.get('user_sex', '') or '')
            index = self.user_sex_combo.findText(saved_sex)
            self.user_sex_combo.setCurrentIndex(index if index >= 0 else 0)
        if self.story_city_edit is not None:
            self.story_city_edit.setText(str(self.settings_manager.get('story_location_city', '') or ''))
        if self.story_country_edit is not None:
            self.story_country_edit.setText(str(self.settings_manager.get('story_location_country', '') or ''))
        if self.offline_checkbox is not None:
            self.offline_checkbox.setChecked(self.settings_manager.is_offline_mode())
        backend_preference = self._current_backend_preference()
        if self.local_model_checkbox is not None:
            self.local_model_checkbox.setChecked(backend_preference == 'local')

        if self.lm_studio_checkbox is not None:
            self.lm_studio_checkbox.setChecked(backend_preference == 'lm_studio')
        if self.lm_studio_base_url_edit is not None:
            self.lm_studio_base_url_edit.setText(str(self.settings_manager.get('lm_studio_base_url', 'http://127.0.0.1:1234/v1') or ''))
        if self.lm_studio_api_key_edit is not None:
            self.lm_studio_api_key_edit.setText(str(self.settings_manager.get('lm_studio_api_key', '') or ''))
        if self.lm_studio_model_id_edit is not None:
            self.lm_studio_model_id_edit.setText(str(self.settings_manager.get('lm_studio_model_id', '') or ''))
        if self.lm_studio_timeout_spin is not None:
            self.lm_studio_timeout_spin.setValue(int(self.settings_manager.get('lm_studio_timeout_seconds', 300) or 300))
        self.refresh_backend_selection_summary()

    def save_ui_to_settings(self, show_popup: bool = False) -> None:
        updates: dict[str, object] = {}
        if self.user_name_edit is not None:
            updates['user_name'] = self.user_name_edit.text().strip()
        if self.user_sex_combo is not None:
            updates['user_sex'] = self.user_sex_combo.currentText().strip()
        if self.story_city_edit is not None:
            updates['story_location_city'] = self.story_city_edit.text().strip()
        if self.story_country_edit is not None:
            updates['story_location_country'] = self.story_country_edit.text().strip()
        if self.offline_checkbox is not None:
            updates['offline_mode'] = self.offline_checkbox.isChecked()
        backend_preference = 'local'
        if self.lm_studio_checkbox is not None and self.lm_studio_checkbox.isChecked():
            backend_preference = 'lm_studio'
        updates['chat_backend_preference'] = backend_preference

        updates['lm_studio_enabled'] = backend_preference == 'lm_studio'
        if self.lm_studio_base_url_edit is not None:
            updates['lm_studio_base_url'] = self.lm_studio_base_url_edit.text().strip() or 'http://127.0.0.1:1234/v1'
        if self.lm_studio_api_key_edit is not None:
            updates['lm_studio_api_key'] = self.lm_studio_api_key_edit.text().strip()
        if self.lm_studio_model_id_edit is not None:
            updates['lm_studio_model_id'] = self.lm_studio_model_id_edit.text().strip()
        if self.lm_studio_timeout_spin is not None:
            updates['lm_studio_timeout_seconds'] = int(self.lm_studio_timeout_spin.value())

        alias_value = str(updates.get('user_name', '') or '').strip()
        sex_value = str(updates.get('user_sex', '') or '').strip()
        updates['initial_setup_complete'] = bool(alias_value and sex_value)

        if backend_preference == 'local':
            selected_local_model_id = self.selected_local_model_id()
            if selected_local_model_id:
                updates['default_model_id'] = selected_local_model_id
        self.settings_manager.update(updates)
        self.refresh_backend_selection_summary()
        self.refresh_lm_studio_status(show_popup=False)
        self.settings_changed.emit()
        if show_popup:
            QMessageBox.information(self, "Settings saved", "Your settings have been saved.")

    def refresh_lm_studio_status(self, show_popup: bool = False) -> None:
        if self.lm_status_label is None:
            return
        enabled = self.lm_studio_checkbox.isChecked() if self.lm_studio_checkbox is not None else False
        if not enabled:
            self.lm_status_label.setText('LM Studio is configured here, but the selected local GGUF model is currently set as the chat backend.')
            if show_popup:
                QMessageBox.information(self, 'LM Studio', 'LM Studio is not the active chat backend right now.')
            return

        try:
            client = LMStudioClient(
                base_url=self.lm_studio_base_url_edit.text().strip() if self.lm_studio_base_url_edit is not None else 'http://127.0.0.1:1234/v1',
                api_key=self.lm_studio_api_key_edit.text().strip() if self.lm_studio_api_key_edit is not None else '',
                timeout_seconds=float(self.lm_studio_timeout_spin.value()) if self.lm_studio_timeout_spin is not None else 300.0,
            )
            preferred_model_id = self.lm_studio_model_id_edit.text().strip() if self.lm_studio_model_id_edit is not None else ''
            model_entry = client.resolve_model(preferred_model_id or None)
            model_id = str(model_entry.get('lm_studio_model_id', ''))
            self.lm_status_label.setText(f'Connected to LM Studio. Active model: {model_id}. Timeout: {int(client.timeout_seconds)}s')
            if show_popup:
                QMessageBox.information(self, 'LM Studio connected', f'Connected successfully.\n\nModel: {model_id}\nTimeout: {int(client.timeout_seconds)}s')
        except LMStudioError as exc:
            self.lm_status_label.setText(str(exc))
            if show_popup:
                QMessageBox.warning(self, 'LM Studio connection failed', str(exc))

    def connect_signals(self) -> None:
        if self.user_name_edit is not None:
            self.user_name_edit.editingFinished.connect(lambda: self.save_ui_to_settings(show_popup=False))
        if self.user_sex_combo is not None:
            self.user_sex_combo.currentIndexChanged.connect(lambda _index: self.save_ui_to_settings(show_popup=False))
        if self.story_city_edit is not None:
            self.story_city_edit.editingFinished.connect(lambda: self.save_ui_to_settings(show_popup=False))
        if self.story_country_edit is not None:
            self.story_country_edit.editingFinished.connect(lambda: self.save_ui_to_settings(show_popup=False))
        if self.offline_checkbox is not None:
            self.offline_checkbox.toggled.connect(lambda _checked: self.save_ui_to_settings(show_popup=False))
        if self.local_model_checkbox is not None:
            self.local_model_checkbox.toggled.connect(self.on_local_model_toggled)

        if self.lm_studio_checkbox is not None:
            self.lm_studio_checkbox.toggled.connect(self.on_lm_studio_toggled)
        if self.lm_studio_base_url_edit is not None:
            self.lm_studio_base_url_edit.editingFinished.connect(lambda: self.save_ui_to_settings(show_popup=False))
        if self.lm_studio_api_key_edit is not None:
            self.lm_studio_api_key_edit.editingFinished.connect(lambda: self.save_ui_to_settings(show_popup=False))
        if self.lm_studio_model_id_edit is not None:
            self.lm_studio_model_id_edit.editingFinished.connect(lambda: self.save_ui_to_settings(show_popup=False))
        if self.lm_studio_timeout_spin is not None:
            self.lm_studio_timeout_spin.editingFinished.connect(lambda: self.save_ui_to_settings(show_popup=False))

    def _current_backend_preference(self) -> str:
        getter = getattr(self.settings_manager, 'get_chat_backend_preference', None)
        if callable(getter):
            return str(getter() or 'local')
        raw = self.settings_manager.get('chat_backend_preference', None)
        if raw is None:
            return 'lm_studio' if bool(self.settings_manager.get('lm_studio_enabled', False)) else 'local'
        return str(raw or 'local')

    def selected_local_model_id(self) -> str | None:
        if self.model_manager_widget is None:
            return None
        selected_id = self.model_manager_widget.selected_model_id()
        if selected_id:
            return selected_id
        default_model_id = self.settings_manager.get('default_model_id')
        if default_model_id:
            return str(default_model_id)
        available_models = [model for model in self.model_manager.list_models() if model.get('status') == 'available']
        if available_models:
            return str(available_models[0].get('id'))
        return None

    def refresh_backend_selection_summary(self) -> None:
        if self.active_local_model_label is None:
            return
        model_id = self.selected_local_model_id()
        model = self.model_manager.get_model(model_id) if model_id else None
        if model is None:
            self.active_local_model_label.setText('Local model: no available GGUF model is currently selected.')
            return
        status = str(model.get('status', 'unknown')).strip()
        name = str(model.get('name', 'Unnamed model'))
        if status == 'available':
            self.active_local_model_label.setText(f'Local model selected for chats: {name}')
        else:
            self.active_local_model_label.setText(f'Local model selected for chats: {name} (currently {status})')

    def _set_backend_checkbox_state(self, preference: str) -> None:
        if preference not in {'local', 'lm_studio'}:
            preference = 'local'
        if self.local_model_checkbox is not None:
            self.local_model_checkbox.blockSignals(True)
            self.local_model_checkbox.setChecked(preference == 'local')
            self.local_model_checkbox.blockSignals(False)
        if self.lm_studio_checkbox is not None:
            self.lm_studio_checkbox.blockSignals(True)
            self.lm_studio_checkbox.setChecked(preference == 'lm_studio')
            self.lm_studio_checkbox.blockSignals(False)

    def on_local_model_toggled(self, checked: bool) -> None:
        if checked:
            self._set_backend_checkbox_state('local')
        else:
            lm_checked = self.lm_studio_checkbox.isChecked() if self.lm_studio_checkbox is not None else False
            if not lm_checked:
                self._set_backend_checkbox_state('local')
                return
        self.save_ui_to_settings(show_popup=False)

    def on_lm_studio_toggled(self, checked: bool) -> None:
        if checked:
            self._set_backend_checkbox_state('lm_studio')
        else:
            local_checked = self.local_model_checkbox.isChecked() if self.local_model_checkbox is not None else False
            if not local_checked:
                self._set_backend_checkbox_state('local')
                return
        self.save_ui_to_settings(show_popup=False)

    def _on_local_model_selection_changed(self) -> None:
        self.refresh_backend_selection_summary()
        if self.local_model_checkbox is not None and self.local_model_checkbox.isChecked():
            self.save_ui_to_settings(show_popup=False)

    def _refresh_system_advisor(self) -> None:
        """Push the currently selected model id into the system info widget."""
        if self.system_info_widget is None or self.model_manager_widget is None:
            return
        model_id = self.model_manager_widget.selected_model_id()
        self.system_info_widget.update_for_model(model_id)

