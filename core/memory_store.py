from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.character_state import build_memory_prompt_lines
from core.paths import get_data_dir


DB_PATH = get_data_dir() / 'memory_store.sqlite3'
TOKEN_RE = re.compile(r"[a-z0-9']+", flags=re.IGNORECASE)


@dataclass(slots=True)
class RetrievalItem:
    source_type: str
    speaker: str
    participant_id: str
    score: float
    content: str
    metadata: dict[str, Any]


class MemoryStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    participant_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    role TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(chat_id, participant_id, source_type, content_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_entries_chat ON memory_entries(chat_id);
                CREATE INDEX IF NOT EXISTS idx_memory_entries_participant ON memory_entries(participant_id);
                CREATE INDEX IF NOT EXISTS idx_memory_entries_created ON memory_entries(created_at);
                '''
            )

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r'\s+', ' ', str(value or '')).strip()

    @staticmethod
    def _content_hash(value: str) -> str:
        return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()

    @staticmethod
    def _hashed_vector(text: str, *, dims: int = 128) -> list[float]:
        values = [0.0] * dims
        tokens = TOKEN_RE.findall(str(text or '').lower())
        if not tokens:
            return values
        for token in tokens:
            digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
            index = int.from_bytes(digest, byteorder='big', signed=False) % dims
            values[index] += 1.0
        norm = math.sqrt(sum(item * item for item in values))
        if norm <= 0:
            return values
        return [item / norm for item in values]

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        size = min(len(left), len(right))
        return sum(left[index] * right[index] for index in range(size))

    @staticmethod
    def _token_overlap(query: str, text: str) -> float:
        query_tokens = set(TOKEN_RE.findall(str(query or '').lower()))
        text_tokens = set(TOKEN_RE.findall(str(text or '').lower()))
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = query_tokens & text_tokens
        return len(overlap) / max(1, len(query_tokens))

    def upsert_character_context(self, chat_id: str, participants: list[dict[str, Any]]) -> None:
        for participant in participants:
            participant_id = str(participant.get('id', '')).strip() or str(participant.get('name', '')).strip().lower() or 'unknown'
            speaker = str(participant.get('name', 'Character')).strip() or 'Character'
            snippets: list[tuple[str, str]] = []
            title = str(participant.get('title', '')).strip()
            description = str(participant.get('description', '')).strip()
            lore = str(participant.get('world_lore_notes', '')).strip()
            system_prompt = str(participant.get('system_prompt', '')).strip()
            if title:
                snippets.append(('character_title', f'{speaker}: {title}'))
            if description:
                snippets.append(('character_description', f'{speaker}: {description}'))
            if lore:
                snippets.append(('character_lore', f'{speaker}: {lore}'))
            if system_prompt:
                snippets.append(('character_prompt', f'{speaker}: {system_prompt}'))
            for line in build_memory_prompt_lines(participant):
                snippets.append(('character_memory', line))
            for source_type, content in snippets:
                self.add_memory_entry(
                    chat_id=chat_id,
                    participant_id=participant_id,
                    source_type=source_type,
                    role='system',
                    speaker=speaker,
                    content=content,
                    metadata={'kind': 'character_context'},
                )

    def add_message_memory(
        self,
        *,
        chat_id: str,
        participants: list[dict[str, Any]],
        role: str,
        speaker: str,
        content: str,
    ) -> None:
        cleaned = self._normalize_text(content)
        if not cleaned:
            return
        participant_id = 'conversation'
        for participant in participants:
            name = str(participant.get('name', '')).strip()
            if name and name.casefold() == str(speaker or '').strip().casefold():
                participant_id = str(participant.get('id', '')).strip() or name.lower()
                break
        self.add_memory_entry(
            chat_id=chat_id,
            participant_id=participant_id,
            source_type='message',
            role=str(role or '').strip() or 'assistant',
            speaker=str(speaker or '').strip() or str(role or '').strip() or 'speaker',
            content=cleaned,
            metadata={'kind': 'chat_message'},
        )

    def add_memory_entry(
        self,
        *,
        chat_id: str,
        participant_id: str,
        source_type: str,
        role: str,
        speaker: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        cleaned = self._normalize_text(content)
        if not cleaned:
            return
        vector = self._hashed_vector(cleaned)
        payload = {
            'chat_id': str(chat_id).strip(),
            'participant_id': str(participant_id).strip() or 'conversation',
            'source_type': str(source_type).strip() or 'memory',
            'role': str(role).strip() or 'system',
            'speaker': str(speaker).strip() or 'speaker',
            'content': cleaned,
            'content_hash': self._content_hash(cleaned),
            'vector_json': json.dumps(vector),
            'metadata_json': json.dumps(metadata or {}, ensure_ascii=False),
            'created_at': self._utc_now_iso(),
        }
        with self._connect() as connection:
            connection.execute(
                '''
                INSERT OR REPLACE INTO memory_entries (
                    chat_id, participant_id, source_type, role, speaker, content, content_hash, vector_json, metadata_json, created_at
                ) VALUES (
                    :chat_id, :participant_id, :source_type, :role, :speaker, :content, :content_hash, :vector_json, :metadata_json, :created_at
                )
                ''',
                payload,
            )

    def search(
        self,
        *,
        chat_id: str,
        query: str,
        participant_ids: list[str] | None = None,
        limit: int = 6,
    ) -> list[RetrievalItem]:
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return []
        query_vector = self._hashed_vector(normalized_query)
        selected_ids = [str(item).strip() for item in (participant_ids or []) if str(item).strip()]
        with self._connect() as connection:
            if selected_ids:
                placeholders = ','.join('?' for _ in selected_ids)
                rows = connection.execute(
                    f'''
                    SELECT * FROM memory_entries
                    WHERE chat_id = ? AND (participant_id IN ({placeholders}) OR participant_id = 'conversation')
                    ORDER BY id DESC
                    LIMIT 400
                    ''',
                    [str(chat_id).strip(), *selected_ids],
                ).fetchall()
            else:
                rows = connection.execute(
                    '''
                    SELECT * FROM memory_entries
                    WHERE chat_id = ?
                    ORDER BY id DESC
                    LIMIT 400
                    ''',
                    [str(chat_id).strip()],
                ).fetchall()

        ranked: list[RetrievalItem] = []
        for row in rows:
            content = self._normalize_text(row['content'])
            if not content:
                continue
            try:
                vector = json.loads(row['vector_json'])
            except json.JSONDecodeError:
                vector = self._hashed_vector(content)
            semantic_score = self._cosine_similarity(query_vector, [float(item) for item in vector])
            overlap_score = self._token_overlap(normalized_query, content)
            recency_bonus = min(0.1, max(0.0, (float(row['id']) % 50) / 500.0))
            score = (semantic_score * 0.72) + (overlap_score * 0.23) + recency_bonus
            if score <= 0.05:
                continue
            try:
                metadata = json.loads(row['metadata_json']) if row['metadata_json'] else {}
            except json.JSONDecodeError:
                metadata = {}
            ranked.append(
                RetrievalItem(
                    source_type=str(row['source_type']),
                    speaker=str(row['speaker']),
                    participant_id=str(row['participant_id']),
                    score=float(score),
                    content=content,
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[: max(1, int(limit))]
