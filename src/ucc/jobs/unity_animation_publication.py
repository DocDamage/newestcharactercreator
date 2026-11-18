"""Atomically publish only the independently tested Unity scene inputs."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, UCCError, ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.storage import ProjectStore
from .export_destination import ExportDestination, plan_destination, rename_new
from .godot_candidate_inputs import identity
from .godot_registered_runtime_files import copy_file, hash_file, read_metadata
from .target_action_context import operation_budget, protected
from .unity_animation_engine import MAX_OUTPUT, UNITY_VERSION, _record, _write
from .unity_animation_payload import PORTABLE_FILES, VERIFIER_FILES, verify_unity_animation_payload
from .unity_corrected_animation_verification import VerifiedUnityCorrectedAnimation
from .unity_engine import tree_hashes


VERIFICATION = 'unity-animation-correction-verified.json'
RECEIPT = 'unity-animation-export-receipt.json'
README = (
    'Private Unity character animation\n\n'
    'Open this project with Unity '+UNITY_VERSION+' using Direct3D 11.\n'
    'Open Assets/UCC/AnimatedCharacter.unity, then press Play.\n'
    'The scene uses a Generic Animator and a neutral preview material.\n'
    'Runtime requirements are Built-in Forward, Linear color and Unlimited skin weights.\n'
    'Retain the source quad mapping, correction data and saved shader references.\n'
    'Use the generated character privately under the permissions you selected in UCC.\n'
).encode('utf-8')


@dataclass(frozen=True, slots=True)
class PublishedUnityAnimation:
    directory: Path
    receipt_sha256: str


def publish_unity_animation(store: ProjectStore, verified: VerifiedUnityCorrectedAnimation, *,
        database_path: Path, destination: ExportDestination, guard: Callable[[], None],
        cancel: Event | None = None, timeout_s: float = 120) -> PublishedUnityAnimation:
    if (type(store) is not ProjectStore or type(verified) is not VerifiedUnityCorrectedAnimation
            or type(destination) is not ExportDestination or destination.path.is_relative_to(store.root)
            or destination.path.is_relative_to(Path(database_path).parent)
            or plan_destination(destination.path, store.root) != destination):
        raise ValidationError('Choose a new Unity destination outside the saved project and catalog')
    with operation_budget(cancel, timeout_s) as budget:
        guard()
        receipt_path = verified.directory.parent/VERIFICATION
        proof, _, proof_sha = read_metadata(receipt_path, 512 * 1024, budget,
                                            expected_sha256=verified.receipt_sha256)
        files, saved = proof.get('portable_files'), proof.get('saved_files')
        if (proof.get('policy') != 'UCC_UNITY_ANIMATED_CORRECTION_ADMISSION_V1'
                or any(proof.get(flag) is not True for flag in ('corrective_runtime_verified',
                                                               'normal_loop_wrap_verified', 'lit_motion_verified'))
                or type(files) is not dict or set(files) != PORTABLE_FILES
                or type(saved) is not dict or set(saved) != PORTABLE_FILES | VERIFIER_FILES
                or any(not is_sha256(digest) or saved[name] != digest for name, digest in files.items())):
            raise ValidationError('The private Unity result is missing the exact corrected playback receipt')

        def unchanged() -> None:
            guard()
            if (hash_file(receipt_path, 512 * 1024, budget)[0] != proof_sha
                    or tree_hashes(verified.directory, budget.cancel) != saved):
                raise ProjectStorageError('Verified Unity inputs changed before private publication')

        unchanged()
        stage = destination.stage(str(uuid4()))
        stamp = identity(stage)
        for relative, digest in files.items():
            source = verified.directory/relative
            row = _record(source, MAX_OUTPUT, budget)
            if row.sha256 != digest:
                raise ProjectStorageError('A verified Unity scene input changed during publication')
            target = stage/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_file(source, target, row, budget)
        with (stage/'README.txt').open('xb') as stream:
            stream.write(README)
        _write(stage/RECEIPT, dict(schema_version=1, policy='UCC_PRIVATE_UNITY_ANIMATION_EXPORT_V1',
            unity_version=UNITY_VERSION, verification_sha256=proof_sha, files=files,
            private_local_only=True, corrective_runtime_verified=True, native_loop_verified=True,
            material_appearance_approved=False, distribution_review_complete=False))
        receipt_sha, _ = hash_file(stage/RECEIPT, 512 * 1024, budget)
        expected = files | {'README.txt': sha256(README).hexdigest(), RECEIPT: receipt_sha}
        unchanged()
        if identity(protected(stage)) != stamp:
            raise ProjectStorageError('Unity publication staging folder was changed')
        verify_unity_animation_payload(stage, expected, budget)
        destination.unchanged()
        budget.check()
        rename_new(stage, destination.path)
        try:
            unchanged()
            if identity(protected(destination.path)) != stamp:
                raise ProjectStorageError('Published Unity folder was changed during verification')
            verify_unity_animation_payload(destination.path, expected, budget)
        except BaseException as error:
            try:
                with operation_budget(None, 10) as rollback_budget:
                    if (identity(protected(destination.path.parent)) == destination.parent_identity
                            and identity(protected(destination.path)) == stamp):
                        verify_unity_animation_payload(destination.path, expected, rollback_budget)
                        rename_new(destination.path, stage)
            except (UCCError, OSError) as rollback_error:
                error.add_note('Unity export rollback preserved the destination: '+str(rollback_error))
            raise
        return PublishedUnityAnimation(destination.path, receipt_sha)
