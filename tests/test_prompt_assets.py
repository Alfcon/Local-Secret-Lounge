from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.prompt_assets import PromptAssetLoader


class PromptAssetLoaderTests(unittest.TestCase):
    def test_loads_base_and_character_specific_prompt_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts_dir = Path(temp_dir)
            (prompts_dir / 'system_rules.txt').write_text('system rules', encoding='utf-8')
            (prompts_dir / 'output_format.txt').write_text('format rules', encoding='utf-8')
            (prompts_dir / 'scene_template.txt').write_text('Scene: {scene_summary}', encoding='utf-8')
            (prompts_dir / 'character_rules_maya_johnson.txt').write_text('maya rules', encoding='utf-8')
            loader = PromptAssetLoader(prompts_dir)

            assets = loader.load_for_character({'name': 'Maya Johnson'})

            self.assertEqual(assets.system_rules, 'system rules')
            self.assertEqual(assets.output_format, 'format rules')
            self.assertEqual(assets.scene_template, 'Scene: {scene_summary}')
            self.assertEqual(assets.character_rules, 'maya rules')

    def test_renders_scene_template(self) -> None:
        rendered = PromptAssetLoader.render_scene_template(
            'Summary={scene_summary} User={user_message}',
            scene_summary='night train',
            character_state='steady',
            recent_exchange='hello',
            user_message='sit down',
        )
        self.assertEqual(rendered, 'Summary=night train User=sit down')


if __name__ == '__main__':
    unittest.main()
