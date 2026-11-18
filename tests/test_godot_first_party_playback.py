"""Publisher transaction tests with synthetic bytes and a doubled Godot process."""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json
import tempfile
import unittest

from fixtures.godot_registered_retention_logic import RetentionFixture
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_runtime_contract import CODE_FILES, DATA_FILES
from ucc.jobs import godot_first_party_playback as playback
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.godot_registered_body_inputs import RegisteredBodyInputs
from ucc.jobs.runner import WorkerFailure


class FirstPartyGodotPlaybackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fixture = RetentionFixture(self.root)
        self.runtime_names = (CODE_FILES - {'ucc_skin_adapter.gd'}) | DATA_FILES | {'project.godot', 'playback.gd'}
        self.assets = self.root/'SYNTHETIC_ASSETS'
        self.assets.mkdir()
        self.scripts = self.root/'SYNTHETIC_SCRIPTS'
        self.scripts.mkdir()
        self.catalog = self.root/'catalog'
        self.catalog.mkdir()
        self.database = self.marker(self.catalog, 'catalog.sqlite')
        self.godot = self.marker(self.root, 'unit-console.exe')
        self.godot_main = self.marker(self.root, 'unit-main.exe')
        self.export_parent = self.root/'exports'
        self.export_parent.mkdir()
        self.destination = plan_destination(self.export_parent/'PRIVATE_UNIT', self.fixture.store.root)
        self.prepared = SimpleNamespace(
            diagnostic=SimpleNamespace(receipt_sha256='a'*64),
            provenance=SimpleNamespace(sha256='b'*64),
        )
        needed = (self.runtime_names - {'playback.gd'}
                  | {'configure.gd', 'ucc_skin_adapter.gd', 'character.glb',
                     'skin_plan.json', 'bind_source_indices.json'})
        data = {name: self.marker(self.assets, name) for name in sorted(needed)}
        records = {name: self.marker_record(path) for name, path in data.items()}
        self.input_guard = Mock()
        self.inputs = RegisteredBodyInputs(data, records, {}, self.input_guard)
        scripts = {name: self.marker(self.scripts, name)
                   for name in ('project.godot', 'pack.gd', 'playback.gd', 'verify.gd')}
        self.report = {
            'status': 'PRIVATE_GODOT_PLAYBACK_REOPENED', 'schema_version': 1,
            'native_animation_advanced': True, 'native_loop_wrapped': True,
            'corrected_normal_stream_drawn': True, 'rendered_motion_observed': True,
            'private_pixels_retained': False,
        }
        self.fail_script = None
        self.commands = []
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.admit = stack.enter_context(patch.object(
            playback, 'admit_first_party_godot_animation', return_value=self.inputs,
        ))
        stack.enter_context(patch.object(playback, 'bundled_registered_playback_paths', return_value=scripts))
        self.run_process = stack.enter_context(patch.object(playback, 'run_process', side_effect=self.native))

    def marker(self, directory, name):
        path = directory/name
        path.write_bytes(('UNIT_NOT_AN_ENGINE_ASSET:'+name).encode())
        return path

    @staticmethod
    def marker_record(path):
        raw = path.read_bytes()
        return {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}

    def native(self, command, logs, **kwargs):
        self.commands.append(command)
        cwd = Path(command[command.index('--path')+1])
        script = command[command.index('--script')+1] if '--script' in command else None
        if script == 'res://pack.gd':
            self.marker(cwd, 'character.tscn')
        elif script == 'res://verify.gd':
            Path(command[-1]).write_bytes(canonical_bytes(self.report))
        return SimpleNamespace(return_code=2 if self.fail_script and script == self.fail_script else 0,
                               cancelled=False, timed_out=False, elapsed_seconds=0.01)

    def publish(self):
        return playback.publish_first_party_godot_playback(
            self.fixture.store, result=self.prepared, selection=self.fixture.selection,
            database_path=self.database, permissions=self.fixture.permissions,
            godot_exe=self.godot, godot_main_exe=self.godot_main, destination=self.destination,
        )

    def test_fresh_reopen_precedes_publication_of_exact_portable_runtime_and_receipt(self):
        result = self.publish()
        target = self.destination.path
        self.assertEqual(result.directory, target)
        self.assertEqual(self.run_process.call_count, 5)
        pack, verify = self.commands[-2:]
        self.assertIn('res://pack.gd', pack)
        self.assertIn('res://verify.gd', verify)
        self.assertEqual(pack[pack.index('--rendering-method')+1], 'mobile')
        self.assertEqual(pack[pack.index('--rendering-driver')+1], 'vulkan')
        self.assertNotIn('--headless', pack)
        self.assertNotEqual(Path(pack[2]), Path(verify[2]))
        portable = self.runtime_names | {'character.tscn', 'playback.json'}
        self.assertEqual({path.name for path in target.iterdir()}, portable | {'playback-receipt.json'})
        raw = (target/'playback-receipt.json').read_bytes()
        receipt = json.loads(raw)
        self.assertEqual(result.receipt_sha256, sha256(raw).hexdigest())
        self.assertEqual(receipt['policy'], 'UCC_PRIVATE_FIRST_PARTY_GODOT_PLAYBACK_RECEIPT_V1')
        self.assertEqual(receipt['binding_sha256'], self.fixture.selection.binding_sha256)
        self.assertEqual(receipt['diagnostic_receipt_sha256'], self.prepared.diagnostic.receipt_sha256)
        self.assertEqual(receipt['runtime_provenance_sha256'], self.prepared.provenance.sha256)
        self.assertEqual(receipt['observed'], self.report)
        self.assertIs(receipt['private_local_only'], True)
        self.assertIs(receipt['distribution_review_complete'], False)
        self.assertIs(receipt['material_appearance_approved'], False)
        expected_hashes = {name: self.marker_record(target/name)['sha256'] for name in portable}
        self.assertEqual(receipt['files'], expected_hashes)
        manifest = json.loads((target/'playback.json').read_bytes())
        self.assertEqual((manifest['frames'], manifest['fps']), (300, 30))
        self.assertEqual(manifest['files'], {name: expected_hashes[name] for name in self.runtime_names})

    def test_entire_publication_is_rejected_if_reopened_motion_was_not_observed(self):
        self.report['rendered_motion_observed'] = False
        with self.assertRaisesRegex(ValidationError, 'did not verify'):
            self.publish()
        self.assertEqual(self.run_process.call_count, 5)
        self.assertFalse(self.destination.path.exists())

    def test_failed_packing_does_not_attempt_reopen_or_publish(self):
        self.fail_script = 'res://pack.gd'
        with self.assertRaisesRegex(WorkerFailure, 'pack failed'):
            self.publish()
        self.assertEqual(self.run_process.call_count, 4)
        self.assertFalse(self.destination.path.exists())

    def test_unlisted_staged_bytes_never_reach_the_chosen_destination(self):
        copy_file = playback.copy_file

        def copy_with_unlisted_sibling(source, destination, row, budget):
            copy_file(source, destination, row, budget)
            if destination.parent.name.startswith('.ucc-export-'):
                self.marker(destination.parent, 'unlisted-private-source.blend')

        with patch.object(playback, 'copy_file', side_effect=copy_with_unlisted_sibling):
            with self.assertRaisesRegex(ProjectStorageError, 'staging changed'):
                self.publish()
        self.assertFalse(self.destination.path.exists())

    def test_source_revoked_at_rename_withdraws_unchanged_owned_export(self):
        rename = playback.rename_new

        def change_authority(source, destination):
            rename(source, destination)
            if destination == self.destination.path:
                self.input_guard.side_effect = ValidationError('UNIT source use revoked during rename')

        with patch.object(playback, 'rename_new', side_effect=change_authority) as moves:
            with self.assertRaisesRegex(ValidationError, 'revoked during rename'):
                self.publish()

        self.assertFalse(self.destination.path.exists())
        self.assertEqual(moves.call_count, 2)
        published_from, published_to = moves.call_args_list[0].args
        self.assertEqual(moves.call_args_list[1].args, (published_to, published_from))

    def test_source_revocation_preserves_foreign_content_added_at_destination(self):
        rename = playback.rename_new

        def add_foreign_bytes(source, destination):
            rename(source, destination)
            if destination == self.destination.path:
                self.marker(destination, 'FOREIGN')
                self.input_guard.side_effect = ValidationError('UNIT source use revoked during rename')

        with patch.object(playback, 'rename_new', side_effect=add_foreign_bytes) as moves:
            with self.assertRaisesRegex(ValidationError, 'revoked during rename') as failure:
                self.publish()

        moves.assert_called_once()
        self.assertIn('external files are retained', '\n'.join(failure.exception.__notes__))
        self.assertEqual((self.destination.path/'FOREIGN').read_bytes(), b'UNIT_NOT_AN_ENGINE_ASSET:FOREIGN')
