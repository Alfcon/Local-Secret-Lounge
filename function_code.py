    def _build_system_prompt(self) -> str:
        assets = self.prompt_loader.load_for_character(self.character)
        base_prompt = self._personalize_text(str(self.character.get('system_prompt', '')).strip())
        character_name = str(self.character.get('name', 'The character')).strip() or 'The character'
        identity_line = (
            f"The user's preferred name is {self.user_display_name}. Address them by that name when it feels natural."
        )
        narration_line = (
            f"Write all actions, narration, and scene description in third person using '{character_name}' "
            'or the appropriate third-person name form, never first person.'
        )
        natural_flow_line = (
            'Keep the output natural and in-scene. Do not add meta lines, separator lines, or stage directions for the UI.'
        )
        speaker_label_line = (
            'The UI already shows the speaker name. In narration, do not keep repeating the full character name at the '
            'start of every paragraph when a natural pronoun or shorter phrasing would read better.'
        )
        no_meta_line = (
            'Never ask the user how to proceed, and never add numbered fragments, timestamps, or speaker labels inside the reply body.'
        )
        no_reasoning_leak_line = (
            'Never expose internal reasoning, numbered observations, choice lists, ranked alternatives, or incomplete sentence fragments. '
            'Output only the final in-world narration and dialogue.'
        )
        continuity_line = (
            'Before every reply, silently review the canonical participant facts below. Do not contradict them, do not '
            'replace established relationships, and do not invent a new roommate, best friend, partner, or companion when '
            'the character files already identify one.'
        )
        thought_style_line = (
            'When a character has a private thought, wrap only the thought text in single asterisks so the UI can render it in italics. '
            'Do not use markdown bold anywhere in replies.'
        )
        ending_line = (
            'End naturally on dialogue, action, or atmosphere. Do not append setup instructions, binary choice prompts, '
            'or a prompt for the next turn.'
        )
        no_choice_prompt_line = (
            'Do not end the reply with option prompts or suggested next moves. Let the scene stand on its own.'
        )
        no_echo_line = (
            'Do not repeat, paraphrase, or restart the opening greeting or scene intro on later turns. '
            'The scene has already begun; each reply must advance what just happened.'
        )

        scene_lines = [
            'This is an unfolding story scene, not an isolated single-message answer.',
            f'Current focal character: {character_name}.',
            "Do not decide the user's actions, dialogue, feelings, or internal thoughts for them."
        ]
        story_location = self._story_location_text()
        if story_location:
            scene_lines.append(
                f'The default story location for this chat is {story_location}. Keep environmental details broadly consistent with that location unless the user clearly moves the scene somewhere else.'
            )
        starting_scenario = self._personalize_text(str(self.character.get('starting_scenario', '')).strip())
        scenario_in_history = any(
            str(m.get('role', '')).strip() == 'scene'
            and str(m.get('format', '')).strip() == 'scenario'
            for m in self.messages
            if isinstance(m, dict)
        )
        if starting_scenario and not scenario_in_history:
            scene_lines.append(f'Opening scene context: {starting_scenario}')
        if len(self.participants) > 1:
            scene_lines.append(
                'Other scene participants are present. Keep them consistent with the profile details below.'
            )
            scene_lines.append(
                'If it helps continuity, you may mention their visible actions or dialogue, but do not invent extra named participants.'
            )
            scene_lines.append(
                'When multiple characters speak, use [HH:MM] Character Name: format for each character\'s dialogue.'
            )
        if self.rolling_summary:
            scene_lines.append('Earlier conversation summary:')
            scene_lines.append(self.rolling_summary)

        rendered_scene_template = self.prompt_loader.render_scene_template(
            assets.scene_template,
            scene_summary=self.rolling_summary or starting_scenario or 'Scene just started.',
            character_state=self._character_state_text(),
            recent_exchange=self._recent_exchange_text(),
            user_message=self._latest_user_message_text(),
        )
        if rendered_scene_template:
            scene_lines.append('Rendered scene template context:')
            scene_lines.append(rendered_scene_template)

        participant_lines = ['Scene participants:']
        for participant in self.participants:
            name = str(participant.get('name', 'Character')).strip() or 'Character'
            summary_bits: list[str] = []
            title = str(participant.get('title', '')).strip()
            description = str(participant.get('description', '')).strip()
            lore = str(participant.get('world_lore_notes', '')).strip().replace('\n', ' ')
            if title:
                summary_bits.append(title)
            if description:
                summary_bits.append(description)
            if lore:
                summary_bits.append(lore[:260])
            summary_text = ' | '.join(bit for bit in summary_bits if bit)
            participant_lines.append(f'- {name}: {summary_text or "No extra details established yet."}')

        canon_lines = self._participant_canon_lines()
        memory_lines = self._participant_memory_lines()
        voice_lines = self._participant_voice_lines()
        retrieval_lines = self._retrieval_augmented_lines()
        scene_state_lines = self.scene_state_machine.prompt_lines()

        parts = [part for part in [base_prompt, assets.system_rules, assets.output_format, assets.character_rules, identity_line, narration_line, natural_flow_line, speaker_label_line, no_meta_line, no_reasoning_leak_line, continuity_line, thought_style_line, ending_line, no_choice_prompt_line, no_echo_line] if part]
        parts.append('\n'.join(scene_lines))
        parts.append('\n'.join(scene_state_lines))
        parts.append('\n'.join(participant_lines))
        parts.append('\n'.join(canon_lines))
        if voice_lines:
            parts.append('\n'.join(voice_lines))
        parts.append('\n'.join(memory_lines))
        if retrieval_lines:
            parts.append('\n'.join(retrieval_lines))
        return '\n\n'.join(parts)

