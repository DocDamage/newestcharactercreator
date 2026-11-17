"""Closed private registered-input retention identities; no execution or grant."""
from dataclasses import dataclass
from hashlib import sha256
import json

from ucc.core.errors import ValidationError
from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
from ucc.core.target_action_format import checked_sha, checked_uuid, checked_text
from .godot_candidate_contract import EngineInputPermission, canonical_bytes
from .godot_runtime_contract import FILES
from .godot_runtime_data import LIMITS

POLICY = "UCC_PRIVATE_REGISTERED_NATIVE_INPUTS_V2"
NAMESPACE = "godot-registered-native-inputs"
MAX_MANIFEST_BYTES = 256 * 1024
PROOF_ROLES = {
    "native_review": "body_first/review_motion.blend",
    "native_timeline": "body_first/target_timeline.json",
    "source_snapshot": "source_snapshot.json",
    "native_mapping": "native_mapping.json",
}
METADATA_LIMITS = {
    "native_recipe.json": 256*1024, "source_receipt.json": 2*1024*1024,
    "runtime_request.json": 256*1024, "source_byte_validation.json": 2*1024*1024,
    "runtime_code_provenance.json": 256*1024,
    "stage_request.json": 256*1024, "stage_result.json": 256*1024,
    "native_stage.json": 4*1024*1024, "reopen_request.json": 256*1024,
    "reopen_result.json": 256*1024, "native_verification.json": 4*1024*1024,
}
PAYLOAD_FILES = FILES | frozenset(METADATA_LIMITS) | {".gdignore"}
FALSE_FLAGS = frozenset({"engine_import_verified", "runtime_execution_verified",
    "runtime_code_provenance_verified", "private_runtime_delivery_authorized",
    "visual_quality_approved", "usable_action_approved", "editing_authorized",
    "distribution_license_review_complete", "source_redistribution_authorized",
    "cloud_transmission_authorized"})


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def file_limit(name: str) -> int:
    if name in FILES:
        return LIMITS[name]
    if name in METADATA_LIMITS:
        return METADATA_LIMITS[name]
    if name == ".gdignore":
        return 0
    raise ValidationError("Unknown private registered-input payload name")


