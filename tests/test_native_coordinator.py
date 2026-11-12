"""Native orchestration fault injection; these bytes are never Blender evidence."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Event
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.native_body_contract import contract
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.native_body import preview_native_body
from ucc.library.provenance import AssetPolicyError, LicensePolicy


class NativeCoordinatorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = ProjectStore(self.root / "hero")
        self.store.save(CharacterProject.new("Native orchestration unit fixture"))
        source_master = self.root / "not-real.blend"
        source_master.write_bytes(b"BLENDER" + b"UNIT_ONLY"*2000)
        stage = stage_unverified_master(self.store, source_master, authorized_source_root=self.root)
        self.project, self.master = stage.project, stage.master_path
        self.metadata = self.store.root / "project.ucc.json"
        self.source = self.root / "unit.fbx"
        self.source.write_bytes(b"NOT_AN_FBX_COORDINATOR_UNIT_ONLY")
        self.snapshot = self.root / "source_snapshot.json"
        self.snapshot.write_text("{}")
        self.profile = self.root / "body-map.json"
        self.profile.write_text("{}")
        self.cancel = Event()
        self.runs = 0
        self.fault = None
        self.corrective = False
        self.before = (self.source.read_bytes(), self.master.read_bytes(), self.metadata.read_bytes())
        self.policy = LicensePolicy("original", "CC0", "local-original://unit", reviewed=True,
                                    local_preview_allowed=True, no_ai=True)

    def run_preview(self, **overrides):
        data, _, source, profile, _ = contract()
        if self.corrective:profile["skin_deformation_policy"]="BOUND_CORRECTIVE_SMOOTH_V1"
        timeline_path=self.root/"target_timeline.json";timeline_path.write_text("{}")
        review_path=self.root/"review_motion.blend";review_path.write_bytes(b"SYNTHETIC_ORCHESTRATION_ONLY")
        def digest(path): return sha256(path.read_bytes()).hexdigest()
        def worker(request, **kwargs):
            self.runs += 1
            self.assertIs(kwargs["cancel"],self.cancel)
            folder = self.store.root / ".ucc-jobs" / request.job_id
            folder.mkdir(parents=True)
            for name, path in kwargs["staged_inputs"].items():
                (folder / name).write_bytes(path.read_bytes())
            if request.operation=="reopen_native_fbx_body":
                from ucc.jobs.runner import WorkerFailure
                if self.fault=="reopen_fail":raise WorkerFailure("Actual-scene reopen failed (synthetic boundary injection)")
                if self.fault=="reopen_staged":(folder/"review_motion.blend").write_bytes(b"TAMPERED")
                if self.fault=="reopen_cancel":self.cancel.set()
                result={"status":"REAL_NATIVE_BODY_REVIEW_REOPENED","bindings":dict(request.options),
                    "frames_verified":4 if self.fault=="reopen_count" else 5,"uncorrected_skin_frames_verified":5,
                    "master_strain_frames_verified":5,"hip_frames_verified":0,"skin_deformation_policy":"BOUND_CORRECTIVE_SMOOTH_V1",
                    "original_master_unchanged":True,"review_unchanged":True,"retargeting_verified":False,
                    "animation_visual_quality_verified":False,"engine_import_verified":False}
                return SimpleNamespace(details=result),folder
            if self.fault == "source": self.source.write_bytes(b"SOURCE_CHANGED")
            if self.fault == "staged": (folder / "candidate.blend").write_bytes(b"TAMPERED")
            if self.fault == "cancel": self.cancel.set()
            if self.fault == "stale": self.store.save(replace(self.store.load(), revision=self.project.revision+1))
            result = {"private_review_renders": {} if self.runs == 1 else None,
                      "timeline": {"sha256":digest(timeline_path)}, "visual_review_blend": {"sha256":digest(review_path)}}
            return SimpleNamespace(details=result), folder
        def evidence(*args, **kwargs):
            value = deepcopy(data)
            if self.fault == "disagree" and self.runs == 2:
                value["full_timeline_frames"][-1]["evaluated_sha256"] = "f"*64
            return value, self.root / "target_timeline.json"
        render_calls=[0]
        def render(*args):
            render_calls[0]+=1
            if self.fault=="late_render" and render_calls[0]==2:raise ValidationError("Private render changed during saved-copy reopen")
            return str(self.root/"index.html")
        intake = {"private_snapshot": str(self.snapshot), "source_sha256": digest(self.source),
                  "snapshot": {"sha256": digest(self.snapshot)}}
        options = dict(source_fbx=self.source, mapping_profile=self.profile, blender_exe=self.root/"unused",
                       worker_script=self.root/"unused.py", permission=self.policy, cancel=self.cancel,
                       expected_project_id=self.project.project_id, expected_revision=self.project.revision,
                       expected_master_blend=self.project.master_blend)
        options.update(overrides)
        with (patch("ucc.jobs.native_body.inspect_selected_fbx", return_value=intake) as inspect,
              patch("ucc.jobs.native_body.read_snapshot", return_value=(source, self.snapshot)),
              patch("ucc.jobs.native_body.read_native_profile", return_value=(profile, digest(self.profile))),
              patch("ucc.jobs.native_body.BlenderJobRunner.run", side_effect=worker),
              patch("ucc.jobs.native_body.read_native_timeline", side_effect=evidence),
              patch("ucc.jobs.native_body.bound_file", return_value=self.root/"review_motion.blend"),
              patch("ucc.jobs.native_body.verify_native_renders", side_effect=render)):
            result = preview_native_body(self.store, **options)
            self.assertEqual(inspect.call_count, 1)
            return result

    def test_two_workers_preserve_all_original_bytes_and_never_promote_project(self):
        result = self.run_preview()
        self.assertEqual(self.runs, 2)
        self.assertEqual(len(set(result.worker_job_ids)), 2)
        self.assertFalse(result.retargeting_verified)
        self.assertEqual(self.store.load(), self.project)
        self.assertEqual(self.before, (self.source.read_bytes(), self.master.read_bytes(), self.metadata.read_bytes()))

    def test_cancel_and_stale_revision_reject_before_import(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"): self.run_preview()
        self.cancel.clear()
        with self.assertRaises(ProjectConflict): self.run_preview(expected_revision=99)
        self.assertEqual(self.runs, 0)

    def test_mutation_cancel_and_independent_worker_disagreement_reject(self):
        for fault, exception in (("source", ProjectStorageError), ("staged", ProjectStorageError),
                                 ("cancel", ProjectStorageError), ("stale", ProjectConflict),
                                 ("disagree", ValidationError)):
            with self.subTest(fault=fault):
                self.setUp()
                self.fault = fault
                with self.assertRaises(exception): self.run_preview()
                self.assertEqual(self.master.read_bytes(), self.before[1])

    def test_unreviewed_license_rejects_before_any_import(self):
        with self.assertRaises(AssetPolicyError):
            self.run_preview(permission=LicensePolicy("unknown", "unknown", "local://unknown"))
        self.assertEqual(self.runs, 0)

    def test_corrective_policy_requires_successful_third_process_and_preserves_originals(self):
        self.corrective=True
        result=self.run_preview()
        self.assertEqual(self.runs,3)
        self.assertTrue(result.private_reopen_job_id)
        self.assertNotIn(result.private_reopen_job_id,result.worker_job_ids)
        self.assertEqual(result.reopen_evidence["uncorrected_skin_frames_verified"],5)
        self.assertEqual(self.before,(self.source.read_bytes(),self.master.read_bytes(),self.metadata.read_bytes()))

    def test_reopen_failure_tamper_incomplete_report_or_cancel_never_publishes_success(self):
        from ucc.jobs.runner import WorkerFailure
        for fault,error in (("reopen_fail",WorkerFailure),("reopen_staged",ProjectStorageError),
                            ("reopen_count",ValidationError),("reopen_cancel",ProjectStorageError),("late_render",ValidationError)):
            with self.subTest(fault=fault):
                self.setUp();self.corrective=True;self.fault=fault
                with self.assertRaises(error):self.run_preview()
                self.assertEqual(self.runs,3)
                self.assertEqual(self.before,(self.source.read_bytes(),self.master.read_bytes(),self.metadata.read_bytes()))
