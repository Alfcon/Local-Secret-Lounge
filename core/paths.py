from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / 'data'
MODELS_DIR = DATA_DIR / 'models'
CHATS_DIR = DATA_DIR / 'chats'
CHARACTERS_DIR = DATA_DIR / 'characters'
CHARACTER_AVATARS_DIR = CHARACTERS_DIR / 'avatars'
DISCOVER_CHARACTERS_DIR = DATA_DIR / 'discover_characters'
CACHE_DIR = DATA_DIR / 'cache'
SETTINGS_FILE = DATA_DIR / 'settings.json'
MODELS_REGISTRY_FILE = MODELS_DIR / 'models.json'


def get_app_root() -> Path:
    return APP_ROOT


def get_data_dir() -> Path:
    return DATA_DIR


def get_models_dir() -> Path:
    return MODELS_DIR


def get_chats_dir() -> Path:
    return CHATS_DIR


def get_characters_dir() -> Path:
    return CHARACTERS_DIR


def get_character_avatars_dir() -> Path:
    return CHARACTER_AVATARS_DIR


def get_discover_characters_dir() -> Path:
    return DISCOVER_CHARACTERS_DIR


def get_cache_dir() -> Path:
    return CACHE_DIR


def get_settings_file() -> Path:
    return SETTINGS_FILE


def get_models_registry_file() -> Path:
    return MODELS_REGISTRY_FILE


def ensure_app_directories() -> None:
    # Note: CHARACTER_AVATARS_DIR (data/characters/avatars/) is intentionally
    # excluded here. Avatars are now stored inside each character own
    # subfolder (data/characters/<slug>/<slug>.<ext>) and the central avatars
    # directory is no longer needed or created on startup.
    for folder in (
        DATA_DIR,
        MODELS_DIR,
        CHATS_DIR,
        CHARACTERS_DIR,
        DISCOVER_CHARACTERS_DIR,
        CACHE_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text('{}', encoding='utf-8')
    if not MODELS_REGISTRY_FILE.exists():
        MODELS_REGISTRY_FILE.write_text('[]', encoding='utf-8')
