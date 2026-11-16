"""Immutable registered target-preview metadata, separate from source records."""
from dataclasses import dataclass

from .target_action_format import (
    ADMISSION, CLOCK, MAX_TOTAL_BYTES, POLICY, PROFILE, RETAINED_FILES,
    ROOT_POLICIES, SKIN_POLICY, TargetActionFile, canonical_bytes,
    checked_fixed, checked_pair, checked_sha, checked_text, checked_uuid,
    closed, document_sha256, read_document, require,
)


@dataclass(frozen=True, slots=True)
class TargetActionSource:
    asset_id: str
    clip_id: str
    source_sha256: str
    source_binding_sha256: str
    catalog_receipt_sha256: str
    catalog_policy_sha256: str
    catalog_record_sha256: str
    snapshot_sha256: str
    skeleton_fingerprint: str

    def __post_init__(self):
        checked_text(self.asset_id, 128)
        checked_text(self.clip_id, 138)
        require(self.clip_id == self.asset_id + "#clip-0000",
                "Target preview needs the exact registered single-clip identity")
        for name in self.__dataclass_fields__:
            if name not in {"asset_id", "clip_id"}:
                checked_sha(getattr(self, name))

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, raw: object) -> "TargetActionSource":
        return cls(**closed(raw, set(cls.__dataclass_fields__)))


@dataclass(frozen=True, slots=True)
class TargetActionTarget:
    project_id: str
    revision: int
    project_sha256: str
    master_sha256: str
    neutral_state_sha256: str
    rest_sha256: str
    family: str = "humanoid.v1"

    def __post_init__(self):
        checked_text(self.project_id)
        require(type(self.revision) is int and 0 <= self.revision <= 2**63 - 1,
                "Target preview revision is invalid")
        require(type(self.family) is str and self.family == "humanoid.v1",
                "Unsupported target preview rig family")
        for name in ("project_sha256", "master_sha256", "neutral_state_sha256", "rest_sha256"):
            checked_sha(getattr(self, name))

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, raw: object) -> "TargetActionTarget":
        return cls(**closed(raw, set(cls.__dataclass_fields__)))


@dataclass(frozen=True, slots=True)
class TargetActionProducer:
    blender_executable_sha256: str
    worker_resources_sha256: str
    neutral_worker_job_ids: tuple[str, str]
    source_intake_worker_job_ids: tuple[str, str]
    body_worker_job_ids: tuple[str, str]
    body_reopen_job_id: str
    cache_job_id: str
    surface_verification_job_id: str

    def __post_init__(self):
        checked_sha(self.blender_executable_sha256)
        checked_sha(self.worker_resources_sha256)
        for name in ("neutral_worker_job_ids", "source_intake_worker_job_ids", "body_worker_job_ids"):
            checked_pair(getattr(self, name))
        for name in ("body_reopen_job_id", "cache_job_id", "surface_verification_job_id"):
            checked_uuid(getattr(self, name))
        require(len(set(self.worker_job_ids)) == 9,
                "Target preview requires nine distinct actual worker identities")

    @property
    def worker_job_ids(self) -> tuple[str, ...]:
        return (*self.neutral_worker_job_ids, *self.source_intake_worker_job_ids,
                *self.body_worker_job_ids, self.body_reopen_job_id, self.cache_job_id,
                self.surface_verification_job_id)

    def to_dict(self) -> dict:
        return {name: list(value) if type(value) is tuple else value
                for name in self.__dataclass_fields__ for value in (getattr(self, name),)}

    @classmethod
    def from_dict(cls, raw: object) -> "TargetActionProducer":
        value = dict(closed(raw, set(cls.__dataclass_fields__)))
        for name in ("neutral_worker_job_ids", "source_intake_worker_job_ids", "body_worker_job_ids"):
            require(type(value[name]) is list and len(value[name]) == 2,
                    "Target preview worker pair is malformed")
            value[name] = tuple(value[name])
        return cls(**value)


@dataclass(frozen=True, slots=True)
class TargetActionBinding:
    preparation_request_sha256: str
    source: TargetActionSource
    target: TargetActionTarget
    mapping_sha256: str
    root_motion_policy: str
    producer: TargetActionProducer
    files: tuple[TargetActionFile, ...]

    def __post_init__(self):
        checked_sha(self.preparation_request_sha256)
        checked_sha(self.mapping_sha256)
        require(type(self.source) is TargetActionSource and type(self.target) is TargetActionTarget
                and type(self.producer) is TargetActionProducer,
                "Target preview needs typed source, target and producer metadata")
        require(type(self.root_motion_policy) is str and self.root_motion_policy in ROOT_POLICIES,
                "Target preview root policy differs from the existing native policy")
        require(type(self.files) is tuple and len(self.files) == len(RETAINED_FILES)
                and all(type(item) is TargetActionFile for item in self.files),
                "Target preview needs the exact retained proof inventory")
        names = [item.name for item in self.files]
        require(len(set(names)) == len(names) and set(names) == RETAINED_FILES,
                "Target preview proof inventory has duplicate or missing files")
        require(sum(item.bytes for item in self.files) <= MAX_TOTAL_BYTES,
                "Target preview proof inventory exceeds its total byte limit")
        require(self.file_map["preparation_request.json"].sha256 == self.preparation_request_sha256,
                "Target preview names a different input preparation request")
        canonical_bytes(self.to_dict())

    @property
    def file_map(self) -> dict[str, TargetActionFile]:
        return {item.name: item for item in self.files}

    @property
    def sha256(self) -> str:
        return document_sha256(self.to_dict())

    @property
    def profile(self) -> str:
        return PROFILE

    def to_dict(self) -> dict:
        return {
            "schema_version": 1, "policy": POLICY, "profile": PROFILE,
            "preparation_request_sha256": self.preparation_request_sha256,
            "source": self.source.to_dict(), "target": self.target.to_dict(),
            "mapping": {"profile_sha256": self.mapping_sha256,
                        "root_motion_policy": self.root_motion_policy,
                        "skin_deformation_policy": SKIN_POLICY},
            "clock": dict(CLOCK), "producer": self.producer.to_dict(),
            "files": {item.name: item.to_dict() for item in sorted(self.files, key=lambda item: item.name)},
            "admission": dict(ADMISSION),
        }

    @classmethod
    def from_dict(cls, raw: object) -> "TargetActionBinding":
        value = closed(raw, {"schema_version", "policy", "profile", "preparation_request_sha256",
                             "source", "target", "mapping", "clock", "producer", "files", "admission"})
        require(type(value["schema_version"]) is int and value["schema_version"] == 1
                and value["policy"] == POLICY and value["profile"] == PROFILE,
                "Unsupported target preview metadata version/profile")
        checked_fixed(value["clock"], CLOCK)
        checked_fixed(value["admission"], ADMISSION)
        mapping = closed(value["mapping"],
                         {"profile_sha256", "root_motion_policy", "skin_deformation_policy"})
        require(mapping["skin_deformation_policy"] == SKIN_POLICY,
                "Unsupported target preview corrective skin policy")
        files = closed(value["files"], set(RETAINED_FILES))
        return cls(value["preparation_request_sha256"], TargetActionSource.from_dict(value["source"]),
                   TargetActionTarget.from_dict(value["target"]), mapping["profile_sha256"],
                   mapping["root_motion_policy"], TargetActionProducer.from_dict(value["producer"]),
                   tuple(TargetActionFile.from_dict(name, files[name]) for name in sorted(files)))

    @classmethod
    def from_bytes(cls, payload: bytes) -> "TargetActionBinding":
        return cls.from_dict(read_document(payload))
