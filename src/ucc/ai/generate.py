"""Explicitly-authorized, loopback-only ComfyUI text-to-image jobs.

Uses only built-in default nodes and a locally installed checkpoint. No upload,
cloud call, remote hostname, custom node, model install or arbitrary workflow JSON.
This generates 2D reference PNGs, not ready-to-rig 3D characters.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import zlib
import uuid
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import HTTPError, URLError
from typing import Any

from ucc.ai.probe import _RejectRedirects, validate_loopback_base
from ucc.core.errors import UCCError, ValidationError

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_RESULT_IMAGES = 4
BUILTIN_NODES = frozenset({
    "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
    "KSampler", "VAEDecode", "SaveImage",
})
FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\.png$")


class ComfyGenerationError(UCCError):
    pass


def _verify_png(data: bytes) -> tuple[int, int]:
    """Validate basic PNG chunks, CRC and bounds without decompressing untrusted pixels."""
    if len(data) < 45 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ComfyGenerationError("ComfyUI output is not a PNG image")
    offset = 8
    has_idat = False
    has_end = False
    size: tuple[int, int] | None = None
    chunks = 0
    while offset < len(data):
        if offset + 12 > len(data):
            raise ComfyGenerationError("Truncated PNG output chunk")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        if length > MAX_IMAGE_BYTES or offset + length + 12 > len(data):
            raise ComfyGenerationError("Invalid PNG chunk length")
        payload = data[offset + 8:offset + 8 + length]
        expected = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != expected:
            raise ComfyGenerationError("PNG output checksum mismatch")
        if chunks == 0:
            if kind != b"IHDR" or length != 13:
                raise ComfyGenerationError("PNG missing IHDR")
            width, height = struct.unpack(">II", payload[:8])
            if not (1 <= width <= 4096 and 1 <= height <= 4096):
                raise ComfyGenerationError("ComfyUI PNG dimensions out of bounds")
            size = (width, height)
        if kind == b"IDAT":
            has_idat = True
        if kind == b"IEND":
            if length != 0 or offset + 12 != len(data):
                raise ComfyGenerationError("Invalid PNG trailer")
            has_end = True
            break
        chunks += 1
        if chunks > 50_000:
            raise ComfyGenerationError("Too many PNG chunks")
        offset += 12 + length
    if size is None or not has_idat or not has_end:
        raise ComfyGenerationError("PNG output missing required data")
    return size


@dataclass(frozen=True, slots=True)
class TextToImageSpec:
    checkpoint: str
    prompt: str
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0
    seed: int = 0
    sampler: str = "euler"
    scheduler: str = "normal"

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, str) or not self.checkpoint or len(self.checkpoint) > 255:
            raise ValidationError("Choose a named checkpoint already installed locally")
        if any(c in self.checkpoint for c in "\r\n\x00"):
            raise ValidationError("Invalid checkpoint name")
        for value, label in ((self.prompt, "prompt"), (self.negative_prompt, "negative_prompt")):
            if not isinstance(value, str) or len(value) > 4000:
                raise ValidationError(f"{label} exceeds 4000 characters")
        if not self.prompt.strip():
            raise ValidationError("A text prompt is required")
        for key in ("width", "height"):
            val = getattr(self, key)
            if type(val) is not int or not 64 <= val <= 1024 or val % 64:
                raise ValidationError(f"{key} must be a 64-pixel multiple between 64 and 1024")
        if self.width * self.height > 1024 * 1024:
            raise ValidationError("Requested image area exceeds conservative RTX 3060 generation bounds")
        if type(self.steps) is not int or not 1 <= self.steps <= 60:
            raise ValidationError("steps must be 1..60")
        if type(self.seed) is not int or not 0 <= self.seed < (2**64):
            raise ValidationError("seed must be an unsigned 64-bit integer")
        if type(self.cfg) not in (int, float) or not 1.0 <= self.cfg <= 15.0:
            raise ValidationError("cfg must be finite and between 1 and 15")
        if self.sampler != "euler" or self.scheduler != "normal":
            raise ValidationError("Only the audited euler/normal built-in workflow is enabled")


def workflow(spec: TextToImageSpec, output_prefix: str) -> dict[str, dict[str, Any]]:
    if not re.fullmatch(r"UCC_[a-f0-9]{12}", output_prefix):
        raise ValidationError("Invalid generated output prefix")
    # Fixed wiring from ComfyUI's official default text-to-image API example.
    return {
        "3": {"class_type": "KSampler", "inputs": {
            "cfg": spec.cfg, "denoise": 1.0, "latent_image": ["5", 0], "model": ["4", 0],
            "negative": ["7", 0], "positive": ["6", 0],
            "sampler_name": spec.sampler, "scheduler": spec.scheduler,
            "seed": spec.seed, "steps": spec.steps}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": spec.checkpoint}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {
            "batch_size": 1, "height": spec.height, "width": spec.width}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": spec.prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": spec.negative_prompt}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {
            "filename_prefix": output_prefix, "images": ["8", 0]}},
    }


@dataclass(frozen=True, slots=True)
class QueuedConcept:
    prompt_id: str
    node_count: int
    workflow_sha256: str
    status: str = "QUEUED_UNVERIFIED"

    def to_dict(self) -> dict[str, Any]:
        return {"prompt_id": self.prompt_id, "node_count": self.node_count,
                "workflow_sha256": self.workflow_sha256, "status": self.status,
                "image_saved": False, "geometry_generated": False}


class ComfyUIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = validate_loopback_base(base_url)
        self._opener = build_opener(ProxyHandler({}), _RejectRedirects())

    def _fetch(self, endpoint: str, data: dict | None = None, *, max_bytes: int = MAX_JSON_BYTES,
               expect_image: bool = False) -> bytes:
        if not endpoint.startswith("/") or endpoint.startswith("//"):
            raise ValidationError("Invalid ComfyUI endpoint")
        payload = json.dumps(data, allow_nan=False, separators=(",", ":")).encode() if data is not None else None
        if payload is not None and len(payload) > 65_536:
            raise ValidationError("ComfyUI job exceeds request size limit")
        req = Request(self.base_url + endpoint, data=payload,
                      headers={"Accept": "image/png" if expect_image else "application/json",
                               **({"Content-Type": "application/json"} if payload is not None else {})},
                      method="POST" if data is not None else "GET")
        try:
            with self._opener.open(req, timeout=15) as resp:
                if resp.status != 200:
                    raise ComfyGenerationError(f"Local ComfyUI HTTP error {resp.status}")
                declared = resp.headers.get("Content-Length")
                if declared and int(declared) > max_bytes:
                    raise ComfyGenerationError("Local ComfyUI response exceeds safe size limit")
                raw = resp.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise ComfyGenerationError("Local ComfyUI response exceeded safe size limit")
                return raw
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ComfyGenerationError(f"Local ComfyUI service unavailable or request rejected: {type(exc).__name__}") from exc

    def _json(self, endpoint: str, data: dict | None = None) -> Any:
        try:
            return json.loads(self._fetch(endpoint, data).decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ComfyGenerationError("Invalid JSON response from local ComfyUI") from exc

    def check_dependencies(self, spec: TextToImageSpec) -> None:
        classes = self._json("/object_info")
        if not isinstance(classes, dict) or not BUILTIN_NODES.issubset(classes.keys()):
            missing = sorted(BUILTIN_NODES - set(classes)) if isinstance(classes, dict) else sorted(BUILTIN_NODES)
            raise ComfyGenerationError("ComfyUI is missing required built-in workflow nodes: " + ", ".join(missing))
        checkpoints = self._json("/models/checkpoints")
        if not isinstance(checkpoints, list) or not all(isinstance(x, str) for x in checkpoints):
            raise ComfyGenerationError("ComfyUI checkpoint API not supported; cannot safely select a model")
        if spec.checkpoint not in checkpoints:
            raise ComfyGenerationError("Selected checkpoint is not listed as installed by ComfyUI")

    def submit(self, spec: TextToImageSpec, *, explicitly_authorized: bool = False) -> QueuedConcept:
        if explicitly_authorized is not True:
            raise ComfyGenerationError("Local AI generation requires explicit per-job user approval")
        self.check_dependencies(spec)
        # Generate unique output prefix independent of prompt and local user paths.
        prefix = "UCC_" + uuid.uuid4().hex[:12]
        graph = workflow(spec, prefix)
        canonical = json.dumps(graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = sha256(canonical).hexdigest()
        answer = self._json("/prompt", {"prompt": graph, "client_id": str(uuid.uuid4())})
        if not isinstance(answer, dict):
            raise ComfyGenerationError("ComfyUI did not return a queue object")
        try:
            prompt_id = str(uuid.UUID(str(answer["prompt_id"])))
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise ComfyGenerationError("ComfyUI returned no valid prompt ID") from exc
        if answer.get("node_errors"):
            raise ComfyGenerationError("ComfyUI reported workflow validation errors")
        return QueuedConcept(prompt_id, len(graph), digest)

    def fetch_images(self, prompt_id: str, output_dir: str | Path) -> dict[str, Any]:
        """Explicitly fetch previously queued output; returns PENDING if no history yet."""
        try:
            clean_id = str(uuid.UUID(prompt_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError("prompt_id must be a UUID") from exc
        history = self._json("/history/" + clean_id)
        if not isinstance(history, dict):
            raise ComfyGenerationError("Invalid ComfyUI history response")
        if clean_id not in history:
            return {"status": "PENDING", "prompt_id": clean_id, "images": []}
        entry = history[clean_id]
        if not isinstance(entry, dict):
            raise ComfyGenerationError("Invalid ComfyUI history entry")
        outputs = entry.get("outputs", {})
        if not isinstance(outputs, dict) or not isinstance(outputs.get("9", {}), dict):
            raise ComfyGenerationError("ComfyUI history lacks expected SaveImage node output")
        images = outputs.get("9", {}).get("images", [])
        if not isinstance(images, list) or not 1 <= len(images) <= MAX_RESULT_IMAGES:
            raise ComfyGenerationError("ComfyUI has no bounded PNG images from this job")
        root = Path(output_dir).expanduser()
        if root.is_symlink():
            raise ValidationError("Output folder cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise ValidationError("Invalid local output directory")
        # Read/validate all outputs before promoting any file.
        downloaded: list[tuple[Path, bytes]] = []
        for index, entry in enumerate(images):
            if not isinstance(entry, dict) or entry.get("type") != "output" or entry.get("subfolder", "") != "":
                raise ComfyGenerationError("Unsupported ComfyUI output location")
            name = entry.get("filename")
            if not isinstance(name, str) or not FILENAME_RE.fullmatch(name) or ".." in name:
                raise ComfyGenerationError("Unsafe ComfyUI output image filename")
            query = urlencode({"filename": name, "subfolder": "", "type": "output"})
            raw = self._fetch("/view?" + query, max_bytes=MAX_IMAGE_BYTES, expect_image=True)
            _verify_png(raw)
            dest = root / f"ucc_{clean_id}_{index:02d}.png"
            if dest.exists() or dest.is_symlink():
                raise ComfyGenerationError("Local output already exists; will not overwrite")
            downloaded.append((dest, raw))
        staged: list[Path] = []
        committed: list[Path] = []
        try:
            for dest, raw in downloaded:
                temp = dest.with_suffix(".png.part")
                if temp.exists() or temp.is_symlink():
                    raise ComfyGenerationError("Staging output already exists")
                with temp.open("xb") as f:
                    f.write(raw)
                    f.flush()
                    import os
                    os.fsync(f.fileno())
                staged.append(temp)
            for (dest, _), temp in zip(downloaded, staged):
                # Hard link is no-clobber on NTFS and POSIX, unlike a replace operation.
                import os
                os.link(temp, dest)
                committed.append(dest)
            return {"status": "PNG_DOWNLOADED_UNREVIEWED", "prompt_id": clean_id,
                    "images": [{"file": str(p), "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
                               for p, raw in downloaded],
                    "geometry_generated": False, "source_license_checked": False}
        except BaseException:
            for dest in committed:
                dest.unlink(missing_ok=True)
            raise
        finally:
            for temp in staged:
                temp.unlink(missing_ok=True)
