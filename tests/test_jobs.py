import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.core.errors import ValidationError
from ucc.jobs.protocol import JobRequest, JobResult
from ucc.jobs.runner import WorkerFailure, BlenderJobRunner, run_process, ProcessOutcome


class WorkerProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        req = JobRequest.new("inspect_environment")
        self.assertEqual(JobRequest.from_dict(json.loads(json.dumps(req.as_dict()))), req)
        reply = JobResult(req.job_id, req.operation, "ok", {"mpfb_registered": False})
        self.assertEqual(JobResult.from_dict(reply.as_dict()), reply)

    def test_unknown_command_fails(self):
        with self.assertRaises(ValidationError):
            JobRequest.new("arbitrary_code")

    def test_preview_glb_needs_staged_blend_and_rejects_unsafe_options(self):
        with self.assertRaisesRegex(ValidationError, "input_project"):
            JobRequest.new("export_preview_glb")
        with self.assertRaisesRegex(ValidationError, "fixed"):
            JobRequest.new("export_preview_glb", input_project="candidate.blend",
                           options={"include_textures": True})
        request = JobRequest.new("export_preview_glb", input_project="candidate.blend")
        self.assertEqual(JobRequest.from_dict(request.as_dict()), request)
        with self.assertRaises(ValidationError):
            JobRequest.new("export_preview_glb", input_project="../escape.blend")

    def test_request_cannot_traverse_or_run_arbitrary_code(self):
        for bad in ("../../user.blend", "C:/user.blend", "\\\\server\\file.blend"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                JobRequest.new("inspect_character", input_project=bad)
        with self.assertRaises(ValidationError):
            JobRequest.new("create_human", options={"execute_python": "dangerous"})

    def test_json_nan_or_large_data_fails(self):
        with self.assertRaises(ValidationError):
            JobRequest.new("inspect_environment", options={"x": float("nan")})
        with self.assertRaises(ValidationError):
            JobRequest.new("inspect_environment", options={"x": "a" * 300000})

    def test_error_result_needs_message_and_uuid(self):
        with self.assertRaises(ValidationError):
            JobResult("bad-id", "inspect_environment", "ok", {})
        with self.assertRaises(ValidationError):
            JobResult(str(uuid4()), "create_human", "error", {}, error=None)


class SubprocessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_stdout_stderr_bounded_and_result(self):
        command = [sys.executable, "-c", "import sys;print('good');print('bad',file=sys.stderr)"]
        out = run_process(command, self.root / "job", timeout_s=5)
        self.assertEqual(out.return_code, 0)
        self.assertIn("good", out.stdout_tail)
        self.assertIn("bad", out.stderr_tail)

    def test_timeout_terminates_process(self):
        command = [sys.executable, "-c", "import time;time.sleep(30)"]
        out = run_process(command, self.root / "timeout", timeout_s=.15)
        self.assertTrue(out.timed_out)
        self.assertNotEqual(out.return_code, 0)

    def test_pre_cancel_never_starts_process(self):
        cancel = threading.Event()
        cancel.set()
        out = run_process(["not-a-real-executable"], self.root / "cancel", cancel=cancel)
        self.assertTrue(out.cancelled)

    def test_late_cancel_kills_process(self):
        cancel = threading.Event()
        threading.Timer(.12, cancel.set).start()
        out = run_process([sys.executable, "-c", "import time;time.sleep(30)"],
                          self.root / "cancel-running", cancel=cancel, timeout_s=5)
        self.assertTrue(out.cancelled)

    def test_blender_job_refuses_missing_executable(self):
        fake = self.root / "missing-blender.exe"
        runner = BlenderJobRunner(fake, self.root / "jobs", self.root / "bridge.py")
        with self.assertRaises(WorkerFailure):
            runner.run(JobRequest.new("inspect_environment"))


class BlenderRunnerStagingTests(unittest.TestCase):
    """Protocol simulation only; NOT a Blender or MPFB integration test."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.blender = self.root / "fake-executable-placeholder-for-unit-test"
        self.script = self.root / "fake-worker-for-unit-test.py"
        self.blender.write_bytes(b"unit test executable marker")
        self.script.write_text("# not executed")
        self.runner = BlenderJobRunner(self.blender, self.root / "jobs", self.script)

    @staticmethod
    def protocol_only_result(job, directory):
        (directory / "result.json").write_text(json.dumps(
            JobResult(job.job_id, job.operation, "ok", {"test_only": True}).as_dict()))
        return ProcessOutcome(0, "", "", 0.1)

    def test_result_id_and_operation_are_checked(self):
        job = JobRequest.new("inspect_environment")
        def fake_process(command, workdir, **kwargs):
            (workdir / "result.json").write_text(json.dumps(
                JobResult(str(uuid4()), job.operation, "ok", {}).as_dict()))
            return ProcessOutcome(0, "", "", 0.1)
        with patch("ucc.jobs.runner.run_process", side_effect=fake_process):
            with self.assertRaisesRegex(WorkerFailure, "mismatch"):
                self.runner.run(job)

    def test_blender_failure_includes_matching_worker_error_response(self):
        job = JobRequest.new("inspect_environment")
        def failed(command, directory, **kwargs):
            (directory / "result.json").write_text(json.dumps(
                JobResult(job.job_id, job.operation, "error", {},
                          error="MPFB TargetService.reapply_macro_details failed").as_dict()
            ))
            return ProcessOutcome(2, "", "", 0.1)
        with patch("ucc.jobs.runner.run_process", side_effect=failed):
            with self.assertRaisesRegex(
                WorkerFailure, "TargetService.reapply_macro_details failed"
            ):
                self.runner.run(job)

    def test_blender_failure_does_not_trust_spoofed_worker_response(self):
        job = JobRequest.new("inspect_environment")
        def failed(command, directory, **kwargs):
            (directory / "result.json").write_text(json.dumps(
                JobResult(str(uuid4()), job.operation, "error", {},
                          error="Spoofed success!").as_dict()
            ))
            return ProcessOutcome(2, "", "Actual Blender failure", 0.1)
        with patch("ucc.jobs.runner.run_process", side_effect=failed):
            with self.assertRaises(WorkerFailure) as raised:
                self.runner.run(job)
        self.assertNotIn("Spoofed success!", str(raised.exception))
        self.assertIn("Actual Blender failure", str(raised.exception))

    def test_job_id_collision_does_not_overwrite(self):
        job = JobRequest.new("inspect_environment")
        with patch("ucc.jobs.runner.run_process", side_effect=lambda command, workdir, **kw: self.protocol_only_result(job, workdir)):
            result, folder = self.runner.run(job)
            self.assertEqual(result.job_id, job.job_id)
            original = (folder / "request.json").read_bytes()
            with self.assertRaisesRegex(WorkerFailure, "already exists"):
                self.runner.run(job)
            self.assertEqual((folder / "request.json").read_bytes(), original)

    def test_inspect_character_requires_staging(self):
        job = JobRequest.new("inspect_character", input_project="master/human.blend")
        with self.assertRaisesRegex(WorkerFailure, "not staged"):
            self.runner.run(job)

    def test_staging_copies_not_edits_the_original(self):
        job = JobRequest.new("inspect_character", input_project="master/human.blend")
        original = self.root / "original.blend"
        original.write_bytes(b"BLENDER" + b"\x00" * 200)
        def simulated(command, directory, **kwargs):
            self.assertEqual((directory / "master/human.blend").read_bytes(), original.read_bytes())
            return self.protocol_only_result(job, directory)
        with patch("ucc.jobs.runner.run_process", side_effect=simulated):
            result, folder = self.runner.run(job, staged_inputs={"master/human.blend": original})
            self.assertEqual(result.status, "ok")
            self.assertEqual(original.read_bytes(), b"BLENDER" + b"\x00" * 200)
            self.assertNotEqual(folder, original.parent)
