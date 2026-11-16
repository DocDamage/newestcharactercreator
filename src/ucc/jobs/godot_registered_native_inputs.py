"""Guarded current registered-target inputs for V2 native source preparation.

This reads an explicitly selected private code directory/provenance record. It
never executes that code or grants private delivery, engine or distribution rights.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.facial import validate_face_parameters
from ucc.core.hand_parts import hand_selection, validate_hand_library_recipe
from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_native_recipe import build_registered_native_recipe
from ucc.export.godot_runtime_contract import CODE_FILES
from .expression_storage import load_expression_library
from .expression_revisions import admit_expression_source
from .hand_storage import load_hand_library, load_hand_receipt
from .master_preview import _master_file, _digest
from .godot_candidate_inputs import regular_file, read_json, identity, check_cancel
from .target_action_context import source_review, require_review, protected, check_target_action_catalog
from .target_action_storage import load_target_action, read_target_action_binding, source_state, ancestry
from .target_action_resources import (host_code_snapshot, worker_namespace_snapshot,
    blender_helper_resources, blender_helper_inventory)
from .worker_resources import worker_dependency_files
from .export_guards import bounded_paths


@dataclass(frozen=True, slots=True)
class _AdmissionBudget:
    cancel: object
    check: Callable
    remaining: Callable


def _registered_sources(store, project, cancel) -> dict[str, Path]:
    """Read prepared source provenance without the V1 unanimated-intent guard."""
    if project.expression is None or project.master_blend is None:
        raise ValidationError("Registered native source needs a prepared expression master")
    master, master_sha = _master_file(store, project.master_blend)
    if _digest(master, cancel) != master_sha:
        raise ProjectStorageError("Registered native immutable source master changed")
    library = load_expression_library(store, project.expression.library_sha256, cancel)
    sources = {"master": master, "expression_library": library.manifest_path}
    if not project.parts:
        admit_expression_source(store, library, master_sha, cancel)
        return sources
    if len(project.parts) != 1:
        raise ValidationError("Registered native source supports one compatible left-hand part")
    part = project.parts[0]
    match = re.fullmatch(r"ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)", part.part_asset_id)
    if match is None or not part.visible:
        raise ValidationError("Registered native source has an unsupported part")
    hand = load_hand_library(store, match[1], cancel)
    recipe = validate_hand_library_recipe(hand.manifest["recipe"])
    # Compare the exact existing hand intent fields directly. Calling the V1
    # source_intent helper would reject attached references; stripping those
    # references would lose the authoritative project context.
    intent = {"project_id": project.project_id, "body_parameters": dict(project.parameters),
        "facial_parameters": validate_face_parameters(dict(project.facial_parameters)),
        "height_m": project.height_m}
    if canonical_digest(intent) != canonical_digest(recipe["source"]):
        raise ProjectConflict("Registered native hand body/face intent differs from its saved recipe")
    selection = hand_selection(project, hand.sha256)
    load_hand_receipt(store, hand, master_sha, selection, cancel)
    admit_expression_source(store, library, recipe["bindings"]["master_sha256"], cancel)
    sources["part:" + part.part_asset_id] = hand.manifest_path
    return sources


def _private_code(directory, cancel, check):
    directory = protected(Path(directory))
    if not directory.is_dir():
        raise ProjectStorageError("Select the existing canonical private runtime code directory")
    files = {}
    for path in bounded_paths(directory, cancel, maximum_entries=16, allowed_directories=frozenset()):
        check()
        if path == directory:
            continue
        if not path.is_file() or path.name not in CODE_FILES or path.parent != directory:
            raise ValidationError("Private runtime directory must contain exactly the seven selected code files")
        files[path.name] = regular_file(path, directory, 256 * 1024)
    if set(files) != CODE_FILES:
        raise ValidationError("Private runtime directory lacks the exact seven code files")
    return files


def admit_registered_native_production(store, runner, *, binding_sha256, database_path,
        expected_project_id, expected_revision, expected_master_blend, expected_project_sha256,
        expected_clip_id, expected_source_binding_sha256, expected_catalog_record_sha256,
        runtime_directory, runtime_code_provenance: Path, motion_asset_id, permissions,
        capability, cancel, check, remaining, progress=None) -> dict:
    if not callable(check) or not callable(remaining):
        raise ValidationError("Registered native admission requires inherited cancellation/deadline guards")
    def bounded_check():
        check_cancel(cancel)
        check()
    budget = _AdmissionBudget(cancel, bounded_check, remaining)
    bounded_check()
    store._check_safety()
    if Path(runner.jobs_root) != store.root / ".ucc-jobs":
        raise ValidationError("Registered native runner must use the selected project job directory")
    database = protected(Path(database_path))
    args = dict(database_path=database, expected_project_id=expected_project_id,
        expected_revision=expected_revision, expected_master_blend=expected_master_blend,
        expected_project_sha256=expected_project_sha256, expected_clip_id=expected_clip_id,
        expected_source_binding_sha256=expected_source_binding_sha256,
        expected_catalog_record_sha256=expected_catalog_record_sha256)
    # Real saved-loader proof admission is mandatory: no caller-constructed DTO.
    loader_progress = None if progress is None else lambda phase: progress('LOAD_TARGET_ACTION_'+str(phase))
    try:
        prepared = load_target_action(store, binding_sha256=binding_sha256,
            **args, cancel=cancel, timeout_s=min(300, remaining()), progress=loader_progress)
    except OSError as error:
        raise ProjectStorageError("Selected registered target is missing or unreadable") from error
    bounded_check()
    binding = read_target_action_binding(store, binding_sha256, cancel=cancel)
    project = store.load()
    review = source_review(store, database, expected_clip_id, expected_project_id,
        expected_revision, expected_master_blend, expected_project_sha256, budget)
    require_review(review, expected_source_binding_sha256, expected_catalog_record_sha256)
    if (prepared.binding_sha256 != binding_sha256 or binding.sha256 != binding_sha256
            or binding.source != review.source or prepared.project_id != project.project_id
            or prepared.project_sha256 != expected_project_sha256
            or prepared.revision != project.revision or prepared.master_sha256 != review.master_sha256
            or prepared.clip_id != expected_clip_id or prepared.source_sha256 != review.source.source_sha256
            or prepared.directory != store.root / "animations/actions" / binding_sha256
            or prepared.binding_path != prepared.directory / "binding.json"):
        raise ProjectConflict("Loaded registered target differs from current selected source context")
    sources = _registered_sources(store, project, cancel)
    if type(motion_asset_id) is not str or not motion_asset_id.startswith("motion:") or motion_asset_id in sources:
        raise ValidationError("Registered native source needs one explicit original motion permission role")
    sources[motion_asset_id] = review.source_path
    evidence = {"native_review": prepared.directory / "body_first/review_motion.blend",
        "native_timeline": prepared.directory / "body_first/target_timeline.json",
        "source_snapshot": prepared.directory / "source_snapshot.json",
        "native_mapping": prepared.directory / "native_mapping.json"}
    implementation = _private_code(runtime_directory, cancel, bounded_check)
    provenance = protected(Path(runtime_code_provenance))
    regular_file(provenance, provenance.parent, 256 * 1024)
    provenance_identity = identity(provenance)
    # Bounded metadata identity only, never code-provenance or licensing admission.
    # Parse and hash the SAME captured bytes: separate path reads allow ABA
    # replacements to bind a digest of content that was never parsed.
    with provenance.open("rb") as stream:
        provenance_raw = stream.read(256 * 1024 + 1)
    if not 2 <= len(provenance_raw) <= 256 * 1024:
        raise ValidationError("Selected runtime provenance exceeds its metadata size bounds")
    try:
        provenance_value = json.loads(provenance_raw.decode("utf-8"),
            object_pairs_hook=_unique_project_fields, parse_constant=_nonfinite_project_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("Malformed selected runtime provenance JSON") from error
    if type(provenance_value) is not dict:
        raise ValidationError("Selected runtime provenance must be a JSON object")
    canonical_bytes(provenance_value)
    provenance_sha = sha256(provenance_raw).hexdigest()
    if identity(provenance) != provenance_identity or _digest(provenance, cancel) != provenance_sha:
        raise ProjectStorageError("Selected runtime provenance changed during metadata admission")
    bindings = {name: _digest(protected(path), cancel) for name, path in sources.items()}
    evidence_bindings = {name: _digest(protected(path), cancel) for name, path in evidence.items()}
    code_hashes = {name: _digest(path, cancel) for name, path in implementation.items()}
    code_lengths = {name: path.stat().st_size for name, path in implementation.items()}
    def recipe_for(current):
        return build_registered_native_recipe(current, expected_project_sha256, bindings,
            evidence_bindings, code_hashes, permissions, motion_asset_id, capability,
            target_action_binding=binding, target_action_binding_sha256=binding_sha256,
            runtime_code_lengths=code_lengths, runtime_code_provenance_sha256=provenance_sha)
    recipe = recipe_for(project)
    def preserve_motion_policy(current_review):
        matches = [p for p in permissions if p.asset_id == motion_asset_id]
        if len(matches) != 1:
            raise ValidationError("Registered native motion needs exactly one explicit permission")
        permission = matches[0]
        if (current_review.policy.ue_only
                or current_review.policy.no_ai and (not permission.policy.no_ai
                                                    or permission.policy.ai_input_allowed)):
            raise ValidationError("Registered native motion cannot override original UE-only or NoAI restrictions")
    preserve_motion_policy(review)
    worker = protected(Path(runner.worker_script))
    blender = protected(Path(runner.blender_exe))
    regular_file(worker, worker.parent, 2 * 1024 * 1024)
    regular_file(blender, blender.parent, 512 * 1024 * 1024)
    resources = worker_dependency_files(worker) | {worker}
    helpers = blender_helper_resources(blender, budget)
    helper_state = blender_helper_inventory(blender, budget)
    host_state = host_code_snapshot(budget)
    worker_state = worker_namespace_snapshot(worker, budget)
    # The loader seals all actual proofs. Retain those watches, source storage,
    # exact dependencies, code files/provenance and canonical ancestor identities.
    expected = dict(prepared.watched_inputs)
    for paths, values in ((sources, bindings), (evidence, evidence_bindings),
                          (implementation, code_hashes)):
        for name, path in paths.items():
            if path in expected and expected[path] != values[name]:
                raise ProjectStorageError("Registered native initial source/proof identities disagree")
            expected[path] = values[name]
    expected[provenance] = provenance_sha
    for path in {*sources.values(), *evidence.values(), *implementation.values(), provenance,
                 *resources, blender, *helpers.values(), store.file}:
        protected(path)
        digest = _digest(path, cancel)
        if path in expected and expected[path] != digest:
            raise ProjectStorageError("Loaded target input changed before registered native admission")
        expected[path] = digest
    authorities = ancestry((*expected, Path(runtime_directory), database))
    if authorities[provenance] != provenance_identity:
        raise ProjectStorageError("Selected runtime provenance identity changed before admission")
    authorities.update(dict(prepared.watched_identities))
    authorities[database] = (*identity(database)[:2], 0, 0)
    baseline = source_state(store, budget)
    def unchanged() -> None:
        bounded_check()
        if host_code_snapshot(budget) != host_state:
            raise ProjectStorageError("Registered native host code/executable closure changed")
        if (worker_namespace_snapshot(worker, budget) != worker_state
                or worker_dependency_files(worker) | {worker} != resources):
            raise ProjectStorageError("Registered native worker namespace changed")
        if (blender_helper_resources(blender, budget) != helpers
                or blender_helper_inventory(blender, budget) != helper_state):
            raise ProjectStorageError("Registered native Blender helper closure changed")
        current_review = source_review(store, database, expected_clip_id, expected_project_id,
            expected_revision, expected_master_blend, expected_project_sha256, budget)
        preserve_motion_policy(current_review)
        if current_review != review or source_state(store, budget) != baseline:
            raise ProjectConflict("Registered native source/project/proof closure changed")
        check_target_action_catalog(database, binding.source,
            expected_database_identity=authorities[database][:2],
            expected_parent_identity=authorities[database.parent][:2])
        if _private_code(runtime_directory, cancel, bounded_check) != implementation:
            raise ProjectStorageError("Private runtime code selection changed")
        for path, stamp in authorities.items():
            now = identity(protected(path))
            if (now[:2] != stamp[:2] if path == database else now != stamp):
                raise ProjectStorageError("Registered native source/code/tool ancestry changed")
        for path, digest in expected.items():
            protected(path)
            if _digest(path, cancel) != digest:
                raise ProjectStorageError("Registered native source/code/provenance input changed")
        current = store.load()
        if current != project or _registered_sources(store, current, cancel) != {
                name:path for name,path in sources.items() if name != motion_asset_id}:
            raise ProjectConflict("Registered native prepared source registration changed")
        for name, path in sources.items():
            if name not in {"master", motion_asset_id}:
                rights = read_json(path, 4 * 1024 * 1024).get("rights", {})
                permission = next(p for p in permissions if p.asset_id == name)
                if rights.get("no_ai") and (not permission.policy.no_ai or permission.policy.ai_input_allowed):
                    raise ValidationError("Registered native source cannot remove registered NoAI")
        recipe_for(current)
    unchanged()
    return {"project": project, "project_sha": expected_project_sha256, "sources": sources,
        "evidence": evidence, "bindings": bindings, "evidence_bindings": evidence_bindings,
        "implementation": implementation, "recipe": recipe, "unchanged": unchanged,
        "source": review.source_path, "binding": binding, "prepared_target": prepared}
