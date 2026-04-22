from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from core.paths import get_settings_file


DEFAULT_SETTINGS: dict[str, Any] = {
    'offline_mode': False,
    'default_model_id': None,
    'chat_backend_preference': 'local',
    'startup_page': 'discover',
    'default_context_size': 4096,
    'default_threads': 4,
    'default_max_tokens': 384,
    'last_model_id': None,
    'last_character_id': None,
    'last_temperature': 0.8,
    'last_context_size': 4096,
    'last_threads': 4,
    'last_max_tokens': 384,
    'user_name': '',
    'user_sex': '',
    'initial_setup_complete': False,
    'lm_studio_enabled': False,
    'lm_studio_base_url': 'http://127.0.0.1:1234/v1',
    'lm_studio_api_key': '',
    'lm_studio_model_id': '',
    'lm_studio_timeout_seconds': 300,
    'ollama_enabled': False,
    'ollama_base_url': 'http://127.0.0.1:11434/v1',
    'ollama_api_key': '',
    'ollama_model_id': '',
    'ollama_timeout_seconds': 300,
    'story_location_city': '',
    'story_location_country': '',
    'ui_font_size': 13,
    'developer_mode': False,
}


class SettingsManager:
    def __init__(self) -> None:
        self.settings_file = get_settings_file()
        self._settings: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.settings_file.exists():
            self._settings = deepcopy(DEFAULT_SETTINGS)
            self.save()
            return self._settings
        try:
            data = json.loads(self.settings_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if 'chat_backend_preference' not in data:
            if bool(data.get('ollama_enabled', False)):
                data['chat_backend_preference'] = 'ollama'
            else:
                data['chat_backend_preference'] = 'lm_studio' if bool(data.get('lm_studio_enabled', False)) else 'local'
        merged = deepcopy(DEFAULT_SETTINGS)
        merged.update(data)
        self._settings = merged
        return self._settings

    def save(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(json.dumps(self._settings, indent=2), encoding='utf-8')

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._settings:
            return self._settings[key]
        return deepcopy(DEFAULT_SETTINGS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value
        self.save()

    def update(self, values: dict[str, Any]) -> None:
        self._settings.update(values)
        self.save()

    def is_offline_mode(self) -> bool:
        return bool(self.get('offline_mode', False))

    def set_offline_mode(self, value: bool) -> None:
        self.set('offline_mode', bool(value))

    def get_user_name(self) -> str:
        return str(self.get('user_name', '') or '').strip()

    def get_user_sex(self) -> str:
        return str(self.get('user_sex', '') or '').strip()

    def needs_initial_setup(self) -> bool:
        alias = self.get_user_name()
        sex = self.get_user_sex()
        if not bool(self.get('initial_setup_complete', False)):
            return not alias or not sex
        return not alias or not sex

    def get_chat_backend_preference(self) -> str:
        preference = str(self.get('chat_backend_preference', 'local') or 'local').strip().lower()
        if preference not in {'local', 'lm_studio', 'ollama'}:
            return 'local'
        return preference

    def is_lm_studio_enabled(self) -> bool:
        return self.get_chat_backend_preference() == 'lm_studio'

    def is_ollama_enabled(self) -> bool:
        return self.get_chat_backend_preference() == 'ollama'

    def is_developer_mode(self) -> bool:
        return bool(self.get('developer_mode', False))

    def set_developer_mode(self, value: bool) -> None:
        self.set('developer_mode', bool(value))
