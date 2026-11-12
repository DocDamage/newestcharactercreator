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
        self.before = (self.source.read_bytes(), self.master.read_bytes(), self.metadata.read_bytes())
        self.policy = LicensePolicy("original", "CC0", "local-original://unit", reviewed=True,
                                    local_preview_allowed=True, no_ai=True)

    def run_preview(self, **overrides):
        data, _, source, profile, _ = contract()
        def digest(path): return sha256(path.read_bytes()).hexdigest()
        def worker(request, **kwargs):
            self.runs += 1
            folder = self.store.root / ".ucc-jobs" / request.job_id
            folder.mkdir(parents=True)
            for name, path in kwargs["staged_inputs"].items():
                (folder / name).write_bytes(path.read_bytes())
            if self.fault == "source": self.source.write_bytes(b"SOURCE_CHANGED")
            if self.fault == "staged": (folder / "candidate.blend").write_bytes(b"TAMPERED")
            if self.fault == "cancel": self.cancel.set()
            if self.fault == "stale": self.store.save(replace(self.store.load(), revision=self.project.revision+1))
            result = {"private_review_renders": {} if self.runs == 1 else None,
                      "timeline": {}, "visual_review_blend": {}}
            return SimpleNamespace(details=result), folder
        def evidence(*args, **kwargs):
            value = deepcopy(data)
            if self.fault == "disagree" and self.runs == 2:
                value["full_timeline_frames"][-1]["evaluated_sha256"] = "f"*64
            return value, self.root / "target_timeline.json"
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
              patch("ucc.jobs.native_body.verify_native_renders", return_value=str(self.root/"index.html"))):
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
