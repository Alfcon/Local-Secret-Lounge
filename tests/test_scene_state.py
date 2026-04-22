from __future__ import annotations

import unittest

from core.scene_state import SceneStateMachine


class SceneStateMachineTests(unittest.TestCase):
    def test_tracks_participants_and_phase_changes(self) -> None:
        machine = SceneStateMachine(default_location='Perth')
        machine.set_participants([{'name': 'Maya'}, {'name': 'Sophia'}])
        machine.apply_message(text='Maya argues angrily in the Library.', role='assistant', speaker='Maya')
        state = machine.snapshot()

        self.assertEqual(state['phase'], 'escalation')
        self.assertEqual(state['tension'], 'high')
        self.assertIn('Maya', state['active_participants'])
        self.assertTrue(state['location'])

    def test_registers_resolution_and_hooks(self) -> None:
        machine = SceneStateMachine()
        machine.apply_message(text='Why is the door open?', role='user', speaker='Ella')
        machine.apply_message(text='They breathe and apologize.', role='assistant', speaker='Maya')
        state = machine.snapshot()

        self.assertEqual(state['phase'], 'cooldown')
        self.assertIn('Why is the door open?', state['unresolved_hooks'])


if __name__ == '__main__':
    unittest.main()
