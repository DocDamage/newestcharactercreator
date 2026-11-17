"""Explicit per-use private body300 execution selection; no delivery grant."""
from dataclasses import dataclass
from hashlib import sha256
import json
from ucc.core.errors import ValidationError
from ucc.core.storage import _unique_project_fields,_nonfinite_project_number
from ucc.core.target_action_format import checked_sha,checked_uuid,checked_text
from .godot_candidate_contract import canonical_bytes
from .godot_runtime_contract import CODE_FILES,CAPABILITY

POLICY="UCC_PRIVATE_REGISTERED_BODY300_EXECUTION_V1"
PROFILE="GODOT_4_7_1_MOBILE_VULKAN_BODY300_V1"
STATUS="REGISTERED_BODY300_GPU_GEOMETRY_NORMALS_DIAGNOSTIC_VERIFIED"
VERTICES=13380
FRAMES=300
REFERENCE_BYTES=FRAMES*VERTICES*12
OUTPUT_BYTES=FRAMES*VERTICES*16
FALSE_FLAGS=frozenset({"engine_import_verified","visual_quality_approved","usable_action_approved",
    "material_appearance_verified","distribution_license_review_complete","private_runtime_delivery_authorized",
    "runtime_code_provenance_verified","source_redistribution_authorized","cloud_transmission_authorized",
    "shipping_runtime_implemented"})


@dataclass(frozen=True,slots=True)
class RuntimeCodeSelection:
    name:str
    sha256:str
    bytes:int

    def __post_init__(self)->None:
        if type(self.name) is not str or self.name not in CODE_FILES or type(self.bytes) is not int or not 1<=self.bytes<=256*1024:
            raise ValidationError("Select bounded exact private runtime code")
        checked_sha(self.sha256)


@dataclass(frozen=True,slots=True)
class RegisteredRuntimeExecutionSelection:
    execution_id:str
    retention_manifest_sha256:str
    code:tuple[RuntimeCodeSelection,...]
    provenance_sha256:str
    godot_executable_sha256:str
    godot_main_sha256:str
    purpose:str
    private_local_code_execution_confirmed:bool
    capability:str=CAPABILITY

    def __post_init__(self)->None:
        checked_uuid(self.execution_id);checked_text(self.purpose,500)
        for value in (self.retention_manifest_sha256,self.provenance_sha256,
                      self.godot_executable_sha256,self.godot_main_sha256):checked_sha(value)
        if (self.private_local_code_execution_confirmed is not True or self.capability!=CAPABILITY
                or type(self.code) is not tuple or len(self.code)!=7
                or any(type(row) is not RuntimeCodeSelection for row in self.code)
                or {row.name for row in self.code}!=CODE_FILES):
            raise ValidationError("Require explicit per-use local execution of the exact seven selected programs")
        object.__setattr__(self,"code",tuple(sorted(self.code,key=lambda row:row.name)))

    def to_dict(self)->dict:
        return dict(schema_version=1,policy=POLICY,profile=PROFILE,execution_id=self.execution_id,
            retention_manifest_sha256=self.retention_manifest_sha256,
            code={r.name:dict(sha256=r.sha256,bytes=r.bytes) for r in self.code},
            provenance_sha256=self.provenance_sha256,godot_executable_sha256=self.godot_executable_sha256,
            godot_main_sha256=self.godot_main_sha256,purpose=self.purpose,
            private_local_code_execution_confirmed=True,capability=self.capability,
            **{name:False for name in FALSE_FLAGS})

    @property
    def sha256(self)->str:return sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_bytes(cls,payload:bytes)->"RegisteredRuntimeExecutionSelection":
        if type(payload) is not bytes or not 0<len(payload)<=256*1024:
            raise ValidationError("Unbounded execution selection")
        try:
            raw=json.loads(payload.decode("utf-8"),object_pairs_hook=_unique_project_fields,parse_constant=_nonfinite_project_number)
            keys=set(cls.__dataclass_fields__)|{"schema_version","policy","profile"}|FALSE_FLAGS
            if (type(raw) is not dict or set(raw)!=keys or type(raw['schema_version']) is not int
                    or raw['schema_version']!=1 or raw['policy']!=POLICY or raw['profile']!=PROFILE
                    or any(raw[name] is not False for name in FALSE_FLAGS)
                    or type(raw['code']) is not dict or set(raw['code'])!=CODE_FILES):
                raise ValidationError("Execution selection changed its closed profile or grants")
            rows=[]
            for name,value in raw['code'].items():
                if type(value) is not dict or set(value)!={'sha256','bytes'}:
                    raise ValidationError("Malformed execution code identity")
                rows.append(RuntimeCodeSelection(name,**value))
            fields={name:raw[name] for name in cls.__dataclass_fields__ if name!='code'}
            result=cls(code=tuple(rows),**fields)
            if canonical_bytes(result.to_dict())!=payload:raise ValidationError("Execution selection is not canonical")
            return result
        except (ValueError,TypeError,UnicodeError,RecursionError) as error:
            raise ValidationError("Malformed execution selection JSON") from error
