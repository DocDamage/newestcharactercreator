"""Compact finite JSON for the bounded worker response wire contract.

Pretty-print whitespace can exceed the existing 256 KiB response-file limit
for supported 64-joint/240-frame source-rest diagnostic evidence.
"""
from __future__ import annotations

import json
from typing import Any


def encode_result(reply: dict[str, Any]) -> str:
    return json.dumps(reply, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
