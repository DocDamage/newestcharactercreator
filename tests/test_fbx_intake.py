"""Synthetic native FBX boundary tests; genuine import is a separate Blender gate."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from threading import Event
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blender_bridge.fbx_source import matrix_values, FbxSourceError, inspect_fbx_source
from fixtures.fbx_snapshot_contract import snapshot, report, IDENTITY
from ucc.animations.fbx_snapshot import validate_snapshot, read_snapshot
from ucc.core.errors import ValidationError
from ucc.jobs.fbx_intake import inspect_selected_fbx
from ucc.jobs.protocol import JobRequest, JobResult
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import LicensePolicy, AssetPolicyError


class FbxSnapshotTests(unittest.TestCase):
    def test_complete_multiroot_armature_object_motion_is_preserved(self):
        data=snapshot()
        measured=validate_snapshot(data,"a"*64)
        self.assertEqual((measured["root_count"],measured["frame_count"]),(2,4))
        self.assertNotEqual(data["frames"][0]["pose_sha256"],data["frames"][-1]["pose_sha256"])
        self.assertEqual(data["frames"][0]["poses"],data["frames"][-1]["poses"])

    def test_bad_binding_bounds_convention_flags_and_import_options_reject(self):
        for key,value in (("source_sha256","b"*64),("convention","BVH"),("schema_version",True),
                          ("retargeting_verified",True),("fps",float("nan")),("last_frame",2401),
                          ("action","bad\ncontrol"),("import_options",{}),("rest_import_options",{}),("extra",True)):
            data=snapshot(); data[key]=value
            with self.subTest(key=key), self.assertRaises(ValidationError): validate_snapshot(data,"a"*64)

    def test_missing_frames_parents_duplicate_names_rest_and_final_pose_tamper_reject(self):
        for case in ("missing","order","parent","name","rest","tail","rest_world","pose","matrix","reflection","shear","stationary"):
            data=snapshot()
            if case=="missing":data["frames"].pop()
            if case=="order":data["frames"][-1]["frame"]=3
            if case=="parent":data["bones"][0]["parent"]="Child"
            if case=="name":data["bones"][1]["name"]="roota"
            if case=="rest":data["bones"][0]["head"][0]=.1
            if case=="tail":data["bones"][0]["tail"]=[1.,0.,0.]
            if case=="rest_world":data["armature_rest_world"][0]=-1.
            if case=="pose":data["frames"][-1]["poses"][-1][3]=.1
            if case=="matrix":data["frames"][-1]["armature_world"][15]=0.
            if case=="reflection":data["bones"][0]["matrix"][0]=-1.
            if case=="shear":data["bones"][0]["matrix"][1]=.1
            if case=="stationary":
                for i in range(1,4): data["frames"][i]={**deepcopy(data["frames"][0]),"frame":i+1}
            with self.subTest(case=case),self.assertRaises(ValidationError):validate_snapshot(data,"a"*64)

    def test_worker_matrix_checks_reject_nonfinite_reflection_and_shear(self):
        for index,value in ((0,-1.),(0,0.),(1,.2),(3,float("inf")),(15,0.)):
            v=IDENTITY[:];v[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(FbxSourceError):
                matrix_values([v[i:i+4] for i in range(0,16,4)])

    def test_snapshot_file_hash_and_rehashed_malformed_json_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);data=snapshot();payload=json.dumps(data).encode();r=report(data,payload)
            path=folder/"source_snapshot.json";path.write_bytes(payload)
            self.assertEqual(read_snapshot(folder,r,"a"*64)[0],data)
            path.write_bytes(payload+b" ")
            with self.assertRaises(ValidationError):read_snapshot(folder,r,"a"*64)
            for bad in (b'{"schema_version":1,"schema_version":1}',b'NaN',b'\xff',b'['*2000+b'0'+b']'*2000):
                path.write_bytes(bad);r=report(data,bad)
                with self.assertRaises(ValidationError):read_snapshot(folder,r,"a"*64)

    def test_protocol_no_master_no_paths_no_options_except_sha(self):
        JobRequest.new("inspect_fbx_animation",options={"source_sha256":"a"*64})
        for options in ({},{"source_sha256":True},{"source_sha256":"A"*64},{"source_sha256":"a"*64,"path":"../source.fbx"}):
            with self.assertRaises(ValidationError):JobRequest.new("inspect_fbx_animation",options=options)
        with self.assertRaises(ValidationError):JobRequest.new("inspect_fbx_animation",input_project="master.blend",options={"source_sha256":"a"*64})

    def test_external_image_loader_is_blocked_and_restored_even_when_import_fails(self):
        loader=lambda *a,**kw: self.fail("External image read must never happen")
        image_utils=SimpleNamespace(load_image=loader)
        def import_fbx(**kwargs): image_utils.load_image("../../outside.png")
        bpy=SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(read_factory_settings=lambda **kw:None),
                                              import_scene=SimpleNamespace(fbx=import_fbx)))
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"source.fbx";source.write_bytes(b"SYNTHETIC_NOT_FBX")
            with patch.dict("sys.modules",{"bpy_extras":SimpleNamespace(image_utils=image_utils)}):
                with self.assertRaisesRegex(FbxSourceError,"image resources"):
                    inspect_fbx_source(bpy,source,Path(temp)/"out.json",sha256(source.read_bytes()).hexdigest())
            self.assertIs(image_utils.load_image,loader)
            self.assertFalse((Path(temp)/"out.json").exists())


class FbxCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/"original.fbx"
        self.source.write_bytes(b"SYNTHETIC_COORDINATOR_NOT_FBX")
        self.original=self.source.read_bytes();self.runs=0;self.fault=None
        self.policy=LicensePolicy("original","CC0","local-original://fixture",reviewed=True,local_preview_allowed=True,no_ai=True)

    def run_worker(self,job,**kwargs):
        self.runs+=1
        folder=self.root/job.job_id;folder.mkdir()
        (folder/"source.fbx").write_bytes(self.original)
        data=snapshot();data["source_sha256"]=sha256(self.original).hexdigest()
        if self.fault=="disagree" and self.runs==2:data["action"]="Another action"
        payload=json.dumps(data).encode();(folder/"source_snapshot.json").write_bytes(payload)
        r=report(data,payload)
        if self.fault=="source":self.source.write_bytes(b"changed")
        if self.fault=="staged":(folder/"source.fbx").write_bytes(b"changed")
        if self.fault=="artifact":(folder/"source_snapshot.json").write_bytes(payload+b"tamper")
        if self.runs==1:self.first_folder=folder
        if self.fault=="first_artifact" and self.runs==2:
            (self.first_folder/"source_snapshot.json").write_bytes(b"changed")
        return JobResult(job.job_id,job.operation,"ok",r),folder

    def invoke(self,**kwargs):
        return inspect_selected_fbx(self.source,blender_exe=Path("unused"),worker_script=Path("unused"),
                                    jobs_root=self.root/".ucc-jobs",permission=self.policy,**kwargs)

    def test_two_processes_agree_and_original_retained(self):
        with patch("ucc.jobs.fbx_intake.BlenderJobRunner.run",side_effect=self.run_worker):result=self.invoke()
        self.assertEqual(self.runs,2);self.assertTrue(result["two_workers_agree"])
        self.assertEqual(self.source.read_bytes(),self.original)

    def test_unreviewed_ue_only_and_cancellation_prevent_launch(self):
        for field in ("reviewed","ue_only","local_preview_allowed"):
            self.policy=LicensePolicy("original","CC0","local://fixture",reviewed=field!="reviewed",
                                      ue_only=field=="ue_only",local_preview_allowed=field!="local_preview_allowed")
            with self.assertRaises(AssetPolicyError):self.invoke()
        self.policy=LicensePolicy("original","CC0","local://fixture",reviewed=True,local_preview_allowed=True)
        cancel=Event();cancel.set()
        with self.assertRaises(WorkerFailure):self.invoke(cancel=cancel)

    def test_source_staging_snapshot_tamper_and_worker_disagreement_reject(self):
        for fault in ("source","staged","artifact","disagree","first_artifact"):
            with self.subTest(fault=fault):
                self.fault=fault
                self.runs=0
                with patch("ucc.jobs.fbx_intake.BlenderJobRunner.run",side_effect=self.run_worker),self.assertRaises(ValidationError):self.invoke()
                self.source.write_bytes(self.original)
