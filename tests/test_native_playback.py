"""Coordinator fault injection with clearly synthetic bytes, not Blender proof."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.motion_skin_contract import write_cache,file_record
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.native_body import NativeBodyPreview
from ucc.jobs.native_playback import prepare_native_playback
from ucc.library.provenance import AssetPolicyError,LicensePolicy
from ucc.preview.motion_cache import read_motion_cache


class PlaybackCoordinatorTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.store=ProjectStore(self.root/"hero");self.store.save(CharacterProject.new("Playback unit fixture"))
        master=self.root/"unit-not-real.blend";master.write_bytes(b"BLENDER"+b"UNIT_ONLY"*2000)
        staged=stage_unverified_master(self.store,master,authorized_source_root=self.root)
        self.master=staged.master_path;self.project=staged.project
        self.folder=self.store.root/".ucc-jobs"/"original-unit-job";self.folder.mkdir(parents=True)
        _,_,_,self.timeline=write_cache(self.folder)
        self.source=self.root/"unit.fbx";self.source.write_bytes(b"NOT_AN_FBX_UNIT_ONLY")
        for name in ("source_snapshot.json","native_mapping.json"):(self.folder/name).write_text("{}")
        (self.folder/"target_timeline.json").write_text(json.dumps(self.timeline))
        (self.folder/"review_motion.blend").write_bytes(b"NOT_A_REAL_SAVED_ANIMATION")
        self.digest=lambda p:sha256(p.read_bytes()).hexdigest()
        self.bindings={"master_sha256":self.digest(self.master),"source_sha256":self.digest(self.source),
            "snapshot_sha256":self.digest(self.folder/"source_snapshot.json"),"mapping_sha256":self.digest(self.folder/"native_mapping.json")}
        report={"bindings":self.bindings,"timeline":file_record(self.folder/"target_timeline.json"),"visual_review_blend":file_record(self.folder/"review_motion.blend")}
        self.preview=NativeBodyPreview(self.project.project_id,self.project.revision,self.bindings["master_sha256"],
            self.bindings["source_sha256"],self.timeline,str(self.folder/"review_motion.blend"),"",str(self.folder/"target_timeline.json"),
            ("unit-one","unit-two"),str(self.folder/"native_mapping.json"),report)
        self.policy=LicensePolicy("original","CC0","original-unit://cache",reviewed=True,local_preview_allowed=True,no_ai=True)
        self.cancel=Event();self.fault=None;self.runs=0

    def prepare(self,**overrides):
        def worker(request,**kwargs):
            self.runs+=1;self.assertEqual(request.operation,"cache_native_fbx_body");self.assertIs(kwargs["cancel"],self.cancel)
            output=self.store.root/".ucc-jobs"/request.job_id;output.mkdir()
            for name,path in kwargs["staged_inputs"].items():(output/name).write_bytes(path.read_bytes())
            data,report,_,_=write_cache(output)
            data["bindings"]=dict(request.options);report["bindings"]=dict(request.options)
            report["saved_review_verification"]["bindings"]=dict(request.options)
            manifest=output/"motion_skin.json";manifest.write_text(json.dumps(data));report["manifest"]=file_record(manifest)
            if self.fault=="source":self.source.write_bytes(b"EXTERNAL_CHANGE")
            if self.fault=="staged":(output/"candidate.blend").write_bytes(b"CORRUPTED")
            if self.fault=="cancel":self.cancel.set()
            if self.fault=="revision":self.store.save(replace(self.store.load(),revision=self.project.revision+1))
            if self.fault=="reopen":report["saved_review_verification"]["frames_verified"]=2
            if self.fault=="geometry":(output/"motion_skin.bin").write_bytes(b"CORRUPTED")
            return SimpleNamespace(details=report),output
        def cache(*args,**kwargs):
            result=read_motion_cache(*args,**kwargs)
            if self.fault=="late_revision":self.store.save(replace(self.store.load(),revision=self.project.revision+1))
            return result
        with patch("ucc.jobs.native_playback.read_native_profile",return_value=({"skin_deformation_policy":"BOUND_CORRECTIVE_SMOOTH_V1"},self.bindings["mapping_sha256"])),\
             patch("ucc.jobs.native_playback.validate_snapshot"),\
             patch("ucc.jobs.native_playback.read_native_timeline",return_value=(self.timeline,self.folder/"target_timeline.json")),\
             patch("ucc.jobs.native_playback.BlenderJobRunner") as runner,\
             patch("ucc.jobs.native_playback.read_motion_cache",side_effect=cache):
            runner.return_value.run.side_effect=worker
            return prepare_native_playback(self.store,self.preview,source_fbx=self.source,
                permission=overrides.get("permission",self.policy),blender_exe=self.root/"unit-exe",worker_script=self.root/"unit-worker",cancel=self.cancel)

    def test_complete_private_cache_publishes_without_changing_project(self):
        master=self.master.read_bytes();project=self.store.load();result=self.prepare()
        self.assertEqual(result.cache.frame_count,3);self.assertEqual(result.source_sha256,self.bindings["source_sha256"])
        self.assertEqual(self.runs,1);self.assertEqual(self.master.read_bytes(),master);self.assertEqual(self.store.load(),project)

    def test_source_staged_cancel_revision_reopen_and_geometry_faults_never_publish(self):
        for fault in ("source","staged","cancel","revision","reopen","geometry","late_revision"):
            with self.subTest(fault=fault):
                self.setUp();self.fault=fault
                with self.assertRaises((ProjectStorageError,ProjectConflict,ValidationError)):self.prepare()
                self.assertEqual(self.digest(self.master),self.bindings["master_sha256"])

    def test_license_denial_cancel_and_stale_preview_do_not_start_worker(self):
        denied=LicensePolicy("original","unknown","original-unit://cache")
        with self.assertRaises(AssetPolicyError):self.prepare(permission=denied)
        self.assertEqual(self.runs,0);self.cancel.set()
        with self.assertRaises(ProjectStorageError):self.prepare()
        self.cancel.clear();self.preview=replace(self.preview,revision=self.preview.revision+1)
        with self.assertRaises(ProjectConflict):self.prepare()
        self.assertEqual(self.runs,0)
