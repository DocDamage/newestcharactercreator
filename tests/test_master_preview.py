"""Master-preview orchestration tests; synthetic GLB is NOT character art."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.master_preview import preview_saved_master
from ucc.jobs.protocol import JobResult
from ucc.preview.glb_mesh import PreviewError


def write_synthetic_triangle_glb(path: Path) -> None:
    """One test-only embedded triangle to exercise real GLB parsing."""
    verts = b"".join(struct.pack("<fff", *p) for p in (
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
    ))
    indices = struct.pack("<HHH", 0, 1, 2)
    data = verts + indices + (b"\x00" * 2)
    doc = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(data)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(verts)},
            {"buffer": 0, "byteOffset": len(verts), "byteLength": len(indices)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [
            {"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}
        ]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    info = json.dumps(doc, separators=(",", ":")).encode()
    info += b" " * (-len(info) % 4)
    payload = (struct.pack("<I4s", len(info), b"JSON") + info +
               struct.pack("<I4s", len(data), b"BIN\x00") + data)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(payload)) + payload)


class MasterPreviewContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ProjectStore(self.root / "hero")
        self.store.save(CharacterProject.new("A human"))
        staging = self.root / "test-staged-worker"
        staging.mkdir()
        source = staging / "generated_human.blend"
        source.write_bytes(b"BLENDER" + b"contract-only" * 120)
        version = stage_unverified_master(
            self.store, source, authorized_source_root=staging
        )
        self.saved = version.project
        self.master = version.master_path
        self.blender = self.root / "test-blender"
        self.script = self.root / "test-bridge.py"
        self.blender.write_text("not real Blender", encoding="utf-8")
        self.script.write_text("unit test only", encoding="utf-8")
        self.cancel = Event()
        self.operations = []

    def response(self, job, **kwargs):
        self.operations.append(job.operation)
        folder = self.store.root / ".ucc-jobs" / job.job_id
        folder.mkdir(parents=True)
        (folder / "candidate.blend").write_bytes(
            kwargs["staged_inputs"]["candidate.blend"].read_bytes()
        )
        write_synthetic_triangle_glb(folder / "preview.glb")
        details = {
            "staged_glb": "preview.glb", "selected_mesh_count": 1,
            "selected_vertex_count": 19000, "blender_version": "5.3.0",
            "static_only": True, "evaluated_geometry_baked": True,
            "textures_included": False,
            "animation_exported": False, "skinning_exported": False,
            "engine_import_verified": False,
        }
        return JobResult(job.job_id, job.operation, "ok", details), folder

    def invoke(self, **changes):
        options = {
            "blender_exe": self.blender, "worker_script": self.script,
            "expected_project_id": self.saved.project_id,
            "expected_revision": self.saved.revision,
            "expected_master_blend": self.saved.master_blend,
            "cancel": self.cancel,
        }
        options.update(changes)
        with patch("ucc.jobs.master_preview.BlenderJobRunner.run",
                   side_effect=self.response):
            return preview_saved_master(self.store, **options)

    def test_actual_triangle_reader_and_no_project_mutation(self):
        before = self.store.file.read_bytes()
        original_master = self.master.read_bytes()
        result = self.invoke()
        self.assertEqual(self.operations, ["export_preview_glb"])
        self.assertEqual(result.mesh.source_face_count, 1)
        self.assertEqual(result.mesh.sample_count, 1)
        self.assertEqual(result.revision, self.saved.revision)
        self.assertEqual(result.master_blend, self.saved.master_blend)
        self.assertEqual(result.selected_vertex_count, 19000)
        self.assertFalse(result.certified_for_engine_import)
        self.assertEqual(self.store.file.read_bytes(), before)
        self.assertEqual(self.master.read_bytes(), original_master)

    def test_reject_stale_project_before_blender_is_started(self):
        with self.assertRaises(ProjectConflict):
            self.invoke(expected_revision=15)
        with self.assertRaises(ProjectConflict):
            self.invoke(expected_project_id="different")
        with self.assertRaises(ProjectConflict):
            self.invoke(expected_master_blend="master/versions/" + "0" * 64 + ".blend")
        self.assertEqual(self.operations, [])

    def test_tampered_content_address_rejected(self):
        self.master.write_bytes(b"BLENDER" + b"changed" * 200)
        with self.assertRaisesRegex(ProjectStorageError, "digest mismatch"):
            self.invoke()
        self.assertEqual(self.operations, [])

    def test_reject_missing_master(self):
        self.master.unlink()
        with self.assertRaisesRegex(ProjectStorageError, "missing"):
            self.invoke()
        self.assertEqual(self.operations, [])

    def test_cancellation_before_export_and_after_export(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.invoke()
        self.assertEqual(self.operations, [])
        self.cancel.clear()

        def cancelled_after(job, **kwargs):
            outcome = self.response(job, **kwargs)
            self.cancel.set()
            return outcome
        with patch("ucc.jobs.master_preview.BlenderJobRunner.run",
                   side_effect=cancelled_after):
            with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
                preview_saved_master(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend, cancel=self.cancel,
                )
        self.assertEqual(self.store.load(), self.saved)

    def test_external_revision_change_prevents_stale_preview(self):
        def changed(job, **kwargs):
            outcome = self.response(job, **kwargs)
            old = self.store.load()
            self.store.save(replace(old, revision=old.revision + 1,
                                    name="Saved by other editor"),
                            expected_revision=old.revision)
            return outcome
        with patch("ucc.jobs.master_preview.BlenderJobRunner.run",
                   side_effect=changed):
            with self.assertRaisesRegex(ProjectConflict, "changed during preview"):
                preview_saved_master(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )
        self.assertEqual(self.store.load().name, "Saved by other editor")

    def test_invalid_worker_flags_do_not_certify(self):
        def incorrect(job, **kwargs):
            response, folder = self.response(job, **kwargs)
            return replace(response, details={**response.details,
                                              "engine_import_verified": True}), folder
        with patch("ucc.jobs.master_preview.BlenderJobRunner.run", side_effect=incorrect):
            with self.assertRaisesRegex(ProjectStorageError, "unsafe evidence"):
                preview_saved_master(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )

    def test_invalid_glb_does_not_modify_master(self):
        before = self.store.file.read_bytes()
        def corrupt(job, **kwargs):
            response, folder = self.response(job, **kwargs)
            (folder / "preview.glb").write_bytes(b"not gltf" * 10)
            return response, folder
        with patch("ucc.jobs.master_preview.BlenderJobRunner.run", side_effect=corrupt):
            with self.assertRaises(PreviewError):
                preview_saved_master(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )
        self.assertEqual(self.store.file.read_bytes(), before)

    def test_invalid_executable_and_worker_fail_closed(self):
        with self.assertRaises(ValidationError):
            self.invoke(blender_exe=self.root / "not-here")
        with self.assertRaises(ValidationError):
            self.invoke(worker_script=self.root / "not-here")
        self.assertEqual(self.operations, [])

    def test_symlinked_jobs_root_rejected(self):
        destination = self.root / "outside"
        destination.mkdir()
        jobs = self.store.root / ".ucc-jobs"
        try:
            jobs.symlink_to(destination, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(ProjectStorageError, "redirected"):
            self.invoke()
        self.assertEqual(list(destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
