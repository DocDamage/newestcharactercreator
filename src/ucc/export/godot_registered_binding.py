"""Pure fixed-role projection of registered native proof metadata.

Call only after normal load_target_action current-context/proof admission and
read_target_action_binding. This projection reads no files and cannot establish
proof validity, current rights, runtime readiness or permission to export.
"""
from dataclasses import dataclass

from ucc.core.errors import ValidationError
from ucc.core.models import CharacterProject
from ucc.core.target_action import TargetActionBinding, TargetActionFile, TargetActionSource
from ucc.core.target_action_format import canonical_bytes, checked_sha


@dataclass(frozen=True, slots=True)
class NativeProducerProof:
    role: str
    job_id: str
    request: TargetActionFile
    result: TargetActionFile


@dataclass(frozen=True, slots=True)
class RegisteredNativeProofProjection:
    binding_sha256: str
    project_sha256: str
    clip_id: str
    animation_ids: tuple[str, ...]
    producer_proofs: tuple[NativeProducerProof, ...]
    retained_files: tuple[TargetActionFile, ...]
    source_snapshot: TargetActionFile
    native_mapping: TargetActionFile
    native_review: TargetActionFile
    native_timeline: TargetActionFile

    @property
    def engine_use_authorized(self) -> bool:
        return False

    @property
    def retained_content_verified(self) -> bool:
        return False


def project_registered_native_proofs(binding: TargetActionBinding, *,
        selected_binding_sha256: str, project: CharacterProject,
        project_sha256: str, current_source: TargetActionSource) -> RegisteredNativeProofProjection:
    """Project only typed, explicitly selected metadata; preserve every source ID."""
    if (type(binding) is not TargetActionBinding or type(project) is not CharacterProject
            or type(current_source) is not TargetActionSource):
        raise ValidationError("Registered native projection requires typed project, source and binding")
    checked_sha(selected_binding_sha256)
    checked_sha(project_sha256)
    # Re-run the production closed reader: this also checks the complete 45-file
    # inventory, fixed clock/skin policy and nine distinct canonical worker IDs.
    binding = TargetActionBinding.from_bytes(canonical_bytes(binding.to_dict()))
    target = binding.target
    if (binding.sha256 != selected_binding_sha256 or binding.source != current_source
            or target.project_sha256 != project_sha256
            or target.project_id != project.project_id or target.revision != project.revision
            or project.family != target.family
            or project.master_blend != "master/versions/" + target.master_sha256 + ".blend"
            or current_source.clip_id not in project.animations):
        raise ValidationError("Registered native projection differs from the explicit current selection")
    records = binding.file_map
    producer = binding.producer
    jobs = (
        ("neutral_first", producer.neutral_worker_job_ids[0], "neutral/first", True),
        ("neutral_second", producer.neutral_worker_job_ids[1], "neutral/second", True),
        ("source_intake_first", producer.source_intake_worker_job_ids[0], "source_intake_first", False),
        ("source_intake_second", producer.source_intake_worker_job_ids[1], "source_intake_second", False),
        ("body_first", producer.body_worker_job_ids[0], "body_first", False),
        ("body_second", producer.body_worker_job_ids[1], "body_second", False),
        ("body_reopen", producer.body_reopen_job_id, "body_reopen", False),
        ("playback", producer.cache_job_id, "playback", False),
        ("surface_verify", producer.surface_verification_job_id, "surface_verify", False),
    )
    proofs = tuple(NativeProducerProof(role, job_id,
        records[prefix + ("_request.json" if neutral else "/request.json")],
        records[prefix + ("_result.json" if neutral else "/result.json")])
        for role, job_id, prefix, neutral in jobs)
    return RegisteredNativeProofProjection(binding.sha256, project_sha256,
        current_source.clip_id, project.animations, proofs,
        tuple(records[name] for name in sorted(records)),
        records["source_snapshot.json"], records["native_mapping.json"],
        records["body_first/review_motion.blend"], records["body_first/target_timeline.json"])
