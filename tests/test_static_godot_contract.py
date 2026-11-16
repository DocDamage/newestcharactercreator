"""Per-use engine rights and destination no-replace tests, not asset approval."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.library.provenance import AssetPolicyError
from ucc.export.static_godot_contract import StaticGodotRequest
from ucc.jobs.export_destination import plan_destination,rename_new
from fixtures.godot_export_logic import request


class StaticExportRequestTests(unittest.TestCase):
    def test_closed_roundtrip_and_no_scope_or_approval_upgrade(self):
        original=request();self.assertEqual(StaticGodotRequest.from_dict(original.to_dict()),original)
        for key,value in [('engine_minor',8),('animation_clips',True),('distribution_license_review_complete',True),('extra',True)]:
            raw=deepcopy(original.to_dict());raw[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):StaticGodotRequest.from_dict(raw)

    def test_each_exact_source_needs_reviewed_non_UE_only_NoAI_permission(self):
        original=request();permission=original.permissions[0]
        for change in [{'reviewed':False},{'ue_only':True},{'no_ai':False},{'ai_input_allowed':True},{'redistribute_source_allowed':True}]:
            bad=replace(permission,policy=replace(permission.policy,**change))
            with self.subTest(change=change),self.assertRaises((ValidationError,AssetPolicyError)):
                replace(original,permissions=(bad,*original.permissions[1:]))
        for bad in [replace(permission,source_only=True),replace(permission,source_sha256='f'*64)]:
            with self.assertRaises((ValidationError,AssetPolicyError)):replace(original,permissions=(bad,*original.permissions[1:]))
        with self.assertRaises(ValidationError):replace(original,permissions=original.permissions[:-1])


class DestinationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve();self.project=self.root/'source';self.project.mkdir()

    def test_new_folder_publish_keeps_all_existing_data(self):
        existing=self.root/'existing.txt';existing.write_text('KEEP')
        plan=plan_destination(self.root/'new',self.project);stage=plan.stage('UNIT_JOB');(stage/'output.txt').write_text('OWNED_OUTPUT')
        plan.unchanged();rename_new(stage,plan.path)
        self.assertEqual((plan.path/'output.txt').read_text(),'OWNED_OUTPUT');self.assertEqual(existing.read_text(),'KEEP')

    def test_raced_in_empty_destination_is_never_replaced(self):
        plan=plan_destination(self.root/'new',self.project);stage=plan.stage('UNIT_JOB');(stage/'output.txt').write_text('OWNED_OUTPUT')
        plan.path.mkdir();identity=plan.path.stat().st_ino
        with self.assertRaises(OSError):rename_new(stage,plan.path)
        self.assertTrue(stage.is_dir());self.assertEqual(plan.path.stat().st_ino,identity);self.assertEqual(list(plan.path.iterdir()),[])

    def test_existing_reserved_relative_missing_parent_and_parent_replacement_reject(self):
        (self.project/'master').mkdir()
        for path in [self.project,self.project/'master/output',Path('relative'),self.root/'missing/new',self.root/'NUL.txt',self.root/'trailing.']:
            with self.subTest(path=path),self.assertRaises((ValidationError,ProjectStorageError)):plan_destination(path,self.project)
        parent=self.root/'parent';parent.mkdir();plan=plan_destination(parent/'new',self.project)
        parent.rename(self.root/'old-parent');parent.mkdir()
        with self.assertRaises(ProjectStorageError):plan.unchanged()
