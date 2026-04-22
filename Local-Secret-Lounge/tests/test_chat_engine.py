from __future__ import annotations

import unittest

from core.chat_engine import ChatEngine
from core.settings_manager import SettingsManager


class ChatEngineTests(unittest.TestCase):
    def test_estimate_message_tokens_is_nonzero(self) -> None:
        engine = ChatEngine(SettingsManager())
        count = engine.estimate_message_tokens(messages=[
            {'role': 'system', 'content': 'Rules'},
            {'role': 'user', 'content': 'Hello there'},
        ])
        self.assertGreater(count, 0)

    def test_clean_generated_text_removes_meta_prompt(self) -> None:
        cleaned = ChatEngine.clean_generated_text('Maya smiles.\n\nDo you want to continue?')
        self.assertEqual(cleaned, 'Maya smiles.')


if __name__ == '__main__':
    unittest.main()
