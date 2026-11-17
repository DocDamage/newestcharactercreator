"""Owned configuration lifecycle faults; all engine/native gates are doubled."""
import json
from pathlib import Path
import unittest
import test_godot_registered_body_target as coordination
from ucc.core.errors import ProjectStorageError
from ucc.jobs.runner import WorkerFailure


class GeneratedProjectLifecycleTests(unittest.TestCase):
    setUp = coordination.RegisteredBodyCoordinatorTests.setUp
    run_child = coordination.RegisteredBodyCoordinatorTests.run_child
    verify_outputs = coordination.RegisteredBodyCoordinatorTests.verify_outputs
    invoke = coordination.RegisteredBodyCoordinatorTests.invoke
    receipts = coordination.RegisteredBodyCoordinatorTests.receipts

    def replace_owned_file(self, engine, name):
        replacement = self.f.root / ('replacement-' + str(len(self.calls)))
        replacement.write_bytes((engine / name).read_bytes())
        replacement.replace(engine / name)

    def test_identical_editor_rewrites_are_recorded_with_raw_outcomes(self):
        original = self.run_child

        def child(command, *args, **kwargs):
            outcome = original(command, *args, **kwargs)
            if len(self.calls) in (1, 3):
                self.replace_owned_file(Path(command[command.index('--path') + 1]), 'project.godot')
            return outcome

        self.runner.side_effect = child
        result = self.invoke()
        receipt = json.loads((result.directory / 'diagnostic_receipt.json').read_bytes())
        for row in receipt['commands']:
            folder = result.directory / row['phase']
            raw = json.loads((folder / 'process_outcome.json').read_bytes())
            expected = {k: v for k, v in row.items() if k != 'generated_project_transition'}
            self.assertEqual(raw, expected)
            self.assertEqual(json.loads((folder / 'outcome.json').read_bytes()), row)
            if row['phase'] in ('initial-import', 'configured-import'):
                transition = row['generated_project_transition']
                self.assertEqual(transition['phase'], row['phase'])
                self.assertNotEqual(transition['previous_identity'], transition['new_identity'])
            else:
                self.assertNotIn('generated_project_transition', row)

    def test_changed_editor_config_rejects_but_retains_actual_child_outcome(self):
        original = self.run_child

        def child(command, *args, **kwargs):
            outcome = original(command, *args, **kwargs)
            engine = Path(command[command.index('--path') + 1])
            (engine / 'project.godot').write_bytes(b'NONSHIPPING_CHANGED_CONFIGURATION')
            return outcome

        self.runner.side_effect = child
        with self.assertRaises(ProjectStorageError):
            self.invoke()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.receipts(), [])
        [work] = list((self.f.store.root / '.ucc-jobs').glob('registered-body300-*'))
        raw = json.loads((work / 'initial-import/process_outcome.json').read_bytes())
        self.assertEqual(raw['return_code'], 0)
        self.assertFalse((work / 'initial-import/outcome.json').exists())

    def test_identical_config_replacement_in_noneditor_phase_rejects(self):
        original = self.run_child

        def child(command, *args, **kwargs):
            outcome = original(command, *args, **kwargs)
            if len(self.calls) == 2:
                self.replace_owned_file(Path(command[command.index('--path') + 1]), 'project.godot')
            return outcome

        self.runner.side_effect = child
        with self.assertRaises(ProjectStorageError):
            self.invoke()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.receipts(), [])

    def test_editor_cannot_replace_another_program_with_identical_bytes(self):
        original = self.run_child

        def child(command, *args, **kwargs):
            outcome = original(command, *args, **kwargs)
            self.replace_owned_file(Path(command[command.index('--path') + 1]), 'validate.gd')
            return outcome

        self.runner.side_effect = child
        with self.assertRaises(ProjectStorageError):
            self.invoke()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.receipts(), [])

    def test_native_crash_reports_original_exit_before_config_identity_error(self):
        original = self.run_child

        def child(command, *args, **kwargs):
            original(command, *args, **kwargs)
            self.replace_owned_file(Path(command[command.index('--path') + 1]), 'project.godot')
            return coordination.ProcessOutcome(0xC0000005, '', '', .001)

        self.runner.side_effect = child
        with self.assertRaisesRegex(WorkerFailure, 'exit code 3221225477'):
            self.invoke()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.receipts(), [])
        [work] = list((self.f.store.root / '.ucc-jobs').glob('registered-body300-*'))
        raw = json.loads((work / 'initial-import/process_outcome.json').read_bytes())
        self.assertEqual(raw['return_code'], 0xC0000005)
        self.assertFalse((work / 'initial-import/outcome.json').exists())
