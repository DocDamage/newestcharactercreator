"""Strict JSON contract between desktop process and isolated Blender worker."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ucc.core.errors import ValidationError
from ucc.core.models import safe_relative_path
from .phenotype import validate_macro_parameters

PROTOCOL_VERSION = 1
SUPPORTED_OPERATIONS = {"inspect_environment", "inspect_character", "create_human", "export_preview_glb", "refit_human", "verify_skin_deformation", "verify_keyframed_timeline", "verify_local_bvh_motion", "verify_multi_bvh_chain", "verify_calibrated_bvh_chain", "verify_reviewed_bvh_chain", "inspect_fbx_animation", "verify_native_fbx_body", "reopen_native_fbx_body", "cache_native_fbx_body"}
MAX_REQUEST_BYTES = 256 * 1024


def _check_json(data: object) -> None:
    try:
        encoded = json.dumps(data, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Job options must be finite JSON: {exc}") from exc
    if len(encoded.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValidationError("Worker JSON request too large")


@dataclass(frozen=True, slots=True)
class JobRequest:
    job_id: str
    operation: str
    input_project: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if type(self.protocol_version) is not int or self.protocol_version != PROTOCOL_VERSION:
            raise ValidationError("Unsupported worker protocol version")
        try:
            UUID(self.job_id)
        except (ValueError, TypeError) as exc:
            raise ValidationError("job_id must be UUID") from exc
        if self.operation not in SUPPORTED_OPERATIONS:
            raise ValidationError(f"Unsupported Blender operation: {self.operation}")
        if self.input_project is not None:
            safe_relative_path(self.input_project, "input_project")
        if type(self.options) is not dict:
            raise ValidationError("options must be JSON object")
        _check_json(self.as_dict())
        if self.operation == "inspect_fbx_animation":
            from ucc.animations.source_rest_frames import is_sha256
            if self.input_project is not None or set(self.options) != {"source_sha256"} or not is_sha256(self.options["source_sha256"]):
                raise ValidationError("FBX intake requires only a source SHA-256 and no master")
        if self.operation == "verify_native_fbx_body":
            from ucc.animations.source_rest_frames import is_sha256
            hashes={"source_sha256","snapshot_sha256","mapping_sha256","master_sha256"}
            if (self.input_project!="candidate.blend" or set(self.options)!=hashes|{"render_private_frames"} or
                    type(self.options["render_private_frames"]) is not bool or any(not is_sha256(self.options[k]) for k in hashes)):
                raise ValidationError("Native body jobs require exact source/snapshot/map/master identities")
        if self.operation in {"reopen_native_fbx_body", "cache_native_fbx_body"}:
            from ucc.animations.source_rest_frames import is_sha256
            hashes={"source_sha256","snapshot_sha256","mapping_sha256","master_sha256","review_sha256","timeline_sha256"}
            if self.input_project!="candidate.blend" or set(self.options)!=hashes or any(not is_sha256(self.options[k]) for k in hashes):
                raise ValidationError("Native reopen requires exact source/master/map/snapshot/review/timeline identities")
        if self.operation == "create_human":
            if self.input_project is not None:
                raise ValidationError("create_human creates a new master; no input project allowed")
            if set(self.options) not in (set(), {"macro_parameters"}):
                raise ValidationError("create_human permits only saved MPFB macro parameters")
            if self.options:
                validate_macro_parameters(self.options["macro_parameters"])
        if self.operation == "inspect_character" and self.options:
            keys = set(self.options)
            if keys not in ({"macro_parameters"},
                            {"macro_parameters", "verify_rig_binding"}):
                raise ValidationError("inspect_character permits only MPFB macros and rig check")
            validate_macro_parameters(self.options["macro_parameters"])
            if "verify_rig_binding" in keys and self.options["verify_rig_binding"] is not True:
                raise ValidationError("verify_rig_binding must be true when requested")
        if self.operation in {"verify_skin_deformation", "verify_keyframed_timeline", "verify_local_bvh_motion"}:
            if self.options:
                raise ValidationError("Animation diagnostic uses fixed non-editable test settings")
        if self.operation in {"verify_multi_bvh_chain", "verify_calibrated_bvh_chain"}:
            if set(self.options) != {"axis_profile"} or self.options["axis_profile"] not in (
                "Y_UP_TO_Z_UP", "Z_UP_IDENTITY"
            ):
                raise ValidationError("Multi-bone BVH requires one fixed, explicit up-axis profile")
        if self.operation == "verify_reviewed_bvh_chain":
            if (not {"axis_profile", "reviewed_mapping"}.issubset(self.options) or
                set(self.options) - {"axis_profile", "reviewed_mapping", "source_rest_profile_sha256",
                                     "source_frame_conversion", "render_private_frames"}) or (
                self.options["axis_profile"] not in ("Y_UP_TO_Z_UP", "Z_UP_IDENTITY")
            ):
                raise ValidationError("Reviewed mapping requires explicitly selected BVH axes")
            from ucc.animations.review_mapping import validate_review_mapping
            validate_review_mapping(self.options["reviewed_mapping"])
            if "source_rest_profile_sha256" in self.options:
                from ucc.animations.source_rest_frames import is_sha256
                if not is_sha256(self.options["source_rest_profile_sha256"]):
                    raise ValidationError("Source rest profile requires an exact lowercase SHA-256")
            if "source_frame_conversion" in self.options:
                from ucc.animations.source_rest_frames import CONVERSION_CONVENTION
                if (self.options["source_frame_conversion"] != CONVERSION_CONVENTION or
                        "source_rest_profile_sha256" not in self.options):
                    raise ValidationError("Conversion audit requires bound frames and the fixed BVH convention")
            if "render_private_frames" in self.options and (
                self.options["render_private_frames"] is not True or "source_frame_conversion" not in self.options
            ):
                raise ValidationError("Private frame rendering requires the conversion audit")
        if self.operation == "refit_human":
            if set(self.options) != {"macro_parameters"}:
                raise ValidationError("refit_human permits only saved MPFB macro parameters")
            validate_macro_parameters(self.options["macro_parameters"])
        if self.operation in {"inspect_character", "export_preview_glb", "refit_human", "verify_skin_deformation", "verify_keyframed_timeline", "verify_local_bvh_motion", "verify_multi_bvh_chain", "verify_calibrated_bvh_chain", "verify_reviewed_bvh_chain"} and not self.input_project:
            raise ValidationError(f"{self.operation} needs input_project")
        if self.operation == "export_preview_glb" and self.options:
            raise ValidationError("Preview export uses fixed, offline safe settings")

    @classmethod
    def new(cls, operation: str, **kwargs: Any) -> "JobRequest":
        return cls(job_id=str(uuid4()), operation=operation, **kwargs)

    def as_dict(self) -> dict[str, Any]:
        return {"protocol_version": self.protocol_version, "job_id": self.job_id,
                "operation": self.operation, "input_project": self.input_project,
                "options": self.options}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRequest":
        if not isinstance(data, dict):
            raise ValidationError("Worker request must be object")
        expected = {"protocol_version", "job_id", "operation", "input_project", "options"}
        if set(data) != expected:
            raise ValidationError("Worker request fields mismatch")
        return cls(**data)


@dataclass(frozen=True, slots=True)
class JobResult:
    job_id: str
    operation: str
    status: str
    details: dict[str, Any]
    error: str | None = None
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValidationError("Unexpected worker result version")
        if self.status not in {"ok", "error"} or self.operation not in SUPPORTED_OPERATIONS:
            raise ValidationError("Invalid result status/operation")
        if type(self.details) is not dict:
            raise ValidationError("details must be an object")
        try:
            UUID(self.job_id)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Invalid result UUID") from exc
        if self.status == "error" and not self.error:
            raise ValidationError("Error result must provide diagnostic message")
        _check_json(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {"protocol_version": self.protocol_version, "job_id": self.job_id,
                "operation": self.operation, "status": self.status,
                "details": self.details, "error": self.error}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "JobResult":
        if not isinstance(raw, dict):
            raise ValidationError("Worker result must be JSON object")
        expected = {"protocol_version", "job_id", "operation", "status", "details", "error"}
        if set(raw) != expected:
            raise ValidationError("Worker result fields mismatch")
        return cls(**raw)
