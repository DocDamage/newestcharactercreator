"""Private Unity delivery-closure controls without engine assets."""
from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest import TestCase

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.target_action_context import Budget
from ucc.jobs.unity_animation_engine import copy_unity_project_inputs
from ucc.jobs.unity_animation_payload import PORTABLE_FILES, VERIFIER_FILES, _STAGING_FILES, split_animated_unity_inputs
from ucc.jobs.unity_animation_publication import RECEIPT, VERIFICATION, publish_unity_animation
from ucc.jobs.unity_corrected_animation_verification import VerifiedUnityCorrectedAnimation
from ucc.jobs.unity_engine import tree_hashes


class UnityAnimationPayloadTests(TestCase):
    def test_staging_and_verifier_inputs_are_excluded_from_delivery(self):
        before = {name: 'c'*64 for name in PORTABLE_FILES | VERIFIER_FILES | _STAGING_FILES}
        portable, probe = split_animated_unity_inputs(before)
        self.assertEqual(set(portable), PORTABLE_FILES)
        self.assertEqual(set(probe), VERIFIER_FILES)
        self.assertFalse(set(portable) & (set(probe) | _STAGING_FILES))
        with self.assertRaises(ValidationError):
            split_animated_unity_inputs(before | {'Assets/Unknown.asset': 'd'*64})

    def test_fresh_copy_uses_real_budget_and_checks_selected_subset(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root/'native'
            for part in ('Assets', 'Packages', 'ProjectSettings'):
                (source/part).mkdir(parents=True)
                (source/part/'unit-control.txt').write_bytes(b'unit')
            budget = Budget(None, 10)
            measured = tree_hashes(source, budget.cancel)
            with self.assertRaises(ProjectStorageError):
                copy_unity_project_inputs(source, root/'rejected', measured, budget,
                                          selected=measured | {'Assets/unknown.txt': 'd'*64})
            self.assertFalse((root/'rejected').exists())
            copy_unity_project_inputs(source, root/'fresh', measured, budget)
            self.assertEqual(tree_hashes(root/'fresh', budget.cancel), measured)

    def test_private_publication_rechecks_and_omits_verifiers(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root/'work'/'fresh'
            data = b'UNIT_CONTROL'
            digest = sha256(data).hexdigest()
            files = {name: digest for name in PORTABLE_FILES | VERIFIER_FILES}
            for name in files:
                path = source/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            receipt = canonical_bytes(dict(policy='UCC_UNITY_ANIMATED_CORRECTION_ADMISSION_V1',
                portable_files={name: digest for name in PORTABLE_FILES}, saved_files=files,
                corrective_runtime_verified=True, normal_loop_wrap_verified=True, lit_motion_verified=True))
            (source.parent/VERIFICATION).write_bytes(receipt)
            verified = VerifiedUnityCorrectedAnimation(source, sha256(receipt).hexdigest())
            store = ProjectStore(root/'saved-character')
            destination = plan_destination(root/'export', store.root)
            result = publish_unity_animation(store, verified, database_path=root/'catalog/library.sqlite3',
                                             destination=destination, guard=lambda: None)
            self.assertEqual(result.directory, destination.path)
            observed = {path.relative_to(result.directory).as_posix()
                        for path in result.directory.rglob('*') if path.is_file()}
            self.assertEqual(observed, PORTABLE_FILES | {'README.txt', RECEIPT})
