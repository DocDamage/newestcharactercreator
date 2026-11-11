"""Read-only reachability/capability probes for locally hosted AI services.

No checkpoint downloads, workflow submission or model changes are performed.
External/cloud URLs are deliberately disabled until an explicit provider policy
and authorization flow is implemented.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

from ucc.core.errors import ValidationError


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True, slots=True)
class AIProbe:
    provider: str
    base_url: str
    reachable: bool
    summary: str
    details: dict

    def to_dict(self) -> dict:
        return {"provider": self.provider, "base_url": self.base_url,
                "reachable": self.reachable, "summary": self.summary,
                "details": self.details}


def validate_loopback_base(url: str) -> str:
    if not isinstance(url, str) or len(url) > 255:
        raise ValidationError("AI server URL must be a short local HTTP URL")
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValidationError("Only explicit loopback HTTP servers are supported in this stage")
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValidationError("AI server URL cannot include credentials, paths or query strings")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("AI server port invalid") from exc
    if port is None or not 1 <= port <= 65535:
        raise ValidationError("AI server must use an explicit TCP port")
    return url.rstrip("/")


def _get_json(base_url: str, endpoint: str, max_bytes: int = 4_000_000) -> object:
    # Local probes must not traverse a system HTTP proxy or external redirects.
    opener = build_opener(ProxyHandler({}), _RejectRedirects())
    request = Request(base_url + endpoint, method="GET", headers={"Accept": "application/json"})
    with opener.open(request, timeout=3) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("AI probe response too large")
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("AI probe response exceeded safe limit")
        return json.loads(content.decode("utf-8"))


def probe_comfyui(base_url: str = "http://127.0.0.1:8188") -> AIProbe:
    url = validate_loopback_base(base_url)
    try:
        stats = _get_json(url, "/system_stats")
        if not isinstance(stats, dict) or "system" not in stats:
            raise ValueError("Expected ComfyUI system_stats response")
        info = stats.get("system", {})
        # Never enumerate or upload the user's full checkpoint filenames in this probe.
        summary = "ComfyUI system API available"
        details = {"os": info.get("os") if isinstance(info, dict) else None,
                   "version": info.get("comfyui_version") if isinstance(info, dict) else None,
                   "can_submit_workflows": False}
        return AIProbe("comfyui", url, True, summary, details)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, URLError, HTTPError) as exc:
        return AIProbe("comfyui", url, False, f"ComfyUI unavailable: {type(exc).__name__}", {})


def probe_webui(base_url: str = "http://127.0.0.1:7860") -> AIProbe:
    url = validate_loopback_base(base_url)
    try:
        model_list = _get_json(url, "/sdapi/v1/sd-models")
        if not isinstance(model_list, list):
            raise ValueError("Expected WebUI model list array")
        return AIProbe("stable-diffusion-webui", url, True,
                       "Stable Diffusion WebUI API available",
                       {"model_count": len(model_list), "model_names_shared": False,
                        "can_submit_workflows": False})
    except (OSError, ValueError, TypeError, json.JSONDecodeError, URLError, HTTPError) as exc:
        return AIProbe("stable-diffusion-webui", url, False,
                       f"Stable Diffusion WebUI unavailable: {type(exc).__name__}", {})
