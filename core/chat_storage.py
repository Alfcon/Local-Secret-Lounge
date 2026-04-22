from __future__ import annotations

import json
import logging
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from core.character_state import (
    extract_character_memory,
    extract_character_static,
    merge_character_static_and_memory,
)
from core.paths import get_app_root, get_chats_dir

logger = logging.getLogger(__name__)


class ChatStorage:
    def __init__(self) -> None:
        self.chats_dir = get_chats_dir()
        self.chats_dir.mkdir(parents=True, exist_ok=True)

        legacy_dir = get_app_root() / 'data' / 'chats'
        self.legacy_chat_dirs: list[Path] = []
        try:
            if legacy_dir.resolve() != self.chats_dir.resolve():
                self.legacy_chat_dirs.append(legacy_dir)
        except FileNotFoundError:
            self.legacy_chat_dirs.append(legacy_dir)

    def create_chat_session(
        self,
        *,
        character: dict[str, Any],
        model_entry: dict[str, Any],
        generation_settings: dict[str, Any],
        user_name: str = '',
    ) -> dict[str, Any]:
        now = datetime.now().replace(microsecond=0).isoformat()
        chat_id = self._generate_chat_id(character.get('name', 'chat'))
        title = f"Chat with {character.get('name', 'Character')}"
        session = {
            'id': chat_id,
            'title': title,
            'character': deepcopy(character),
            'participants': [deepcopy(character)],
            'pending_participants': [],
            'model': deepcopy(model_entry),
            'generation_settings': deepcopy(generation_settings),
            'user_name': str(user_name or '').strip(),
            'messages': [],
            'message_count': 0,
            'preview': '',
            'rolling_summary': '',
            'rolling_summary_message_count': 0,
            'scene_state': {},
            'created_at': now,
            'updated_at': now,
        }
        return self.save_chat(session)

    def list_chats(self, search_query: str | None = None) -> list[dict[str, Any]]:
        chats: list[dict[str, Any]] = []
        query = (search_query or '').strip().lower()
        seen_ids: set[str] = set()
        for file_path in self._iter_chat_metadata_files():
            try:
                data = json.loads(file_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            chat_id = str(data.get('id', '')).strip()
            if not chat_id or chat_id in seen_ids:
                continue
            seen_ids.add(chat_id)
            summary = self._summarize_chat(data)
            if query and not self._chat_matches(summary, query):
                continue
            chats.append(summary)
        chats.sort(key=lambda item: str(item.get('updated_at', '')), reverse=True)
        return chats

    def load_chat(self, chat_id: str) -> dict[str, Any]:
        file_path = self._existing_chat_file(chat_id)
        if file_path is None:
            raise FileNotFoundError(f'Chat not found: {chat_id}')
        data = json.loads(file_path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Invalid chat file format.')
        data.setdefault('chat_dir', str(file_path.parent if file_path.name == 'chat.json' else file_path.parent))
        data.setdefault('chat_file', str(file_path))
        return self._hydrate_chat_characters_from_snapshots(data)

    def save_chat(self, chat_data: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(chat_data)
        chat_id = str(payload.get('id', '')).strip()
        if not chat_id:
            seed = payload.get('character', {}).get('name', 'chat') if isinstance(payload.get('character'), dict) else 'chat'
            chat_id = self._generate_chat_id(str(seed))
            payload['id'] = chat_id

        payload.setdefault('messages', [])
        payload.setdefault('title', f"Chat with {payload.get('character', {}).get('name', 'Character')}")
        payload.setdefault('user_name', '')
        payload.setdefault('participants', [deepcopy(payload.get('character', {}))] if isinstance(payload.get('character'), dict) else [])
        payload.setdefault('pending_participants', [])

        payload = self._snapshot_chat_assets(payload)

        payload['message_count'] = len([msg for msg in payload['messages'] if msg.get('role') != 'system'])
        payload['preview'] = self._build_preview(payload['messages'])
        payload['updated_at'] = datetime.now().replace(microsecond=0).isoformat()

        chat_dir = self._chat_dir(chat_id)
        chat_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = self._chat_file(chat_id)
        payload['chat_dir'] = str(chat_dir)
        payload['chat_file'] = str(metadata_path)

        metadata_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

        legacy_file = None
        for legacy_dir in self.legacy_chat_dirs:
            candidate = legacy_dir / f'{chat_id}.json'
            if candidate.exists():
                legacy_file = candidate
                break
        if legacy_file is not None:
            try:
                legacy_file.unlink()
            except Exception as exc:
                logger.warning('Failed to remove legacy chat file %s: %s', legacy_file, exc)

        return payload

    def rename_chat(self, chat_id: str, new_title: str) -> dict[str, Any]:
        title = new_title.strip()
        if not title:
            raise ValueError('Chat title cannot be empty.')
        chat = self.load_chat(chat_id)
        chat['title'] = title
        return self.save_chat(chat)

    def append_message(self, chat_id: str, role: str, content: str) -> dict[str, Any]:
        chat = self.load_chat(chat_id)
        chat.setdefault('messages', []).append(
            {
                'role': role,
                'content': content,
                'timestamp': datetime.now().replace(microsecond=0).isoformat(),
            }
        )
        return self.save_chat(chat)

    def export_chat(self, chat_id: str, export_path: str | Path) -> Path:
        chat = self.load_chat(chat_id)
        target = Path(export_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(chat, indent=2), encoding='utf-8')
        return target

    def export_transcript(self, chat_id: str, export_path: str | Path, *, format: str = 'txt') -> Path:
        chat = self.load_chat(chat_id)
        fmt = format.lower().strip()
        if fmt not in {'txt', 'md'}:
            raise ValueError('Transcript format must be txt or md.')
        target = Path(export_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        title = str(chat.get('title', 'Chat')).strip() or 'Chat'
        character_name = str(chat.get('character', {}).get('name', 'Character'))
        user_name = str(chat.get('user_name', '') or '').strip() or 'You'
        if fmt == 'md':
            lines.append(f'# {title}')
            lines.append('')
            lines.append(f'- Character: {character_name}')
            lines.append(f'- User: {user_name}')
            lines.append(f"- Model: {chat.get('model', {}).get('name', '-')}")
            lines.append('')
        else:
            lines.append(title)
            lines.append('=' * len(title))
            lines.append(f'Character: {character_name}')
            lines.append(f'User: {user_name}')
            lines.append(f"Model: {chat.get('model', {}).get('name', '-')}")
            lines.append('')

        for message in chat.get('messages', []):
            role = str(message.get('role', 'user'))
            if role == 'system':
                continue
            speaker = str(message.get('speaker', '')).strip()
            if not speaker:
                speaker = user_name if role == 'user' else character_name
            content = str(message.get('content', '')).rstrip()
            if fmt == 'md':
                lines.append(f'## {speaker}')
                lines.append('')
                lines.append(content)
                lines.append('')
            else:
                lines.append(f'{speaker}:')
                lines.append(content)
                lines.append('')
        target.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
        return target

    def import_chat(self, file_path: str | Path) -> dict[str, Any]:
        source = Path(file_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f'Chat file not found: {source}')
        try:
            data = json.loads(source.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise ValueError(f'Invalid chat JSON file: {source.name}') from exc
        if not isinstance(data, dict):
            raise ValueError('Imported chat file must contain a JSON object.')
        if 'messages' not in data or not isinstance(data.get('messages'), list):
            raise ValueError('Imported chat file must include a messages list.')

        imported = deepcopy(data)
        imported.pop('chat_dir', None)
        imported.pop('chat_file', None)
        imported_id = str(imported.get('id', '')).strip() or self._generate_chat_id(
            imported.get('character', {}).get('name', 'chat')
        )
        if self._chat_exists(imported_id):
            imported_id = self._generate_chat_id(imported.get('character', {}).get('name', 'chat'))
        imported['id'] = imported_id
        imported.setdefault('created_at', datetime.now().replace(microsecond=0).isoformat())
        imported.setdefault('user_name', '')
        imported['updated_at'] = datetime.now().replace(microsecond=0).isoformat()
        return self.save_chat(imported)

    def delete_chat(self, chat_id: str) -> None:
        file_path = self._existing_chat_file(chat_id)
        if file_path is None:
            return
        if file_path.name == 'chat.json':
            shutil.rmtree(file_path.parent, ignore_errors=True)
        else:
            try:
                file_path.unlink()
            except FileNotFoundError:
                pass

    def _summarize_chat(self, chat: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': chat.get('id'),
            'title': chat.get('title') or f"Chat with {chat.get('character', {}).get('name', 'Character')}",
            'character_name': chat.get('character', {}).get('name', '-'),
            'model_name': chat.get('model', {}).get('name', '-'),
            'message_count': chat.get('message_count', 0),
            'preview': chat.get('preview', ''),
            'updated_at': chat.get('updated_at', chat.get('created_at', '')),
            'created_at': chat.get('created_at', ''),
        }

    @staticmethod
    def _chat_matches(summary: dict[str, Any], query: str) -> bool:
        haystack = ' '.join(
            [
                str(summary.get('title', '')),
                str(summary.get('character_name', '')),
                str(summary.get('model_name', '')),
                str(summary.get('preview', '')),
            ]
        ).lower()
        return query in haystack

    @staticmethod
    def _build_preview(messages: list[dict[str, Any]]) -> str:
        # Return the last visible message snippet as a plain string for the list widget
        for message in reversed(messages):
            if message.get('role') in {'assistant', 'user'}:
                content = str(message.get('content', '')).strip().replace('\n', ' ')
                return content[:140]
        return ''

    def _chat_dir(self, chat_id: str) -> Path:
        return self.chats_dir / chat_id

    def _chat_file(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / 'chat.json'

    def _existing_chat_file(self, chat_id: str) -> Path | None:
        primary = self._chat_file(chat_id)
        if primary.exists():
            return primary
        primary_flat = self.chats_dir / f'{chat_id}.json'
        if primary_flat.exists():
            return primary_flat
        for legacy_dir in self.legacy_chat_dirs:
            legacy_dir_chat = legacy_dir / chat_id / 'chat.json'
            if legacy_dir_chat.exists():
                return legacy_dir_chat
            legacy_flat = legacy_dir / f'{chat_id}.json'
            if legacy_flat.exists():
                return legacy_flat
        return None

    def _iter_chat_metadata_files(self) -> list[Path]:
        results: list[Path] = []
        for base_dir in [self.chats_dir, *self.legacy_chat_dirs]:
            if not base_dir.exists():
                continue
            for child in sorted(base_dir.iterdir(), key=lambda item: item.name.lower()):
                if child.is_dir():
                    metadata = child / 'chat.json'
                    if metadata.exists():
                        results.append(metadata)
                elif child.is_file() and child.suffix.lower() == '.json':
                    results.append(child)
        return results

    def _hydrate_character_from_snapshot(self, character: Any) -> dict[str, Any]:
        if not isinstance(character, dict):
            return {}
        hydrated = deepcopy(character)
        asset_dir_value = str(hydrated.get('chat_asset_dir', '') or hydrated.get('pack_dir', '')).strip()
        if not asset_dir_value:
            return hydrated
        asset_dir = Path(asset_dir_value).expanduser()
        static_file = asset_dir / 'character_static.json'
        memory_file = asset_dir / 'memory.json'
        if static_file.exists() and static_file.is_file():
            try:
                static_data = json.loads(static_file.read_text(encoding='utf-8'))
                if isinstance(static_data, dict):
                    merged = merge_character_static_and_memory(static_data, hydrated)
                    if memory_file.exists() and memory_file.is_file():
                        memory_data = json.loads(memory_file.read_text(encoding='utf-8'))
                        if isinstance(memory_data, dict):
                            merged = merge_character_static_and_memory(static_data, memory_data)
                    for key, value in hydrated.items():
                        merged.setdefault(key, deepcopy(value))
                    merged['pack_dir'] = str(asset_dir)
                    merged['chat_asset_dir'] = str(asset_dir)
                    merged['static_file'] = str(static_file)
                    merged['memory_file'] = str(memory_file) if memory_file.exists() else ''
                    merged['card_file'] = str(asset_dir / 'character.json')
                    return merged
            except Exception as exc:
                logger.warning('Failed to hydrate chat character snapshot from %s: %s', asset_dir, exc)
                return hydrated
        return hydrated

    def _hydrate_chat_characters_from_snapshots(self, chat: dict[str, Any]) -> dict[str, Any]:
        hydrated = deepcopy(chat)
        participants = hydrated.get('participants', [])
        if isinstance(participants, list):
            hydrated['participants'] = [self._hydrate_character_from_snapshot(item) for item in participants if isinstance(item, dict)]
        if isinstance(hydrated.get('character'), dict):
            primary = self._hydrate_character_from_snapshot(hydrated['character'])
            hydrated['character'] = primary
            primary_key = self._character_identity_key(primary)
            updated_participants = hydrated.get('participants', []) if isinstance(hydrated.get('participants'), list) else []
            if updated_participants:
                match = next((item for item in updated_participants if self._character_identity_key(item) == primary_key), None)
                if match is not None:
                    hydrated['character'] = deepcopy(match)
        return hydrated

    def _chat_exists(self, chat_id: str) -> bool:
        return self._existing_chat_file(chat_id) is not None

    def _snapshot_chat_assets(self, payload: dict[str, Any]) -> dict[str, Any]:
        chat_id = str(payload.get('id', '')).strip()
        chat_dir = self._chat_dir(chat_id)
        characters_dir = chat_dir / 'characters'
        characters_dir.mkdir(parents=True, exist_ok=True)

        original_primary = payload.get('character', {}) if isinstance(payload.get('character'), dict) else {}
        participants = payload.get('participants', [])
        normalized = self._normalize_participants_for_snapshot(original_primary, participants)

        used_names: set[str] = set()
        snapped: list[dict[str, Any]] = []
        primary_key = self._character_identity_key(original_primary)
        primary_snapshot: dict[str, Any] | None = None

        for participant in normalized:
            snapshot = self._snapshot_character(chat_id, participant, used_names)
            snapped.append(snapshot)
            if primary_snapshot is None and self._character_identity_key(snapshot) == primary_key:
                primary_snapshot = snapshot

        if primary_snapshot is None and snapped:
            primary_snapshot = snapped[0]

        if primary_snapshot is not None:
            payload['character'] = deepcopy(primary_snapshot)
            payload['participants'] = [deepcopy(primary_snapshot)] + [
                deepcopy(item) for item in snapped
                if self._character_identity_key(item) != self._character_identity_key(primary_snapshot)
            ]
        else:
            payload['character'] = {}
            payload['participants'] = []

        return payload

    def _normalize_participants_for_snapshot(
        self,
        primary_character: dict[str, Any],
        participants: Any,
    ) -> list[dict[str, Any]]:
        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add_candidate(candidate: Any) -> None:
            if not isinstance(candidate, dict):
                return
            key = self._character_identity_key(candidate)
            if key in seen:
                return
            seen.add(key)
            ordered.append(deepcopy(candidate))

        add_candidate(primary_character)
        if isinstance(participants, list):
            for item in participants:
                add_candidate(item)
        return ordered

    @staticmethod
    def _paths_point_to_same_file(source: Path, target: Path) -> bool:
        try:
            return source.resolve() == target.resolve()
        except Exception as exc:
            logger.debug('Falling back to string path comparison for %s and %s: %s', source, target, exc)
            return str(source) == str(target)

    def _snapshot_character(
        self,
        chat_id: str,
        character: dict[str, Any],
        used_names: set[str],
    ) -> dict[str, Any]:
        participant_name = self._participant_folder_name(character, used_names)
        participant_dir = self._chat_dir(chat_id) / 'characters' / participant_name
        participant_dir.mkdir(parents=True, exist_ok=True)

        snapshot = deepcopy(character)

        avatar_local = ''
        avatar_value = str(snapshot.get('avatar_path', '')).strip()
        if avatar_value:
            avatar_source = Path(avatar_value).expanduser()
            if avatar_source.exists() and avatar_source.is_file():
                avatar_target = participant_dir / f"avatar{avatar_source.suffix.lower() or '.img'}"
                if not self._paths_point_to_same_file(avatar_source, avatar_target):
                    shutil.copy2(avatar_source, avatar_target)
                avatar_local = str(avatar_target)

        if not avatar_local:
            existing_avatars = sorted(participant_dir.glob('avatar.*'))
            if existing_avatars:
                avatar_local = str(existing_avatars[0])

        original_card_file = str(snapshot.get('card_file', '')).strip()
        if original_card_file:
            source_card = Path(original_card_file).expanduser()
            if source_card.exists() and source_card.is_file():
                mirrored_source = participant_dir / source_card.name
                try:
                    if not self._paths_point_to_same_file(source_card, mirrored_source):
                        shutil.copy2(source_card, mirrored_source)
                except Exception as exc:
                    logger.warning('Failed to mirror source character card %s into %s: %s', source_card, mirrored_source, exc)
                snapshot['source_card_file'] = str(source_card)

        original_pack_dir = str(snapshot.get('pack_dir', '')).strip()
        if original_pack_dir:
            snapshot['source_pack_dir'] = original_pack_dir

        static_target = participant_dir / 'character_static.json'
        memory_target = participant_dir / 'memory.json'
        local_json = participant_dir / 'character.json'

        snapshot['avatar_path'] = avatar_local
        snapshot['pack_dir'] = str(participant_dir)
        snapshot['card_file'] = str(local_json)
        snapshot['static_file'] = str(static_target)
        snapshot['memory_file'] = str(memory_target)
        snapshot['chat_asset_dir'] = str(participant_dir)

        static_target.write_text(json.dumps(extract_character_static(snapshot), indent=2), encoding='utf-8')
        memory_target.write_text(json.dumps(extract_character_memory(snapshot), indent=2), encoding='utf-8')
        local_json.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        return snapshot

    @staticmethod
    def _character_identity_key(character: dict[str, Any]) -> str:
        character_id = str(character.get('id', '')).strip()
        if character_id:
            return f'id:{character_id}'
        name = str(character.get('name', '')).strip().lower()
        if name:
            return f'name:{name}'
        return 'unknown'

    def _participant_folder_name(self, character: dict[str, Any], used_names: set[str]) -> str:
        source = str(character.get('slug', '')).strip() or str(character.get('id', '')).strip() or str(character.get('name', '')).strip()
        base = ''.join(ch.lower() if ch.isalnum() else '_' for ch in source).strip('_')
        base = '_'.join(part for part in base.split('_') if part) or 'character'
        candidate = base
        counter = 2
        while candidate in used_names:
            candidate = f'{base}_{counter}'
            counter += 1
        used_names.add(candidate)
        return candidate

    def _generate_chat_id(self, seed: str) -> str:
        base = ''.join(ch.lower() if ch.isalnum() else '_' for ch in seed).strip('_')
        base = '_'.join(part for part in base.split('_') if part)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix = base or 'chat'
        candidate = f'{prefix}_{timestamp}'
        counter = 2
        while self._chat_exists(candidate):
            candidate = f'{prefix}_{timestamp}_{counter}'
            counter += 1
        return candidate
