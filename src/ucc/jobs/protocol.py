"""Strict JSON contract between desktop process and isolated Blender worker."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ucc.core.errors import ValidationError
from ucc.core.models import safe_relative_path

PROTOCOL_VERSION = 1
SUPPORTED_OPERATIONS = {"inspect_environment", "inspect_character", "create_human", "export_preview_glb"}
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
        if self.operation == "create_human" and self.options:
            raise ValidationError("MPFB creation options are not verified yet; use defaults")
        if self.operation in {"inspect_character", "export_preview_glb"} and not self.input_project:
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
