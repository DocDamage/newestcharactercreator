"""Nonshipping metadata only; no source, Action, cache or engine evidence."""
from uuid import UUID

from ucc.core.target_action import (
    TargetActionBinding, TargetActionFile, TargetActionProducer,
    TargetActionSource, TargetActionTarget,
)
from ucc.core.target_action_format import RETAINED_FILES, canonical_bytes
from ucc.core.target_action_request import TargetActionRequest


def metadata_pair():
    source = TargetActionSource("unit-asset", "unit-asset#clip-0000",
                                *[str(index) * 64 for index in range(1, 8)])
    request = TargetActionRequest(
        str(UUID(int=10)), "unit-project", 4, "a"*64, "b"*64, source,
        "c"*64, "ARMATURE_ORIGIN_DISPLACEMENT_V1", "d"*64, "e"*64,
        "Nonshipping metadata validation only", True)
    producer = TargetActionProducer(
        "d"*64, "e"*64, tuple(str(UUID(int=i)) for i in (1, 2)),
        tuple(str(UUID(int=i)) for i in (3, 4)),
        tuple(str(UUID(int=i)) for i in (5, 6)),
        str(UUID(int=7)), str(UUID(int=8)), str(UUID(int=9)))
    files = tuple(TargetActionFile(
        name, request.sha256 if name == "preparation_request.json" else "f"*64,
        len(canonical_bytes(request.to_dict())) if name == "preparation_request.json" else 1)
        for name in sorted(RETAINED_FILES))
    target = TargetActionTarget("unit-project", 4, "a"*64, "b"*64, "7"*64, "8"*64)
    binding = TargetActionBinding(request.sha256, source, target, "c"*64,
                                  "ARMATURE_ORIGIN_DISPLACEMENT_V1", producer, files)
    return request, binding
