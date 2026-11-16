"""Genuine hand-library reconstruction over a newly prepared neutral original."""
from dataclasses import dataclass, replace
from pathlib import Path
import re
from threading import Event
from uuid import uuid4

from ucc.core.errors import CompatibilityError
from ucc.core.models import CharacterProject, PartInstance
from ucc.core.storage import ProjectStore
from .expression_keys import PreparedExpressionKeys
from .expression_storage import check_cancel, install_master_copy, safe_directory
from .geometry_evidence import EvidenceError
from .hand_library import build_hand_library
from .hand_revision import apply_hand_revision
from .hand_storage import (HandLibrary, load_hand_library, load_hand_receipt, publish_asset,
                           publish_manifest, publish_hand_receipt)
from .master_preview import _master_file


@dataclass(frozen=True, slots=True)
class ExistingExpressionHand:
    library: HandLibrary
    selection: str
    observed: dict


def verify_existing_hand(store: ProjectStore, initial: CharacterProject, *, blender_exe: Path,
                         worker_script: Path, mpfb_data_dir: Path, cancel: Event | None,
                         timeout_s: float) -> ExistingExpressionHand | None:
    if not initial.parts:
        return None
    if len(initial.parts) != 1:
        raise CompatibilityError('Expression preparation requires one registered compatible left hand')
    part = initial.parts[0]
    match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', part.part_asset_id)
    if match is None or part.slot != 'hand.L' or part.visible is not True or part.status != 'proposed':
        raise CompatibilityError('Expression preparation requires a visible registered compatible left hand')
    library = load_hand_library(store, match[1], cancel)
    # Same-selection is a real two-worker no-op. It reconstructs current skin
    # from the original/assets/receipt rather than trusting a rehashed master.
    result = apply_hand_revision(store, manifest_sha256=library.sha256, selection=match[2],
        blender_exe=blender_exe, worker_script=worker_script, mpfb_data_dir=mpfb_data_dir,
        expected_project_id=initial.project_id, expected_revision=initial.revision,
        expected_master_blend=initial.master_blend, cancel=cancel, timeout_s=timeout_s)
    if result.revision is not None or result.project != initial:
        raise EvidenceError('Existing hand verification unexpectedly changed the saved project')
    return ExistingExpressionHand(library, match[2], result.observed)


@dataclass(frozen=True, slots=True)
class RebuiltExpressionHand:
    scratch: ProjectStore
    library: HandLibrary
    scene: Path
    sha256: str
    receipt: dict
    parts: tuple[PartInstance, ...]
    observed: dict


def rebuild_expression_hand(store: ProjectStore, initial: CharacterProject, keys: PreparedExpressionKeys,
                            previous: ExistingExpressionHand, *, blender_exe: Path, worker_script: Path,
                            mpfb_data_dir: Path, cancel: Event | None, timeout_s: float) -> RebuiltExpressionHand:
    check_cancel(cancel)
    root = safe_directory(store, '.ucc-jobs', create=True)/('expression-hand-'+str(uuid4()))
    root.mkdir(exist_ok=False); scratch = ProjectStore(root)
    install_master_copy(scratch, keys.scene, keys.sha256, keys.scene.parent, cancel)
    prepared = scratch.save(replace(initial, revision=0, parts=(), rig_profile=None,
        geometry_state='generated_unverified', master_blend='master/versions/'+keys.sha256+'.blend'))
    common = dict(blender_exe=blender_exe, worker_script=worker_script, mpfb_data_dir=mpfb_data_dir,
                  cancel=cancel, timeout_s=timeout_s)
    built = build_hand_library(scratch, **common, expected_project_id=prepared.project_id,
        expected_revision=prepared.revision, expected_master_blend=prepared.master_blend)
    revised = apply_hand_revision(scratch, **common, manifest_sha256=built.library.sha256,
        selection=previous.selection, expected_project_id=prepared.project_id,
        expected_revision=prepared.revision, expected_master_blend=prepared.master_blend)
    if revised.revision is None or built.library.sha256 == previous.library.sha256:
        raise EvidenceError('Expression hand preparation did not actually rebuild and apply a new compatible library')
    scene, sha = _master_file(scratch, revised.project.master_blend)
    receipt = load_hand_receipt(scratch, built.library, sha, previous.selection, cancel)
    parts = (replace(revised.project.parts[0], part_id=initial.parts[0].part_id),)
    observed = {'previous_hand_verified': previous.observed, 'rebuilt_library': built.observed,
                'reapplied_selection': revised.observed, 'selection': previous.selection,
                'new_manifest_sha256': built.library.sha256}
    return RebuiltExpressionHand(scratch, built.library, scene, sha, receipt, parts, observed)


def publish_rebuilt_hand(store: ProjectStore, rebuilt: RebuiltExpressionHand,
                          cancel: Event | None) -> None:
    """Register genuinely rebuilt immutable objects; never alter receipt bindings."""
    library = rebuilt.library
    for variant, path in library.assets.items():
        publish_asset(store, path, library.manifest['assets'][variant]['sha256'], path.parent, cancel)
    if publish_manifest(store, library.manifest, cancel) != library.sha256:
        raise EvidenceError('Published compatible hand library differs from independently verified reconstruction')
    publish_hand_receipt(store, rebuilt.receipt, cancel)
    installed = load_hand_library(store, library.sha256, cancel)
    load_hand_receipt(store, installed, rebuilt.sha256, rebuilt.receipt['selection'], cancel)
