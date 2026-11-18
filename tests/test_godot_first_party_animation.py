"""Host orchestration tests using nonshipping source bytes and doubled engine phases."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
from hashlib import sha256
import io
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID
import tempfile
import unittest

from fixtures.godot_registered_retention_logic import RetentionFixture
from ucc.cli import main as cli_main
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.export.godot_runtime_contract import CODE_FILES
from ucc.jobs import godot_first_party_animation as animation
from ucc.jobs.godot_registered_body_target import VerifiedRegisteredNativeBodyDiagnostic
from ucc.jobs.godot_registered_runtime_storage import RetainedRegisteredNativeInputs
from ucc.library.provenance import AssetPolicyError


class FirstPartyGodotAnimationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fixture = RetentionFixture(self.root)
        sources = self.root/'SYNTHETIC_CODE_NOT_EXECUTABLE'
        sources.mkdir()
        self.code = {name: sources/name for name in sorted(CODE_FILES)}
        for name, path in self.code.items():
            path.write_bytes(('UNIT_NOT_EXECUTABLE:'+name).encode())
        self.blender = self.marker('unit-blender.exe')
        self.worker = self.marker('unit-worker.py')
        catalog = self.root/'catalog'
        catalog.mkdir()
        self.database = catalog/'unit-catalog.sqlite'
        self.database.write_bytes(b'UNIT_MARKER_NOT_A_DATABASE')
        self.godot = self.marker('unit-godot-console.exe')
        self.godot_main = self.marker('unit-godot.exe')
        self.retained = RetainedRegisteredNativeInputs(
            self.fixture.fresh, str(UUID(int=8030)), 'e'*64, self.fixture.selection.project_id,
            self.fixture.selection.revision, self.fixture.selection.binding_sha256,
        )
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.locate = stack.enter_context(patch.object(
            animation, 'bundled_registered_correction_paths', return_value=self.code,
        ))
        self.prepare = stack.enter_context(patch.object(
            animation, 'prepare_registered_native_source', return_value=self.fixture.preparation,
        ))
        self.retain = stack.enter_context(patch.object(
            animation, 'retain_registered_native_inputs', return_value=self.retained,
        ))
        self.verify = stack.enter_context(patch.object(
            animation, 'verify_registered_native_body_runtime',
            side_effect=lambda *args, **kwargs: VerifiedRegisteredNativeBodyDiagnostic(
                self.fixture.fresh, kwargs['execution'].execution_id, 'f'*64,
            ),
        ))

    def marker(self, name):
        path = self.root/name
        path.write_bytes(('UNIT_MARKER_NEVER_EXECUTED:'+name).encode())
        return path

    def run_animation(self, **overrides):
        values = {
            'selection': self.fixture.selection, 'database_path': self.database,
            'permissions': self.fixture.permissions, 'blender_exe': self.blender,
            'worker_script': self.worker, 'godot_exe': self.godot, 'godot_main_exe': self.godot_main,
            'purpose': 'Unit admission only', 'private_local_execution_confirmed': True,
        }
        return animation.prepare_first_party_godot_animation(self.fixture.store, **(values | overrides))

    def assert_no_native_phase(self):
        self.prepare.assert_not_called()
        self.retain.assert_not_called()
        self.verify.assert_not_called()

    def test_requires_exact_private_execution_confirmation_and_purpose(self):
        for override in (
            {'private_local_execution_confirmed': False},
            {'private_local_execution_confirmed': 1},
            {'purpose': ''},
            {'selection': self.fixture.selection.to_dict()},
        ):
            with self.subTest(override=override), self.assertRaises(ValidationError):
                self.run_animation(**override)
        self.assert_no_native_phase()

    def test_first_party_code_cannot_supply_missing_or_denied_user_permissions(self):
        allowed = self.fixture.permissions
        motion = next(permission for permission in allowed if permission.asset_id.startswith('motion:'))
        without_motion = tuple(
            replace(permission, asset_id='unit-non-motion') if permission is motion else permission
            for permission in allowed
        )
        for denied in (
            allowed[:-1] + allowed[:1],
            without_motion,
            tuple(replace(permission, source_only=True) if permission is motion else permission
                  for permission in allowed),
            tuple(replace(permission, policy=replace(permission.policy, can_use_non_unreal=False))
                  if permission is motion else permission for permission in allowed),
        ):
            with self.subTest(permissions=tuple(p.asset_id for p in denied)), self.assertRaises(
                (ValidationError, AssetPolicyError),
            ):
                self.run_animation(permissions=denied)
        self.assert_no_native_phase()

    def test_partial_or_extra_correction_namespace_is_rejected_before_workers(self):
        one_file = next(iter(self.code))
        partial = {name: path for name, path in self.code.items() if name != one_file}
        extra = self.code | {'foreign.gd': self.marker('foreign.gd')}
        for resources in (partial, extra):
            self.locate.return_value = resources
            with self.subTest(names=sorted(resources)), self.assertRaises(ValidationError):
                self.run_animation()
        self.assert_no_native_phase()

    def test_pre_cancelled_operation_never_launches_a_native_phase(self):
        cancelled = Event()
        cancelled.set()
        with self.assertRaises(ProjectStorageError):
            self.run_animation(cancel=cancelled)
        self.assert_no_native_phase()

    def test_replaced_staged_program_stops_before_retention_even_with_same_bytes(self):
        def replace_staged_program(*args, **kwargs):
            runtime = kwargs['runtime_directory']
            selected = runtime/'runtime_kernel.gd'
            replacement = runtime/'sibling.tmp'
            replacement.write_bytes(selected.read_bytes())
            replacement.replace(selected)
            return self.fixture.preparation

        self.prepare.side_effect = replace_staged_program
        with self.assertRaisesRegex(ProjectStorageError, 'stage identity changed'):
            self.run_animation()
        self.prepare.assert_called_once()
        self.retain.assert_not_called()
        self.verify.assert_not_called()

    def test_forwards_exact_permissions_and_binds_execution_to_staged_code_and_engines(self):
        result = self.run_animation()
        prepare = self.prepare.call_args.kwargs
        retain = self.retain.call_args.kwargs
        verify = self.verify.call_args.kwargs
        for kwargs in (prepare, retain, verify):
            self.assertIs(kwargs['permissions'], self.fixture.permissions)
            self.assertEqual(kwargs['database_path'], self.database)
        self.assertIs(retain['selection'], self.fixture.selection)
        self.assertIs(verify['selection'], self.fixture.selection)
        self.assertEqual(prepare['binding_sha256'], self.fixture.selection.binding_sha256)
        self.assertEqual(prepare['runtime_directory'], result.runtime_directory)
        self.assertEqual(prepare['runtime_code_provenance'], result.provenance_path)
        self.assertEqual(retain['expected_production_receipt_sha256'], self.fixture.receipt_sha)
        self.assertEqual(verify['expected_production_receipt_sha256'], self.fixture.receipt_sha)
        self.assertEqual(verify['retention_id'], self.retained.retention_id)
        self.assertEqual(verify['expected_manifest_sha256'], self.retained.manifest_sha256)
        self.assertIs(result.preparation, self.fixture.preparation)
        self.assertIs(result.retained, self.retained)
        self.assertIs(result.execution, verify['execution'])
        self.assertEqual(result.diagnostic.execution_id, result.execution.execution_id)
        self.assertEqual(result.execution.retention_manifest_sha256, self.retained.manifest_sha256)
        self.assertEqual(result.execution.provenance_sha256, sha256(result.provenance_path.read_bytes()).hexdigest())
        self.assertEqual(result.execution.godot_executable_sha256, sha256(self.godot.read_bytes()).hexdigest())
        self.assertEqual(result.execution.godot_main_sha256, sha256(self.godot_main.read_bytes()).hexdigest())
        provenance = json.loads(result.provenance_path.read_bytes())
        self.assertEqual(provenance, result.provenance.to_dict())
        self.assertEqual(provenance['use'], 'PRIVATE_LOCAL_VERIFICATION_ONLY')
        self.assertIs(provenance['distribution_license_review_complete'], False)
        self.assertIs(provenance['shipping_authorized'], False)
        self.assertEqual({record.name for record in result.execution.code}, CODE_FILES)
        for record in result.execution.code:
            expected = self.code[record.name].read_bytes()
            self.assertEqual((result.runtime_directory/record.name).read_bytes(), expected)
            self.assertEqual((record.sha256, record.bytes), (sha256(expected).hexdigest(), len(expected)))

    def authorization(self):
        return {
            'schema_version': 1,
            'policy': 'UCC_PRIVATE_FIRST_PARTY_GODOT_AUTHORIZATION_V1',
            'selection': self.fixture.selection.to_dict(),
            'permissions': [permission.to_dict() for permission in self.fixture.permissions],
            'purpose': 'Unit admission only',
            'private_local_execution_confirmed': True,
        }

    def run_cli(self, authorization, *, command='prepare-godot-animation', destination=None):
        chosen = self.root/'authorization.json'
        chosen.write_text(json.dumps(authorization), encoding='utf-8')
        args = [
            command, str(self.fixture.store.root),
            '--authorization', str(chosen), '--database', str(self.database),
            '--blender', str(self.blender), '--godot', str(self.godot),
            '--godot-main', str(self.godot_main), '--timeout', '90',
        ]
        if destination is not None:
            args.extend(('--destination', str(destination)))
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_rejects_forged_authorization_without_dispatch(self):
        valid = self.authorization()
        with patch.object(animation, 'prepare_first_party_godot_animation') as host:
            for changed in (
                valid | {'private_local_execution_confirmed': False},
                valid | {'private_local_execution_confirmed': 1},
                valid | {'schema_version': True},
                valid | {'engine_project_exported': True},
                {key: value for key, value in valid.items() if key != 'private_local_execution_confirmed'},
            ):
                with self.subTest(changed=changed.keys()):
                    code, output, error = self.run_cli(changed)
                    self.assertEqual(code, 2)
                    self.assertEqual(output, '')
                    self.assertIn('private Godot authorization', error)
            host.assert_not_called()

    def test_cli_dispatches_typed_authorization_and_scopes_success_to_preparation(self):
        diagnostic = VerifiedRegisteredNativeBodyDiagnostic(self.fixture.fresh, str(UUID(int=7700)), 'f'*64)
        with patch.object(
            animation, 'prepare_first_party_godot_animation',
            return_value=SimpleNamespace(retained=self.retained, diagnostic=diagnostic),
        ) as host:
            code, output, error = self.run_cli(self.authorization())

        self.assertEqual((code, error), (0, ''))
        host.assert_called_once()
        self.assertEqual(host.call_args.args[0].root, self.fixture.store.root)
        inputs = host.call_args.kwargs
        self.assertEqual(inputs['selection'], self.fixture.selection)
        self.assertEqual(inputs['permissions'], self.fixture.permissions)
        self.assertIs(inputs['private_local_execution_confirmed'], True)
        self.assertEqual(inputs['godot_exe'], self.godot)
        self.assertEqual(inputs['godot_main_exe'], self.godot_main)
        self.assertGreater(inputs['timeout_s'], 0)
        self.assertLessEqual(inputs['timeout_s'], 90.0)
        reported = json.loads(output)
        self.assertEqual(reported['status'], 'PRIVATE_GODOT_ANIMATION_GEOMETRY_VERIFIED')
        self.assertEqual(reported['diagnostic_receipt_sha256'], diagnostic.receipt_sha256)
        self.assertIs(reported['engine_project_exported'], False)

    def test_cli_export_has_no_implicit_private_execution_or_publication_consent(self):
        from ucc.jobs import godot_first_party_playback as playback

        destination = self.root/'UNCREATED_EXPORT'
        denied = self.authorization() | {'private_local_execution_confirmed': False}
        with (patch.object(animation, 'prepare_first_party_godot_animation') as prepare,
              patch.object(playback, 'publish_first_party_godot_playback') as publish):
            code, output, error = self.run_cli(
                denied, command='export-godot-animation', destination=destination,
            )
        self.assertEqual(code, 2)
        self.assertEqual(output, '')
        self.assertIn('private Godot authorization', error)
        prepare.assert_not_called()
        publish.assert_not_called()
        self.assertFalse(destination.exists())

    def test_cli_export_passes_same_exact_inputs_through_prepare_and_publication(self):
        from ucc.jobs import godot_first_party_playback as playback

        destination = self.root/'UNCREATED_EXPORT'
        prepared = object()
        published = playback.PublishedFirstPartyGodotPlayback(destination, 'c'*64)
        with (patch.object(animation, 'prepare_first_party_godot_animation', return_value=prepared) as prepare,
              patch.object(playback, 'publish_first_party_godot_playback', return_value=published) as publish):
            code, output, error = self.run_cli(
                self.authorization(), command='export-godot-animation', destination=destination,
            )
        self.assertEqual((code, error), (0, ''))
        prepare.assert_called_once()
        publish.assert_called_once()
        earlier, later = prepare.call_args.kwargs, publish.call_args.kwargs
        for name in ('selection', 'permissions', 'database_path', 'godot_exe', 'godot_main_exe'):
            self.assertIs(earlier[name], later[name])
        self.assertIs(later['result'], prepared)
        self.assertEqual(later['destination'].path, destination)
        self.assertGreater(later['timeout_s'], 0)
        self.assertLessEqual(later['timeout_s'], earlier['timeout_s'])
        report = json.loads(output)
        self.assertEqual(report['status'], 'PRIVATE_GODOT_ANIMATION_EXPORTED_AND_REOPENED')
        self.assertEqual(report['directory'], str(destination))
        self.assertEqual(report['receipt_sha256'], published.receipt_sha256)
        self.assertIs(report['engine_project_exported'], True)
        self.assertIs(report['distribution_review_complete'], False)