@dataclass(frozen=True, slots=True)
class RegisteredInputSelection:
    project_id: str
    revision: int
    project_sha256: str
    master_sha256: str
    clip_id: str
    binding_sha256: str
    source_binding_sha256: str
    catalog_record_sha256: str

    def __post_init__(self) -> None:
        checked_text(self.project_id, 160)
        checked_text(self.clip_id, 138)
        require(type(self.revision) is int and 0 <= self.revision <= 2**63-1,
                "Registered retention revision is invalid")
        for name in self.__dataclass_fields__:
            if name not in {"project_id", "revision", "clip_id"}:
                checked_sha(getattr(self, name))

    def to_dict(self) -> dict:
        return {name:getattr(self,name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, raw: object) -> "RegisteredInputSelection":
        require(type(raw) is dict and set(raw)==set(cls.__dataclass_fields__),
                "Registered selection has missing or unknown fields")
        return cls(**raw)

    def loader_args(self) -> dict:
        return dict(binding_sha256=self.binding_sha256, expected_project_id=self.project_id,
            expected_revision=self.revision, expected_master_blend="master/versions/"+self.master_sha256+".blend",
            expected_project_sha256=self.project_sha256, expected_clip_id=self.clip_id,
            expected_source_binding_sha256=self.source_binding_sha256,
            expected_catalog_record_sha256=self.catalog_record_sha256)


@dataclass(frozen=True, slots=True)
class RetainedInputFile:
    name: str
    sha256: str
    bytes: int

    def __post_init__(self) -> None:
        require(type(self.name) is str and self.name in PAYLOAD_FILES,
                "Retained input file is outside the closed payload")
        checked_sha(self.sha256)
        require(type(self.bytes) is int and 0 <= self.bytes <= file_limit(self.name)
                and (self.bytes > 0 or self.name==".gdignore"),
                "Retained input file exceeds its exact byte bound")
        if self.name==".gdignore":
            require(self.sha256==sha256(b"").hexdigest(), "Private .gdignore must stay empty")

    def to_dict(self) -> dict:
        return {"sha256":self.sha256,"bytes":self.bytes}


@dataclass(frozen=True, slots=True)
class RetainedProofReference:
    role: str
    name: str
    sha256: str
    bytes: int

    def __post_init__(self) -> None:
        require(type(self.role) is str and self.role in PROOF_ROLES
                and self.name==PROOF_ROLES[self.role], "Registered proof role/path differs")
        checked_sha(self.sha256)
        require(type(self.bytes) is int and 0 < self.bytes <= 512*1024*1024,
                "Registered proof reference size is invalid")

    def to_dict(self) -> dict:
        return {"name":self.name,"sha256":self.sha256,"bytes":self.bytes}


@dataclass(frozen=True, slots=True)
class RegisteredRuntimeManifest:
    retention_id: str
    selection: RegisteredInputSelection
    source_receipt_sha256: str
    recipe_sha256: str
    runtime_request_sha256: str
    stage_job_id: str
    reopen_job_id: str
    files: tuple[RetainedInputFile, ...]
    proofs: tuple[RetainedProofReference, ...]
    permissions: tuple[EngineInputPermission, ...]

    def __post_init__(self) -> None:
        checked_uuid(self.retention_id);checked_uuid(self.stage_job_id);checked_uuid(self.reopen_job_id)
        require(self.stage_job_id!=self.reopen_job_id, "Registered source requires distinct worker identities")
        require(type(self.selection) is RegisteredInputSelection,"Registered retention needs typed selection")
        for value in (self.source_receipt_sha256,self.recipe_sha256,self.runtime_request_sha256):checked_sha(value)
        require(type(self.files) is tuple and len(self.files)==len(PAYLOAD_FILES)
                and all(type(row) is RetainedInputFile for row in self.files)
                and {row.name for row in self.files}==PAYLOAD_FILES,
                "Registered retention requires its exact unique payload inventory")
        require(type(self.proofs) is tuple and len(self.proofs)==4
                and all(type(row) is RetainedProofReference for row in self.proofs)
                and {row.role for row in self.proofs}==set(PROOF_ROLES),
                "Registered retention requires four distinct bound proof references")
        require(type(self.permissions) is tuple and 3 <= len(self.permissions) <= 4
                and all(type(p) is EngineInputPermission for p in self.permissions)
                and len({p.asset_id for p in self.permissions})==len(self.permissions),
                "Registered retention needs distinct explicit source permissions")
        for permission in self.permissions:
            permission.require_godot()
            require(not permission.policy.ai_input_allowed and not permission.policy.redistribute_source_allowed,
                    "Private retention cannot grant AI or original-source redistribution")
        records={row.name:row for row in self.files}
        require(records["native_recipe.json"].sha256==self.recipe_sha256
                and records["source_receipt.json"].sha256==self.source_receipt_sha256
                and records["runtime_request.json"].sha256==self.runtime_request_sha256,
                "Registered manifest metadata anchors disagree")
        object.__setattr__(self,"files",tuple(sorted(self.files,key=lambda row:row.name)))
        object.__setattr__(self,"proofs",tuple(sorted(self.proofs,key=lambda row:row.role)))
        object.__setattr__(self,"permissions",tuple(sorted(self.permissions,key=lambda p:p.asset_id)))
        require(len(canonical_bytes(self.to_dict()))<=MAX_MANIFEST_BYTES,"Registered manifest is oversized")

    @property
    def sha256(self) -> str:
        return sha256(canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict:
        return {"schema_version":2,"policy":POLICY,"retention_id":self.retention_id,
            "selection":self.selection.to_dict(),"source_receipt_sha256":self.source_receipt_sha256,
            "recipe_sha256":self.recipe_sha256,"runtime_request_sha256":self.runtime_request_sha256,
            "stage_job_id":self.stage_job_id,"reopen_job_id":self.reopen_job_id,
            "files":{row.name:row.to_dict() for row in self.files},
            "proofs":{row.role:row.to_dict() for row in self.proofs},
            "permissions":[p.to_dict() for p in self.permissions],**{name:False for name in FALSE_FLAGS}}

    @classmethod
    def from_dict(cls, raw: object) -> "RegisteredRuntimeManifest":
        names=set(cls.__dataclass_fields__)|{"schema_version","policy"}|FALSE_FLAGS
        require(type(raw) is dict and set(raw)==names,"Registered manifest is not closed")
        require(type(raw["schema_version"]) is int and raw["schema_version"]==2 and raw["policy"]==POLICY
                and all(raw[name] is False for name in FALSE_FLAGS),"Registered manifest changed profile/readiness")
        require(type(raw["files"]) is dict and set(raw["files"])==PAYLOAD_FILES
                and type(raw["proofs"]) is dict and set(raw["proofs"])==set(PROOF_ROLES)
                and type(raw["permissions"]) is list,"Malformed registered manifest collections")
        def closed(row, keys):
            require(type(row) is dict and set(row)==keys,"Unknown/partial registered file record")
            return row
        files=tuple(RetainedInputFile(name,**closed(row,{"sha256","bytes"})) for name,row in raw["files"].items())
        proofs=tuple(RetainedProofReference(role,**closed(row,{"name","sha256","bytes"})) for role,row in raw["proofs"].items())
        return cls(raw["retention_id"],RegisteredInputSelection.from_dict(raw["selection"]),
            raw["source_receipt_sha256"],raw["recipe_sha256"],raw["runtime_request_sha256"],
            raw["stage_job_id"],raw["reopen_job_id"],files,proofs,
            tuple(EngineInputPermission.from_dict(value) for value in raw["permissions"]))

    @classmethod
    def from_bytes(cls, payload: bytes) -> "RegisteredRuntimeManifest":
        require(type(payload) is bytes and 0<len(payload)<=MAX_MANIFEST_BYTES,"Registered manifest bytes are unbounded")
        try:
            raw=json.loads(payload.decode("utf-8"),object_pairs_hook=_unique_project_fields,
                           parse_constant=_nonfinite_project_number)
        except (ValueError,UnicodeError,RecursionError) as error:
            raise ValidationError("Malformed registered manifest JSON") from error
        result=cls.from_dict(raw)
        require(canonical_bytes(result.to_dict())==payload,"Registered manifest is not canonical")
        return result
