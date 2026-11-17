"""Closed V2 source recipe for an explicitly selected registered target Action.

Metadata alone never admits saved proofs, runtime code provenance or engine
execution. The host must load the current binding and retain all source guards.
"""
import re

from ucc.core.errors import ValidationError
from ucc.core.models import CharacterProject
from ucc.core.target_action import TargetActionBinding
from ucc.core.target_action_format import canonical_bytes as binding_bytes
from ucc.core.expression_library import canonical_digest
from .godot_candidate_contract import EngineInputPermission, canonical_bytes, _hash
from .godot_runtime_contract import CODE_FILES, CAPABILITY
from .godot_native_recipe import INPUTS
from .godot_registered_binding import project_registered_native_proofs

POLICY = "MPFB_REGISTERED_TARGET_RUNTIME_SOURCE_V2"
MATERIAL_POLICY = "PRESERVE_UNASSIGNED_HUMAN_MATERIAL_SLOTS_V1"
OPERATIONS = frozenset({"stage_registered_native_godot_runtime",
                        "verify_registered_native_godot_runtime"})
MAX_BYTES = 256 * 1024
MAX_CODE_BYTES = 256 * 1024


def build_registered_native_recipe(project: CharacterProject, project_file_sha256: str,
        source_bindings: dict[str, str], evidence_bindings: dict[str, str],
        implementation: dict[str, str], permissions: tuple[EngineInputPermission, ...],
        motion_asset_id: str, capability: str, *, target_action_binding: TargetActionBinding,
        target_action_binding_sha256: str, runtime_code_lengths: dict[str, int],
        runtime_code_provenance_sha256: str, material_policy: str = MATERIAL_POLICY) -> dict:
    if (type(project) is not CharacterProject or not _hash(project_file_sha256)
            or project.family != "humanoid.v1" or project.base_provider != "mpfb" or project.expression is None
            or any(not part.visible for part in project.parts) or capability != CAPABILITY
            or type(material_policy) is not str or material_policy != MATERIAL_POLICY
            or project.appearance):
        raise ValidationError("Registered native source needs the explicit prepared unassigned-material profile")
    if type(target_action_binding) is not TargetActionBinding:
        raise ValidationError("Registered native source needs typed selected target metadata")
    binding = TargetActionBinding.from_bytes(binding_bytes(target_action_binding.to_dict()))
    projection = project_registered_native_proofs(binding,
        selected_binding_sha256=target_action_binding_sha256, project=project,
        project_sha256=project_file_sha256, current_source=binding.source)
    if type(motion_asset_id) is not str or not motion_asset_id.startswith("motion:") or len(motion_asset_id) > 160:
        raise ValidationError("Registered native source needs an explicit original motion role")
    if len(project.parts) > 1:
        raise ValidationError("Registered native profile supports one compatible left hand")
    part_hashes = {}
    for part in project.parts:
        match = re.fullmatch(r"ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)", part.part_asset_id)
        if match is None or part.slot != "hand.L":
            raise ValidationError("Registered native profile requires the registered compatible left-hand identity")
        part_hashes["part:" + part.part_asset_id] = match[1]
    expected_sources = {"master", "expression_library", motion_asset_id} | {
        "part:" + part.part_asset_id for part in project.parts}
    if (type(source_bindings) is not dict or set(source_bindings) != expected_sources
            or any(not _hash(value) for value in source_bindings.values())
            or source_bindings["master"] != binding.target.master_sha256
            or source_bindings[motion_asset_id] != binding.source.source_sha256
            or source_bindings["expression_library"] != project.expression.library_sha256
            or any(source_bindings[name] != digest for name, digest in part_hashes.items())):
        raise ValidationError("Registered native source roles differ from selected project/source content")
    expected_evidence = {"native_review": projection.native_review.sha256,
        "native_timeline": projection.native_timeline.sha256,
        "source_snapshot": projection.source_snapshot.sha256,
        "native_mapping": projection.native_mapping.sha256}
    if (type(evidence_bindings) is not dict or evidence_bindings != expected_evidence
            or any(not _hash(value) for value in evidence_bindings.values())
            or binding.mapping_sha256 != expected_evidence["native_mapping"]
            or binding.source.snapshot_sha256 != expected_evidence["source_snapshot"]):
        raise ValidationError("Registered native evidence differs from the fixed selected proof roles")
    if (type(implementation) is not dict or set(implementation) != CODE_FILES
            or any(not _hash(value) for value in implementation.values())
            or type(runtime_code_lengths) is not dict or set(runtime_code_lengths) != CODE_FILES
            or any(type(size) is not int or not 0 < size <= MAX_CODE_BYTES
                   for size in runtime_code_lengths.values())
            or not _hash(runtime_code_provenance_sha256)):
        raise ValidationError("Registered native source needs exact private code SHA/length/provenance identities")
    if (type(permissions) is not tuple or len(permissions) != len(expected_sources)
            or any(type(permission) is not EngineInputPermission for permission in permissions)
            or {permission.asset_id for permission in permissions} != expected_sources):
        raise ValidationError("Every registered native original source needs separate explicit engine permission")
    for permission in permissions:
        if permission.source_sha256 != source_bindings[permission.asset_id]:
            raise ValidationError("Registered native permission identifies different source content")
        permission.require_godot()
        if (permission.policy.ai_input_allowed or permission.policy.redistribute_source_allowed
                or permission.asset_id not in {"master", motion_asset_id} and not permission.policy.no_ai):
            raise ValidationError("Private registered native recipe retains source privacy and library NoAI")
    result = {"schema_version": 2, "policy": POLICY,
        "project_snapshot": project.to_dict(),
        "project_snapshot_sha256": canonical_digest(project.to_dict()),
        "project_file_sha256": project_file_sha256,
        "source_bindings": dict(source_bindings), "evidence_bindings": dict(evidence_bindings),
        "implementation": dict(implementation), "permissions": [p.to_dict() for p in permissions],
        "motion_asset_id": motion_asset_id, "requested_capability": capability,
        "timeline": {"first_frame": 1, "last_frame": 300, "fps": 30},
        "source_role": "CURRENT_REGISTERED_TARGET_ACTION_AND_AUTHORITATIVE_MASTER_V2",
        "target_action_binding_sha256": target_action_binding_sha256,
        "target_action_binding": binding.to_dict(), "runtime_code_lengths": dict(runtime_code_lengths),
        "runtime_code_provenance_sha256": runtime_code_provenance_sha256,
        "material_policy": material_policy,
        "runtime_code_provenance_verified": False, "private_runtime_delivery_authorized": False,
        "engine_import_verified": False, "runtime_execution_verified": False,
        "visual_quality_approved": False, "distribution_license_review_complete": False,
        "source_redistribution_authorized": False, "cloud_transmission_authorized": False}
    if len(canonical_bytes(result)) > MAX_BYTES:
        raise ValidationError("Registered native recipe exceeds its metadata bound")
    return result


