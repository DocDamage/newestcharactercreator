"""NONSHIPPING producer double: synthetic bytes, no native/engine proof."""
from hashlib import sha256
from pathlib import Path
import shutil
from types import SimpleNamespace

from fixtures.godot_native_logic import stage_report
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_native_recipe import POLICY
from ucc.jobs.godot_registered_native_producer import OUTPUTS


class LazyMetadataFlood:
    """Bounded-consumption probe; the remaining foreign entries are never built."""
    def __init__(self, admitted_names, *, cancel=None):
        self.admitted_names = tuple(admitted_names)
        self.cancel = cancel
        self.consumed = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def __iter__(self):
        for index in range(100000):
            self.consumed += 1
            if self.consumed > 6:
                raise AssertionError("Metadata guard eagerly consumed the directory flood")
            if self.cancel is not None:
                self.cancel.set()
            name = (self.admitted_names[index] if index < len(self.admitted_names)
                    else "FOREIGN_FLOOD_" + str(index))
            yield SimpleNamespace(name=name)


class SyntheticRegisteredRunner:
    def __init__(self, root: Path, fault=None):
        self.root = root
        self.fault = fault or (lambda *args: None)
        self.jobs = []
        self.timeouts = []

    def run(self, job, *, staged_inputs, cancel, timeout_s):
        self.jobs.append(job)
        self.timeouts.append(timeout_s)
        folder = self.root / ("synthetic-worker-" + str(len(self.jobs)))
        folder.mkdir()
        for name, path in staged_inputs.items():
            shutil.copyfile(path, folder / name)
        stage = job.operation == "stage_registered_native_godot_runtime"
        raw = stage_report(job.options["native_recipe_sha256"])
        raw["policy"] = POLICY
        if stage:
            for name in OUTPUTS:
                (folder / name).write_bytes(("SYNTHETIC_NOT_NATIVE:" + name).encode())
            raw["files"] = {name: {"sha256": sha256((folder/name).read_bytes()).hexdigest(),
                                   "bytes": (folder/name).stat().st_size} for name in OUTPUTS}
            name, field = "native_stage.json", "native_stage_sha256"
        else:
            for key in ("source_names", "fps", "numpy_version", "files", "export_optimize_animation_size"):
                raw.pop(key)
            raw.update(status="FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED",
                native_stage_sha256=job.options["native_stage_sha256"], saved_output_rebuilt_or_repaired=False,
                frames=[dict(frame=i, source_error_m=0., normal_vector_error=0., raw_error_m=0.,
                             reconstruction_error_m=0., bone_world_error=0.) for i in range(1, 301)])
            name, field = "native_verification.json", "native_verification_sha256"
        self.fault("before_report", job, folder, raw)
        report = folder / name
        report.write_bytes(canonical_bytes(raw))
        details = dict(policy=POLICY, status=raw["status"], frame_count=300, engine_import_verified=False)
        details[field] = sha256(report.read_bytes()).hexdigest()
        self.fault("after_report", job, folder, raw)
        self.fault("result", job, folder, details)
        return SimpleNamespace(details=details), folder
