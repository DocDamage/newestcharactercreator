"""Input request for local registered target previews; no engine-use grant."""
from dataclasses import dataclass

from .target_action import TargetActionSource
from .target_action_format import (
    CLOCK, PROFILE, REQUEST_POLICY, ROOT_POLICIES, SKIN_POLICY, canonical_bytes,
    checked_fixed, checked_sha, checked_text, checked_uuid, closed,
    document_sha256, read_document, require,
)


@dataclass(frozen=True, slots=True)
class TargetActionRequest:
    job_id: str
    project_id: str
    revision: int
    project_sha256: str
    master_sha256: str
    source: TargetActionSource
    mapping_sha256: str
    root_motion_policy: str
    blender_executable_sha256: str
    worker_resources_sha256: str
    purpose: str
    local_preview_confirmed: bool

    def __post_init__(self):
        checked_uuid(self.job_id)
        checked_text(self.project_id)
        checked_text(self.purpose, 2000)
        require(type(self.revision) is int and 0 <= self.revision <= 2**63 - 1,
                "Target preview request revision is invalid")
        require(type(self.source) is TargetActionSource,
                "Target preview request requires the registered source metadata")
        for name in ("project_sha256", "master_sha256", "mapping_sha256",
                     "blender_executable_sha256", "worker_resources_sha256"):
            checked_sha(getattr(self, name))
        require(type(self.root_motion_policy) is str and self.root_motion_policy in ROOT_POLICIES,
                "Target preview request root policy is unsupported")
        require(type(self.local_preview_confirmed) is bool and self.local_preview_confirmed,
                "Confirm the exact reviewed source for this private local preview")
        canonical_bytes(self.to_dict())

    @property
    def sha256(self) -> str:
        return document_sha256(self.to_dict())

    @property
    def profile(self) -> str:
        return PROFILE

    def to_dict(self) -> dict:
        return {
            "schema_version": 1, "policy": REQUEST_POLICY, "profile": PROFILE,
            "job_id": self.job_id, "project_id": self.project_id, "revision": self.revision,
            "project_sha256": self.project_sha256, "master_sha256": self.master_sha256,
            "source": self.source.to_dict(), "mapping_sha256": self.mapping_sha256,
            "root_motion_policy": self.root_motion_policy, "skin_deformation_policy": SKIN_POLICY,
            "blender_executable_sha256": self.blender_executable_sha256,
            "worker_resources_sha256": self.worker_resources_sha256,
            "purpose": self.purpose, "local_preview_confirmed": self.local_preview_confirmed,
            "clock": dict(CLOCK), "local_preview_only": True,
            "engine_import_verified": False, "editing_authorized": False,
            "source_redistribution_authorized": False, "cloud_transmission_authorized": False,
            "visual_quality_approved": False, "usable_action_approved": False,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "TargetActionRequest":
        fields = set(cls.__dataclass_fields__) | {
            "schema_version", "policy", "profile", "clock", "skin_deformation_policy",
            "local_preview_only", "engine_import_verified", "editing_authorized",
            "source_redistribution_authorized", "cloud_transmission_authorized",
            "visual_quality_approved", "usable_action_approved",
        }
        value = closed(raw, fields)
        require(type(value["schema_version"]) is int and value["schema_version"] == 1
                and value["policy"] == REQUEST_POLICY and value["profile"] == PROFILE
                and value["skin_deformation_policy"] == SKIN_POLICY,
                "Unsupported target preview preparation request")
        checked_fixed(value["clock"], CLOCK)
        for name in ("engine_import_verified", "editing_authorized", "source_redistribution_authorized",
                     "cloud_transmission_authorized", "visual_quality_approved", "usable_action_approved"):
            require(value[name] is False, "Private target preview request cannot grant broader readiness")
        require(value["local_preview_only"] is True, "Target preview request scope must stay private")
        values = {name: value[name] for name in cls.__dataclass_fields__}
        values["source"] = TargetActionSource.from_dict(value["source"])
        return cls(**values)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "TargetActionRequest":
        return cls.from_dict(read_document(payload))
