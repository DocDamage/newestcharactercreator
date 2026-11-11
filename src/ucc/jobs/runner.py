"""Bounded, cancellable subprocess jobs; no shell, no implicit file promotion.

Job results are staged, *not* proof that MPFB or a game engine works. A separate
acceptance test must validate staged files and real Blender reopen behavior.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
import shutil
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from ucc.core.errors import UCCError, ValidationError
from ucc.core.models import safe_relative_path
from .protocol import JobRequest, JobResult, MAX_REQUEST_BYTES


class WorkerFailure(UCCError):
    """Worker process, protocol, timeout, or cancellation failure."""


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    return_code: int | None
    stdout_tail: str
    stderr_tail: str
    elapsed_seconds: float
    cancelled: bool = False
    timed_out: bool = False


def _tail(path: Path, max_bytes: int = 8192) -> str:
    try:
        with path.open("rb") as f:
            f.seek(max(0, path.stat().st_size - max_bytes))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return "<log unavailable>"


def _stop_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def run_process(command: list[str], workdir: Path, *, timeout_s: float = 120,
                cancel: threading.Event | None = None) -> ProcessOutcome:
    """Generic process helper; tests may use Python, production uses Blender."""
    if not command or not all(isinstance(x, str) and x for x in command):
        raise ValidationError("Executable command must be a list of nonempty strings")
    if not 0.05 <= timeout_s <= 3600:
        raise ValidationError("timeout_s out of range")
    workdir.mkdir(parents=True, exist_ok=True)
    stdout_path = workdir / "stdout.log"
    stderr_path = workdir / "stderr.log"
    if cancel is not None and cancel.is_set():
        return ProcessOutcome(None, "", "", 0.0, cancelled=True)
    start = time.monotonic()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        proc: subprocess.Popen[bytes] = subprocess.Popen(
            command, cwd=workdir, shell=False, stdout=stdout, stderr=stderr,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0),
            start_new_session=sys.platform != "win32",
        )
        timed_out = False
        cancelled = False
        try:
            while proc.poll() is None:
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    _stop_tree(proc)
                    break
                if time.monotonic() - start > timeout_s:
                    timed_out = True
                    _stop_tree(proc)
                    break
                time.sleep(0.04)
        except BaseException:
            _stop_tree(proc)
            raise
    return ProcessOutcome(proc.returncode, _tail(stdout_path), _tail(stderr_path),
                          round(time.monotonic()-start, 3), cancelled, timed_out)


class BlenderJobRunner:
    def __init__(self, blender_exe: Path, jobs_root: Path, worker_script: Path):
        self.blender_exe = Path(blender_exe)
        self.jobs_root = Path(jobs_root)
        self.worker_script = Path(worker_script)

    def run(self, job: JobRequest, *, timeout_s: float = 240,
            cancel: threading.Event | None = None,
            staged_inputs: dict[str, Path] | None = None) -> tuple[JobResult, Path]:
        """Execute staged Blender script. Never mutates the input master file."""
        if not self.blender_exe.is_file():
            raise WorkerFailure(f"Blender executable missing: {self.blender_exe}")
        if not self.worker_script.is_file():
            raise WorkerFailure("Bundled Blender bridge is missing")
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        if self.jobs_root.is_symlink():
            raise WorkerFailure("Jobs root cannot be symlink")
        output_dir = self.jobs_root / job.job_id
        try:
            output_dir.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise WorkerFailure("Job ID already exists; refusing to overwrite evidence") from exc
        for rel_name, source in (staged_inputs or {}).items():
            rel = safe_relative_path(rel_name, "staged input")
            source = Path(source)
            if source.is_symlink() or not source.is_file():
                raise WorkerFailure("Staged source must be a real local file")
            target = (output_dir / rel).resolve(strict=False)
            if not target.is_relative_to(output_dir.resolve(strict=True)):
                raise WorkerFailure("Staged input escaped job workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise WorkerFailure("Duplicate staged input path")
            shutil.copy2(source, target)
        if job.input_project and not (output_dir / job.input_project).is_file():
            raise WorkerFailure("Required input_project was not staged")
        request = output_dir / "request.json"
        result = output_dir / "result.json"
        payload = json.dumps(job.as_dict(), ensure_ascii=False, allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise WorkerFailure("Job too large")
        request.write_text(payload, encoding="utf-8")
        command = [str(self.blender_exe), "--background", "--disable-autoexec", "--python",
                   str(self.worker_script.resolve()), "--", "--request", str(request.resolve()),
                   "--result", str(result.resolve()), "--workspace", str(output_dir.resolve())]
        try:
            outcome = run_process(command, output_dir, timeout_s=timeout_s, cancel=cancel)
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkerFailure(f"Could not launch Blender: {exc}; staged evidence: {output_dir}") from exc
        if outcome.cancelled:
            raise WorkerFailure(f"Job cancelled; staged logs: {output_dir}")
        if outcome.timed_out:
            raise WorkerFailure(f"Blender timed out; staged logs: {output_dir}")
        if outcome.return_code != 0:
            # The Blender bridge catches runtime exceptions and writes a
            # versioned JSON error, even when Blender exits nonzero. Surface
            # that actionable cause rather than only an empty stderr tail.
            error_detail = ""
            try:
                if (result.is_file() and not result.is_symlink() and
                        result.stat().st_size <= MAX_REQUEST_BYTES):
                    failure = JobResult.from_dict(
                        json.loads(result.read_text(encoding="utf-8"))
                    )
                    if (failure.job_id == job.job_id and
                            failure.operation == job.operation and
                            failure.status == "error"):
                        error_detail = str(failure.error)[:1000]
            except (OSError, ValueError, TypeError):
                pass
            raise WorkerFailure(
                f"Blender failed ({outcome.return_code}): {error_detail}; "
                f"{outcome.stderr_tail[-500:]}; staged logs: {output_dir}"
            )
        if not result.is_file() or result.stat().st_size > MAX_REQUEST_BYTES:
            raise WorkerFailure("Worker reported success but result was missing/oversized")
        try:
            info = JobResult.from_dict(json.loads(result.read_text(encoding="utf-8")))
        except (ValueError, TypeError, OSError) as exc:
            raise WorkerFailure(f"Invalid worker result: {exc}") from exc
        if info.job_id != job.job_id or info.operation != job.operation:
            raise WorkerFailure("Worker result job/operation mismatch")
        if info.status != "ok":
            raise WorkerFailure(f"Blender reported error: {info.error}")
        return info, output_dir