def validate_registered_native_recipe(raw: object) -> dict:
    if type(raw) is not dict:
        raise ValidationError("Registered native recipe must be a closed object")
    try:
        if type(raw["permissions"]) is not list:
            raise ValidationError("Registered native permissions must be a list")
        expected = build_registered_native_recipe(
            CharacterProject.from_dict(raw["project_snapshot"]), raw["project_file_sha256"],
            raw["source_bindings"], raw["evidence_bindings"], raw["implementation"],
            tuple(EngineInputPermission.from_dict(item) for item in raw["permissions"]),
            raw["motion_asset_id"], raw["requested_capability"],
            target_action_binding=TargetActionBinding.from_dict(raw["target_action_binding"]),
            target_action_binding_sha256=raw["target_action_binding_sha256"],
            runtime_code_lengths=raw["runtime_code_lengths"],
            runtime_code_provenance_sha256=raw["runtime_code_provenance_sha256"],
            material_policy=raw["material_policy"])
    except (KeyError, TypeError, AttributeError) as error:
        raise ValidationError("Malformed registered native recipe") from error
    if canonical_bytes(raw) != canonical_bytes(expected):
        raise ValidationError("Registered native recipe changed its closed profile or readiness")
    return expected


def validate_registered_native_job(operation: str, input_project: object, options: object) -> None:
    fields = set(INPUTS.values()) | {"native_recipe_sha256", "target_action_binding_sha256"}
    if operation == "verify_registered_native_godot_runtime":
        fields.add("native_stage_sha256")
    if (type(operation) is not str or operation not in OPERATIONS or input_project != "candidate.blend"
            or type(options) is not dict or set(options) != fields
            or any(not _hash(value) for value in options.values())):
        raise ValidationError("Registered native worker needs fixed files and exact V2 source/binding hashes")
