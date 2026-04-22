from __future__ import annotations

import ast
import json
import logging
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from core.character_state import default_memory_payload_for_character, merge_character_static_and_memory
from core.paths import (
    get_characters_dir,
    get_discover_characters_dir,
)

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
PYTHON_CHARACTER_KEYS = ('CHARACTER', 'CARD', 'CHARACTER_CARD', 'PROFILE')
DISCOVER_CARD_FILENAMES = ('character_static.json', 'character_static.py', 'character.py', 'character.json')
DISCOVER_MEMORY_FILENAMES = ('memory.json', 'memory.py')
LEGACY_DISCOVER_CARD_PATTERNS = ('{slug}.py', '{slug}.json')
DEFAULT_AVATAR_FILENAMES = tuple(f'avatar{ext}' for ext in IMAGE_EXTENSIONS)
IGNORED_DISCOVER_DIR_NAMES = {'__pycache__'}

logger = logging.getLogger(__name__)


class CharacterManager:
    """
    Manages both discover (built-in) and user-created characters.

    User characters are stored in the subdirectory format:
        data/characters/<slug>/
            character_static.json   – full character data
            memory.json             – blank memory store (created on first save)
            <slug>.<ext>            – avatar image (optional)

    This matches the format used by LocalCharacterFileStore in
    my_character_library_page.py, keeping the two systems fully compatible.

    NOTE: The legacy flat-file format (data/characters/<id>.json) is also
    scanned for backward compatibility but new saves always use the
    subdirectory format.
    """

    _STATIC_FILENAME = 'character_static.json'
    _MEMORY_FILENAME = 'memory.json'
    # _DEFAULT_MEMORY removed — blank memory is now generated via
    # default_memory_payload_for_character() so it always matches the
    # current schema (including relationships_with_characters).

    # Folder names inside data/characters/ that are NOT character slugs
    _RESERVED_DIR_NAMES: frozenset[str] = frozenset(
        {'avatars', 'cache', 'tmp', 'temp', '__pycache__'}
    )

    def __init__(self) -> None:
        self.characters_dir = get_characters_dir()
        self.discover_dir = get_discover_characters_dir()
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.discover_dir.mkdir(parents=True, exist_ok=True)
        # Note: the old data/characters/avatars/ directory is no longer
        # created here. Avatars are now stored inside each character's own
        # subfolder (data/characters/<slug>/<slug>.<ext>).

    # ── Directory / file helpers ──────────────────────────────────────────

    def _character_dir(self, slug: str) -> Path:
        return self.characters_dir / slug

    def _character_static_file(self, slug: str) -> Path:
        return self._character_dir(slug) / self._STATIC_FILENAME

    def _character_memory_file(self, slug: str) -> Path:
        return self._character_dir(slug) / self._MEMORY_FILENAME

    def _ensure_memory(self, slug: str) -> None:
        """Create a blank memory.json inside the character folder if absent.

        The payload is generated from default_memory_payload_for_character so
        it always reflects the current schema, including relationships_with_characters.
        If the character_static.json already exists, its id/slug/name are used
        to populate character_ref; otherwise only the slug is seeded.
        """
        memory_path = self._character_memory_file(slug)
        if not memory_path.is_file():
            static_path = self._character_static_file(slug)
            seed: dict[str, Any] = {'slug': slug}
            if static_path.is_file():
                try:
                    with static_path.open(encoding='utf-8') as fh:
                        raw = json.load(fh)
                    seed = {
                        'id': str(raw.get('id', slug)).strip(),
                        'slug': slug,
                        'name': str(raw.get('name', slug)).strip(),
                    }
                except Exception:
                    pass
            blank = default_memory_payload_for_character(seed)
            with memory_path.open('w', encoding='utf-8') as fh:
                json.dump(blank, fh, indent=2, ensure_ascii=False)

    # ── Public character listing ──────────────────────────────────────────

    def list_builtin_characters(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for pack_dir in sorted(self.discover_dir.iterdir(), key=lambda item: item.name.lower()):
            if not self._is_discover_pack_dir(pack_dir):
                continue
            card_file = self._discover_card_file(pack_dir)
            if card_file is None:
                continue
            try:
                raw = self._load_discover_payload(card_file)
                normalized = self._normalize_discover_character(raw, card_file, pack_dir)
                results.append(normalized)
            except Exception as exc:
                logger.warning('Failed to load discover character pack from %s: %s', card_file, exc)
                continue
        results.sort(key=lambda item: (str(item.get('name', '')).lower(), str(item.get('title', '')).lower()))
        return results

    def list_user_characters(self) -> list[dict[str, Any]]:
        """
        Return all user-created characters.

        Scans in two passes so that both storage formats are supported:

        Pass 1 - Subdirectory format (current / canonical):
            data/characters/<slug>/character_static.json

        Pass 2 - Legacy flat-file format (backward compat):
            data/characters/<id>.json
            (skipped if the same id was already found in pass 1)

        In both cases, the character id and slug are normalised to match the
        containing folder/file stem so that get_character() always resolves.
        """
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # ── Pass 1: subdirectory format ──────────────────────────────
        for subdir in sorted(self.characters_dir.iterdir(), key=lambda p: p.name.lower()):
            if not subdir.is_dir():
                continue
            if subdir.name in self._RESERVED_DIR_NAMES:
                continue

            # Accept canonical filename; fall back to legacy <slug>.json inside folder
            static_file = subdir / self._STATIC_FILENAME
            if not static_file.is_file():
                legacy = subdir / f'{subdir.name}.json'
                if legacy.is_file():
                    static_file = legacy
                else:
                    continue

            try:
                data = json.loads(static_file.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict):
                continue

            # Normalise: id and slug must equal the folder name so that
            # get_character() can look up the folder from the stored id.
            if str(data.get('id', '')) != subdir.name:
                data['id'] = subdir.name
            if str(data.get('slug', '')) != subdir.name:
                data['slug'] = subdir.name

            data.setdefault('source', 'user')
            record = self._normalize_character_record(data)
            if record['id'] and record['id'] not in seen_ids:
                seen_ids.add(record['id'])
                results.append(record)

        # ── Pass 2: legacy flat JSON files ───────────────────────────
        for file_path in sorted(
            self.characters_dir.glob('*.json'), key=lambda p: p.name.lower()
        ):
            try:
                data = json.loads(file_path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict):
                data.setdefault('source', 'user')
                record = self._normalize_character_record(data)
                char_id = record.get('id', '')
                if char_id and char_id not in seen_ids:
                    seen_ids.add(char_id)
                    results.append(record)

        results.sort(key=lambda item: (str(item.get('name', '')).lower(), str(item.get('title', '')).lower()))
        return results

    def list_all_characters(self) -> list[dict[str, Any]]:
        return self.list_builtin_characters() + self.list_user_characters()

    def list_folders(self, include_builtin: bool = True) -> list[str]:
        characters = self.list_all_characters() if include_builtin else self.list_user_characters()
        folders = {
            str(character.get('folder', 'General')).strip() or 'General'
            for character in characters
        }
        return sorted(folders, key=str.lower)

    def list_tags(self, include_builtin: bool = True) -> list[str]:
        characters = self.list_all_characters() if include_builtin else self.list_user_characters()
        tags: set[str] = set()
        for character in characters:
            for tag in character.get('tags', []):
                cleaned = str(tag).strip()
                if cleaned:
                    tags.add(cleaned)
        return sorted(tags, key=str.lower)

    def get_character(self, character_id: str) -> dict[str, Any] | None:
        for character in self.list_all_characters():
            if str(character.get('id')) == character_id:
                return character
        return None

    # ── Save / Delete / Duplicate / Export / Import ───────────────────────

    def save_character(
        self,
        character_data: dict[str, Any],
        copy_avatar_to_managed_storage: bool = False,
    ) -> dict[str, Any]:
        """
        Persist a user character to disk in subdirectory format:
            data/characters/<slug>/character_static.json
            data/characters/<slug>/memory.json   (created blank if absent)
            data/characters/<slug>/<slug>.<ext>  (avatar copy, if requested)

        All fields supplied in character_data are preserved verbatim so that
        nested structures such as identity, voice, and knowledge are never
        silently dropped.
        """
        name = str(character_data.get('name', '')).strip()
        if not name:
            raise ValueError('Character name is required.')

        # Resolve slug from explicit field or generate from name
        slug = str(
            character_data.get('slug', '') or character_data.get('id', '')
        ).strip()
        if not slug or slug.startswith('discover_'):
            slug = self.generate_character_id(name)

        # Handle rename: if the old id differs from slug and old dir exists
        old_id = str(character_data.get('id', '')).strip()
        if old_id and old_id != slug and self._character_dir(old_id).is_dir():
            new_dir = self._character_dir(slug)
            if not new_dir.exists():
                self._character_dir(old_id).rename(new_dir)

        # Ensure the character folder exists
        char_dir = self._character_dir(slug)
        char_dir.mkdir(parents=True, exist_ok=True)

        # Avatar copy into the character's own folder
        avatar_path = str(character_data.get('avatar_path', '')).strip()
        if copy_avatar_to_managed_storage and avatar_path:
            avatar_path = self._copy_avatar_to_character_dir(slug, avatar_path)

        now = datetime.now().replace(microsecond=0).isoformat()

        # Build payload: start with all supplied fields so nested structures
        # (identity, voice, knowledge, etc.) are never lost, then enforce
        # canonical top-level fields.
        payload: dict[str, Any] = dict(character_data)
        payload.update({
            'id':                slug,
            'slug':              slug,
            'name':              name,
            'title':             str(character_data.get('title', '')).strip(),
            'role':              str(character_data.get('role', '')).strip(),
            'description':       str(character_data.get('description', '')).strip(),
            'system_prompt':     str(character_data.get('system_prompt', '')).strip(),
            'avatar_path':       avatar_path,
            'greeting':          str(character_data.get('greeting', '')).strip(),
            'example_dialogue':  str(character_data.get('example_dialogue', '')).strip(),
            'starting_scenario': str(character_data.get('starting_scenario', '')).strip(),
            'world_lore_notes':  str(
                character_data.get('world_lore_notes', character_data.get('world_lore', ''))
            ).strip(),
            'tags':        self._normalize_tags(character_data.get('tags', [])),
            'folder':      str(character_data.get('folder', 'General')).strip() or 'General',
            'is_favorite': bool(character_data.get('is_favorite', False)),
            'source':      'user',
        })

        # Preserve created_at from disk if this is an update
        existing = self._load_user_character_from_dir(slug)
        if existing:
            payload.setdefault('created_at', existing.get('created_at', now))
        else:
            payload.setdefault('created_at', now)
        payload['updated_at'] = now

        # Write character_static.json
        with self._character_static_file(slug).open('w', encoding='utf-8') as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        # Ensure blank memory file exists
        self._ensure_memory(slug)

        return self._normalize_character_record(payload)

    def delete_character(self, character_id: str) -> None:
        if character_id.startswith('discover_'):
            raise ValueError('Discover characters are read-only and cannot be deleted here.')

        # Subdirectory format (current)
        char_dir = self._character_dir(character_id)
        if char_dir.is_dir():
            shutil.rmtree(char_dir)
            return

        # Legacy flat-file format (backward compat)
        flat_file = self.characters_dir / f'{character_id}.json'
        if flat_file.exists():
            flat_file.unlink()
            return

        raise ValueError(f"Character '{character_id}' not found.")

    def duplicate_character(self, character_id: str) -> dict[str, Any]:
        existing = self.get_character(character_id)
        if existing is None:
            raise ValueError('Character not found.')
        duplicated = dict(existing)
        duplicated.pop('id', None)
        duplicated.pop('slug', None)
        duplicated['name'] = f"{existing.get('name', 'Character')} Copy"
        for key in ('source', 'created_at', 'updated_at', 'pack_dir', 'card_file',
                    'static_file', 'memory_file', 'raw'):
            duplicated.pop(key, None)
        return self.save_character(duplicated)

    def export_character(self, character_id: str, destination_path: str | Path) -> Path:
        character = self.get_character(character_id)
        if character is None:
            raise ValueError('Character not found.')
        destination = Path(destination_path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(character, indent=2), encoding='utf-8')
        return destination

    def import_character(
        self,
        source_path: str | Path,
        copy_avatar_to_managed_storage: bool = False,
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser()
        if not source.exists():
            raise FileNotFoundError('Character import file was not found.')
        try:
            data = json.loads(source.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise ValueError('Character import file is not valid JSON.') from exc
        if not isinstance(data, dict):
            raise ValueError('Character import file must contain a single character object.')

        imported = dict(data)
        imported.pop('source', None)

        # Force a new id so we never silently overwrite an existing character
        imported_id = str(imported.get('id', '')).strip()
        if (
            not imported_id
            or imported_id.startswith('discover_')
            or self._character_dir(imported_id).is_dir()
            or (self.characters_dir / f'{imported_id}.json').exists()
        ):
            imported['id'] = ''
            imported['slug'] = ''

        return self.save_character(
            imported,
            copy_avatar_to_managed_storage=copy_avatar_to_managed_storage,
        )

    def set_builtin_avatar(self, character_id: str, avatar_path: str) -> None:
        raise ValueError('Discover character images are defined by their pack files.')

    def generate_character_id(self, name: str) -> str:
        slug = ''.join(ch.lower() if ch.isalnum() else '_' for ch in name).strip('_')
        slug = '_'.join(part for part in slug.split('_') if part)
        base_slug = slug or 'character'
        candidate = base_slug
        counter = 2
        existing_ids = {str(char.get('id')) for char in self.list_all_characters()}
        while candidate in existing_ids or self._character_dir(candidate).is_dir():
            candidate = f'{base_slug}_{counter}'
            counter += 1
        return candidate

    def discover_character_structure_text(self) -> str:
        return (
            'Create one folder per discover character under data/discover_characters/.\n\n'
            'Recommended structure:\n'
            'data/discover_characters/<character_slug>/character.py\n'
            'data/discover_characters/<character_slug>/avatar.png\n\n'
            'Only subfolders are scanned. Loose files in the root of discover_characters are ignored.\n'
            'Inside character.py, define a CHARACTER dictionary.\n'
            'Set avatar to "avatar.png" or another image file inside the same folder.'
        )

    # ── Avatar helpers ────────────────────────────────────────────────────

    def _copy_avatar_to_character_dir(self, slug: str, avatar_path: str) -> str:
        """
        Copy the avatar image into the character's own subfolder.
        Returns the destination path, or the original if copy fails
        (so a missing avatar never blocks a save).
        """
        source = Path(avatar_path).expanduser().resolve()
        if not source.is_file():
            return avatar_path
        suffix = source.suffix.lower() or '.png'
        dest_dir = self._character_dir(slug)
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / f'{slug}{suffix}'
        # Skip copy if source and target are already the same file
        if target.resolve() == source:
            return str(target)
        try:
            shutil.copy2(source, target)
            return str(target)
        except OSError:
            return avatar_path

    # ── Internal load helpers ─────────────────────────────────────────────

    def _load_user_character_from_dir(self, slug: str) -> dict[str, Any] | None:
        """Read character_static.json from the slug subfolder."""
        static_file = self._character_static_file(slug)
        if not static_file.is_file():
            return None
        try:
            data = json.loads(static_file.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    # ── Discover character helpers (unchanged) ────────────────────────────

    def _is_discover_pack_dir(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        if path.name.startswith('_') or path.name in IGNORED_DISCOVER_DIR_NAMES:
            return False
        return True

    def _discover_card_file(self, pack_dir: Path) -> Path | None:
        for name in DISCOVER_CARD_FILENAMES:
            candidate = pack_dir / name
            if candidate.exists() and candidate.is_file():
                return candidate
        for pattern in LEGACY_DISCOVER_CARD_PATTERNS:
            candidate = pack_dir / pattern.format(slug=pack_dir.name)
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _load_discover_payload(self, card_file: Path) -> dict[str, Any]:
        suffix = card_file.suffix.lower()
        if suffix == '.json':
            data = json.loads(card_file.read_text(encoding='utf-8'))
        elif suffix == '.py':
            data = self._load_python_character_payload(card_file)
        else:
            raise ValueError(f'Unsupported discover character file type: {card_file.suffix}')
        if not isinstance(data, dict):
            raise ValueError('Character file must define a single object.')
        return data

    def _discover_memory_file(self, pack_dir: Path) -> Path | None:
        for name in DISCOVER_MEMORY_FILENAMES:
            candidate = pack_dir / name
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _load_python_character_payload(self, card_file: Path) -> dict[str, Any]:
        source = card_file.read_text(encoding='utf-8')
        if not source.strip():
            raise ValueError('Character file is empty.')

        module = ast.parse(source, filename=str(card_file))

        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in PYTHON_CHARACTER_KEYS:
                        return self._literal_eval_dict(node.value, card_file)

        for node in module.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Dict):
                return self._literal_eval_dict(node.value, card_file)

        for node in module.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                return self._literal_eval_dict(node.value, card_file)

        raise ValueError(
            f'No CHARACTER dictionary was found in {card_file.name}. '
            'Define CHARACTER = {...} in the file.'
        )

    @staticmethod
    def _literal_eval_dict(node: ast.AST, card_file: Path) -> dict[str, Any]:
        try:
            data = ast.literal_eval(node)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f'Character file {card_file.name} contains unsupported Python values.') from exc
        if not isinstance(data, dict):
            raise ValueError(f'Character file {card_file.name} must define a dictionary.')
        return data

    def _normalize_discover_character(self, data: dict[str, Any], card_file: Path, pack_dir: Path) -> dict[str, Any]:
        record = deepcopy(data)
        memory_file = None
        if card_file.name.startswith('character_static.'):
            memory_file = self._discover_memory_file(pack_dir)
            if memory_file is not None:
                try:
                    record = merge_character_static_and_memory(record, self._load_discover_payload(memory_file))
                except Exception as exc:
                    logger.warning('Failed to merge memory file for discover character pack %s: %s', pack_dir, exc)
                    record = merge_character_static_and_memory(record, None)
            else:
                record = merge_character_static_and_memory(record, None)
        slug = str(record.get('slug') or pack_dir.name).strip() or pack_dir.name
        character_id = str(record.get('id') or f'discover_{slug}').strip()
        name = str(record.get('name') or slug.replace('_', ' ').title()).strip()
        title = str(record.get('title') or record.get('role') or record.get('story_role') or '').strip()
        identity = record.get('identity') if isinstance(record.get('identity'), dict) else {}
        description = str(
            record.get('description')
            or identity.get('public_summary')
            or record.get('story_role')
            or ''
        ).strip()
        tags = record.get('tags') or []
        if not tags:
            derived_tags = []
            for value in [record.get('role'), record.get('story_role')]:
                text = str(value or '').strip()
                if text:
                    derived_tags.append(text)
            tags = derived_tags

        avatar_path = str(
            record.get('avatar_path')
            or record.get('avatar')
            or record.get('image')
            or record.get('image_path')
            or ''
        ).strip()
        avatar_resolved = self._resolve_discover_avatar(avatar_path, pack_dir, card_file)

        greeting = str(record.get('greeting') or '').strip()
        example_dialogue = str(record.get('example_dialogue') or '').strip()
        starting_scenario = str(record.get('starting_scenario') or '').strip()
        world_lore_notes = str(record.get('world_lore_notes') or record.get('world_lore') or '').strip()
        system_prompt = str(record.get('system_prompt') or '').strip() or self._build_system_prompt(record)

        normalized = {
            'id': character_id,
            'slug': slug,
            'name': name,
            'name_color': str(record.get('name_color') or record.get('name_colour') or '').strip(),
            'title': title,
            'description': description,
            'system_prompt': system_prompt,
            'avatar_path': avatar_resolved,
            'greeting': greeting,
            'example_dialogue': example_dialogue,
            'starting_scenario': starting_scenario,
            'world_lore_notes': world_lore_notes,
            'tags': self._normalize_tags(tags),
            'folder': str(record.get('folder', 'Discover')).strip() or 'Discover',
            'is_favorite': bool(record.get('is_favorite', False)),
            'source': 'discover',
            'pack_dir': str(pack_dir),
            'card_file': str(card_file),
            'static_file': str(card_file) if card_file.name.startswith('character_static.') else '',
            'memory_file': str(memory_file) if memory_file is not None else '',
            'raw': record,
        }
        for key in ('relationship_with_user', 'emotional_baseline', 'memories', 'open_threads', 'scene_flags', 'knowledge', 'character_ref'):
            if key in record:
                normalized[key] = deepcopy(record[key])
        return self._normalize_character_record(normalized)

    def _resolve_discover_avatar(self, avatar_value: str, pack_dir: Path, card_file: Path) -> str:
        candidates: list[Path] = []
        if avatar_value:
            avatar_path = Path(avatar_value)
            if avatar_path.is_absolute():
                candidates.append(avatar_path)
            else:
                candidates.append(pack_dir / avatar_path)
                candidates.append(card_file.parent / avatar_path)

        for avatar_name in DEFAULT_AVATAR_FILENAMES:
            candidates.append(pack_dir / avatar_name)

        stem = card_file.stem
        for ext in IMAGE_EXTENSIONS:
            candidates.append(pack_dir / f'{stem}{ext}')
            candidates.append(pack_dir / f'{pack_dir.name}{ext}')
            candidates.append(card_file.with_suffix(ext))

        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return ''

    def _build_system_prompt(self, record: dict[str, Any]) -> str:
        name = str(record.get('name') or 'The character').strip()
        role = str(record.get('role') or record.get('title') or '').strip()
        story_role = str(record.get('story_role') or '').strip()
        identity = record.get('identity') if isinstance(record.get('identity'), dict) else {}
        voice = record.get('voice') if isinstance(record.get('voice'), dict) else {}
        summary = str(identity.get('public_summary') or record.get('description') or '').strip()
        core_traits = ', '.join(str(item).strip() for item in identity.get('core_traits', []) if str(item).strip())
        values = ', '.join(str(item).strip() for item in identity.get('values', []) if str(item).strip())
        tone = str(voice.get('tone') or '').strip()
        cadence = str(voice.get('cadence') or '').strip()
        patterns = ', '.join(str(item).strip() for item in voice.get('favored_patterns', []) if str(item).strip())
        avoid_patterns = ', '.join(str(item).strip() for item in voice.get('avoid_patterns', []) if str(item).strip())

        parts = [f'You are {name}.']
        if role:
            parts.append(f'Role: {role}.')
        if story_role:
            parts.append(f'Story role: {story_role}.')
        if summary:
            parts.append(summary)
        if core_traits:
            parts.append(f'Core traits: {core_traits}.')
        if values:
            parts.append(f'Values: {values}.')
        if tone:
            parts.append(f'Voice tone: {tone}.')
        if cadence:
            parts.append(f'Cadence: {cadence}.')
        if patterns:
            parts.append(f'Favored speech patterns: {patterns}.')
        if avoid_patterns:
            parts.append(f'Avoid: {avoid_patterns}.')
        parts.append('Stay fully in character, remain conversational, and keep the roleplay immersive.')
        return ' '.join(parts)

    # ── Normalisation helpers ─────────────────────────────────────────────

    @staticmethod
    def _normalize_tags(tags: Any) -> list[str]:
        if isinstance(tags, str):
            raw = tags.split(',')
        elif isinstance(tags, list):
            raw = tags
        else:
            raw = []
        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in raw:
            text = str(tag).strip()
            folded = text.lower()
            if text and folded not in seen:
                cleaned.append(text)
                seen.add(folded)
        return cleaned

    def _normalize_character_record(self, data: dict[str, Any]) -> dict[str, Any]:
        record = dict(data)
        record.setdefault('id', '')
        record.setdefault('name', '')
        record.setdefault('name_color', str(record.get('name_colour', '')))
        record.setdefault('title', '')
        record.setdefault('description', '')
        # Fall back to identity.public_summary when description is blank,
        # so user characters display the same summary text as discover characters.
        if not record.get('description'):
            identity = record.get('identity') if isinstance(record.get('identity'), dict) else {}
            fallback = str(identity.get('public_summary', '') or '').strip()
            if fallback:
                record['description'] = fallback
        record.setdefault('system_prompt', '')
        record.setdefault('avatar_path', '')
        record.setdefault('greeting', '')
        record.setdefault('example_dialogue', '')
        record.setdefault('starting_scenario', '')
        if 'world_lore_notes' not in record:
            record['world_lore_notes'] = str(record.get('world_lore', ''))
        record['tags'] = self._normalize_tags(record.get('tags', []))
        record['folder'] = str(record.get('folder', 'General')).strip() or 'General'
        record['is_favorite'] = bool(record.get('is_favorite', False))
        record.setdefault('source', 'user')
        return record
