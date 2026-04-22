from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.memory_store import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def test_semantic_search_ranks_relevant_memory_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / 'memory.sqlite3')
            participants = [{'id': 'maya', 'name': 'Maya', 'description': 'Journalism student', 'system_prompt': 'Careful speaker'}]
            store.upsert_character_context('chat-1', participants)
            store.add_message_memory(chat_id='chat-1', participants=participants, role='assistant', speaker='Maya', content='Maya keeps her notebook hidden in the library desk.')
            store.add_message_memory(chat_id='chat-1', participants=participants, role='assistant', speaker='Maya', content='The café closes early on Sundays.')

            results = store.search(chat_id='chat-1', query='Where did Maya leave her notebook?', participant_ids=['maya'])

            self.assertTrue(results)
            self.assertIn('notebook', results[0].content.lower())


if __name__ == '__main__':
    unittest.main()
