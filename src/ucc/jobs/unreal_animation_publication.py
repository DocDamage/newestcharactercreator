"""Atomically publish the exact editor-playable Unreal project."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, UCCError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import checked_sha
from ucc.core.worker_payload import UNREAL_REGISTERED_PREVIEW_FILES
from ucc.export.unreal_contract import ENGINE_VERSION
from .export_destination import ExportDestination, plan_destination, rename_new
from .export_guards import bounded_paths
from .godot_candidate_inputs import identity
from .godot_registered_runtime_files import hash_file, read_metadata
from .target_action_context import operation_budget, protected
from .unreal_animation_engine import PROJECT_CONFIG, PROJECT_FILE, RUNTIME_PLUGIN
from .unreal_animation_preview import MAP, NATIVE_ASSETS, PLAYBACK_POLICY, PLAYBACK_RECEIPT, VerifiedUnrealPreview
from .unreal_engine import _copy, _write


RECEIPT = 'unreal-animation-export-receipt.json'
POLICY = 'UCC_PRIVATE_UNREAL_ANIMATION_EXPORT_V1'
README = (
    'Private Unreal character animation\n\n'
    'Open AnimatedCharacter.uproject in Unreal Engine 5.9.0 build 60351404 on Windows.\n'
    'Open the CharacterScene level in Content/UccAnimation and press Play.\n'
    'The scene uses the saved native animation and a live corrected preview mesh.\n'
    'Keep the included UccRegisteredPreview plugin and engine version together.\n'
    'Use the generated character privately under the source permissions selected in UCC.\n'
).encode('utf-8')
PORTABLE_FILES = frozenset({PROJECT_FILE, PROJECT_CONFIG, *('Content/'+name for name in NATIVE_ASSETS | {MAP}),
    *(f'Plugins/{RUNTIME_PLUGIN}/{name}' for name in UNREAL_REGISTERED_PREVIEW_FILES),
    *(f'Plugins/{RUNTIME_PLUGIN}/Binaries/Win64/{name}'
      for name in ('UnrealEditor.modules', f'UnrealEditor-{RUNTIME_PLUGIN}.dll'))})
_DELIVERY = PORTABLE_FILES | {RECEIPT, 'README.txt'}


@dataclass(frozen=True, slots=True)
class PublishedUnrealAnimation:
    directory: Path
    receipt_sha256: str


def verify_unreal_animation_payload(directory: Path, files: dict[str, str], budget) -> None:
    if set(files) not in (PORTABLE_FILES, _DELIVERY):
        raise ValidationError('Unreal animation requires the exact portable scene inventory')
    parents = {parent.as_posix() for name in files for parent in Path(name).parents if parent != Path('.')}
    actual = {}
    for path in bounded_paths(directory, budget.cancel, maximum_entries=128, allowed_directories=frozenset(parents)):
        budget.check()
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            if name not in files:
                raise ProjectStorageError('Unreal animation export contains an unexpected file')
            actual[name] = hash_file(path, 512 * 1024**2, budget)[0]
    if actual != files:
        raise ProjectStorageError('Unreal animation project differs from its sealed files')


def publish_unreal_animation(store: ProjectStore, verified: VerifiedUnrealPreview, *, database_path: Path,
        destination: ExportDestination, guard: Callable[[], None], cancel: Event | None = None,
        timeout_s: float = 120) -> PublishedUnrealAnimation:
    if (type(store) is not ProjectStore or type(verified) is not VerifiedUnrealPreview
            or type(destination) is not ExportDestination or destination.path.is_relative_to(store.root)
            or destination.path.is_relative_to(Path(database_path).parent)
            or plan_destination(destination.path, store.root) != destination):
        raise ValidationError('Choose a new Unreal export destination outside the saved project and catalog')
    with operation_budget(cancel, timeout_s) as budget:
        guard()
        proof_path = verified.directory.parent/PLAYBACK_RECEIPT
        proof, _, proof_sha = read_metadata(proof_path, 512 * 1024, budget,
                                            expected_sha256=verified.receipt_sha256)
        files = proof.get('portable_files')
        if (proof.get('policy') != PLAYBACK_POLICY or proof.get('export_published') is not False
                or any(proof.get(flag) is not True for flag in ('corrected_runtime_verified', 'pie_verified',
                       'normal_loop_wrap_verified', 'lit_motion_verified'))
                or type(files) is not dict or set(files) != PORTABLE_FILES):
            raise ValidationError('Unreal publication requires the exact corrected Play in Editor receipt')
        for digest in files.values():
            checked_sha(digest)

        def unchanged() -> None:
            guard()
            if hash_file(proof_path, 512 * 1024, budget)[0] != proof_sha:
                raise ProjectStorageError('Unreal corrected playback proof changed before publication')
            verify_unreal_animation_payload(verified.directory, files, budget)

        unchanged()
        stage = destination.stage(str(uuid4()))
        owner = identity(stage)
        for name, digest in files.items():
            _copy(verified.directory/name, stage/name, digest, budget.cancel)
        with (stage/'README.txt').open('xb') as stream:
            stream.write(README)
        _write(stage/RECEIPT, dict(schema_version=1, policy=POLICY, unreal_version=ENGINE_VERSION,
            verification_sha256=proof_sha, binding_sha256=checked_sha(proof.get('source_binding_sha256')),
            portable_files=files, private_local_only=True, corrected_runtime_verified=True, pie_verified=True,
            material_appearance_approved=False, distribution_review_complete=False))
        receipt_sha = hash_file(stage/RECEIPT, 512 * 1024, budget)[0]
        expected = files | {'README.txt': sha256(README).hexdigest(), RECEIPT: receipt_sha}
        unchanged()
        verify_unreal_animation_payload(stage, expected, budget)
        if identity(protected(stage)) != owner:
            raise ProjectStorageError('Unreal publication staging folder was replaced')
        destination.unchanged()
        budget.check()
        rename_new(stage, destination.path)
        try:
            unchanged()
            if identity(protected(destination.path)) != owner:
                raise ProjectStorageError('Published Unreal folder changed during verification')
            verify_unreal_animation_payload(destination.path, expected, budget)
        except BaseException as error:
            try:
                with operation_budget(None, 10) as rollback:
                    if (identity(protected(destination.path.parent)) == destination.parent_identity
                            and identity(protected(destination.path)) == owner):
                        verify_unreal_animation_payload(destination.path, expected, rollback)
                        rename_new(destination.path, stage)
            except (UCCError, OSError) as rollback_error:
                error.add_note('Unreal export rollback preserved the destination: ' + str(rollback_error))
            raise
        return PublishedUnrealAnimation(destination.path, receipt_sha)
