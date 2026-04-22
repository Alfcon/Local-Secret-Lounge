        speaker_label_line = (
            'The UI already shows the speaker name. In narration, do not keep repeating the full character name at the '
            'start of every paragraph when a natural pronoun or shorter phrasing would read better.'
        )
        no_meta_line = (
            'Never ask the user how to proceed, and never add numbered fragments, timestamps, or speaker labels inside the reply body.'
        )
        multi_char_line = (
            'When multiple characters are present, format their dialogue as [HH:MM] Speaker Name: text to distinguish speakers.'
        ) if len(self.participants) > 1 else ""
        no_reasoning_leak_line = (
            'Never expose internal reasoning, numbered observations, choice lists, ranked alternatives, or incomplete sentence fragments. '
            'Output only the final in-world narration and dialogue.'
        )
