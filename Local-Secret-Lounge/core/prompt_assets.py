from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from core.paths import get_app_root


PROMPTS_DIR = get_app_root() / 'prompts'


@dataclass(slots=True)
class PromptAssets:
    system_rules: str = ''
    output_format: str = ''
    scene_template: str = ''
    character_rules: str = ''


class PromptAssetLoader:
    def __init__(self, prompts_dir: Path | None = None) -> None:
        self.prompts_dir = prompts_dir or PROMPTS_DIR

    @staticmethod
    def _slug_candidates(character: dict[str, Any]) -> list[str]:
        values = [
            str(character.get('slug', '')).strip(),
            str(character.get('id', '')).strip().removeprefix('discover_').removeprefix('story_'),
            re.sub(r'[^a-z0-9]+', '_', str(character.get('name', '')).strip().lower()).strip('_'),
        ]
        results: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip().lower()
            if cleaned and cleaned not in seen:
                results.append(cleaned)
                seen.add(cleaned)
        return results

    def _read_text(self, filename: str) -> str:
        path = self.prompts_dir / filename
        if not path.exists() or not path.is_file():
            return ''
        try:
            return path.read_text(encoding='utf-8').strip()
        except OSError:
            return ''

    def load_for_character(self, character: dict[str, Any]) -> PromptAssets:
        assets = PromptAssets(
            system_rules=self._read_text('system_rules.txt'),
            output_format=self._read_text('output_format.txt'),
            scene_template=self._read_text('scene_template.txt'),
        )
        for slug in self._slug_candidates(character):
            filename = f'character_rules_{slug}.txt'
            loaded = self._read_text(filename)
            if loaded:
                assets.character_rules = loaded
                break
        return assets

    @staticmethod
    def render_scene_template(
        template: str,
        *,
        scene_summary: str,
        character_state: str,
        recent_exchange: str,
        user_message: str,
    ) -> str:
        rendered = str(template or '')
        replacements = {
            '{scene_summary}': scene_summary,
            '{character_state}': character_state,
            '{recent_exchange}': recent_exchange,
            '{user_message}': user_message,
            '{{scene_summary}}': scene_summary,
            '{{character_state}}': character_state,
            '{{recent_exchange}}': recent_exchange,
            '{{user_message}}': user_message,
        }
        for token, value in replacements.items():
            rendered = rendered.replace(token, value)
        return rendered.strip()
