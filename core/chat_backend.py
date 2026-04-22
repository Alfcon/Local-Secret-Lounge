from __future__ import annotations

from typing import Any

from core.lm_studio_client import LMStudioClient, LMStudioError


REMOTE_SOURCE = 'lm_studio_server'


def get_chat_backend_preference(settings_manager) -> str:
    getter = getattr(settings_manager, 'get_chat_backend_preference', None)
    if callable(getter):
        preference = str(getter() or 'local').strip().lower()
    else:
        raw = settings_manager.get('chat_backend_preference', None)
        if raw is None:
            raw = 'lm_studio' if bool(settings_manager.get('lm_studio_enabled', False)) else 'local'
        preference = str(raw or 'local').strip().lower()
    if preference not in {'local', 'lm_studio'}:
        return 'local'
    return preference


def is_lm_studio_enabled(settings_manager) -> bool:
    return get_chat_backend_preference(settings_manager) == 'lm_studio'


def is_lm_studio_model(model_entry: dict[str, Any] | None) -> bool:
    if not model_entry:
        return False
    return str(model_entry.get('source', '')).strip() == REMOTE_SOURCE


def resolve_lm_studio_model(settings_manager) -> dict[str, Any]:
    client = LMStudioClient.from_settings(settings_manager)
    preferred_model_id = str(settings_manager.get('lm_studio_model_id', '') or '').strip()
    return client.resolve_model(preferred_model_id or None)


def get_preferred_chat_model(settings_manager, model_manager) -> tuple[dict[str, Any] | None, str | None]:
    backend_preference = get_chat_backend_preference(settings_manager)

    if backend_preference == 'lm_studio':
        try:
            model = resolve_lm_studio_model(settings_manager)
            return model, None
        except LMStudioError as exc:
            return None, str(exc)

    available_models = [model for model in model_manager.list_models() if model.get('status') == 'available']
    preferred_id = settings_manager.get('last_model_id') or settings_manager.get('default_model_id')
    if preferred_id:
        preferred = next((model for model in available_models if model.get('id') == preferred_id), None)
        if preferred is not None:
            return preferred, None

    if available_models:
        default_model = next((model for model in available_models if model.get('is_default')), None)
        return default_model or available_models[0], None

    return None, 'No available local GGUF model is selected for chats yet. Highlight one in Settings and tick the local model option, or switch the chat backend to LM Studio.'


def describe_active_backend(settings_manager, model_manager) -> tuple[str, bool]:
    backend_preference = get_chat_backend_preference(settings_manager)
    model_entry, error_text = get_preferred_chat_model(settings_manager, model_manager)

    if model_entry is not None and is_lm_studio_model(model_entry):
        model_id = str(model_entry.get('lm_studio_model_id', 'model'))
        base_url = str(model_entry.get('lm_studio_base_url', ''))
        return f'LM Studio Local Server is selected and ready for chats.\n\nModel: {model_id}\nURL: {base_url}', True

    if model_entry is not None:
        return (
            f"The selected local GGUF model will be used for chats.\n\nModel: {model_entry.get('name', 'Installed model')}",
            True,
        )
    if backend_preference == 'lm_studio':
        return error_text or 'LM Studio is selected, but it is not ready yet.', False
    return error_text or 'A local GGUF model is selected, but it is not ready yet.', False
