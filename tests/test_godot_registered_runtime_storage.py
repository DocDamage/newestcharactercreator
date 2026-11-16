"""Real filesystem retention faults; synthetic native/context gates explicitly stubbed."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from threading import Event
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from fixtures.godot_registered_retention_logic import RetentionFixture,OBSERVED,digest
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_runtime_contract import NAMESPACE,RegisteredRuntimeManifest
from ucc.jobs import godot_registered_runtime_storage as storage
from ucc.library.provenance import AssetPolicyError

ADM="ucc.jobs.godot_registered_runtime_admission."


class RegisteredRuntimeStorageTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.f=RetentionFixture(Path(temp.name).resolve())
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(storage,"current_inputs",return_value=self.f.context))
        self.stack.enter_context(patch(ADM+"_native_timeline",return_value=([],{})))
        self.stack.enter_context(patch(ADM+"validate_reopen_report"))
        self.stack.enter_context(patch(ADM+"validate_runtime_files",return_value=deepcopy(OBSERVED)))
        self.stack.enter_context(patch("ucc.jobs.runner.BlenderJobRunner.run",side_effect=AssertionError("IO-only retention launched a worker")))

    def retain(self,**changes):
        return storage.retain_registered_native_inputs(self.f.store,**(self.f.retain_args()|changes))

    def load(self,result,**changes):
        args=dict(selection=self.f.selection,retention_id=result.retention_id,expected_manifest_sha256=result.manifest_sha256,
            database_path=self.f.root/"unused-fixture-catalog.sqlite",permissions=self.f.permissions)
        return storage.load_registered_native_inputs(self.f.store,**(args|changes))

    def candidates(self):
        root=self.f.store.root/".ucc-candidates"/NAMESPACE
        return list(root.iterdir()) if root.exists() else []

    def test_retention_and_restart_load_preserve_every_reference_without_workers(self):
        source_before=self.f.store.file.read_bytes()
        result=self.retain();manifest=RegisteredRuntimeManifest.from_bytes((result.directory/"manifest.json").read_bytes())
        self.assertEqual(manifest.selection,self.f.selection)
        self.assertEqual(len(manifest.proofs),4)
        self.assertEqual((result.directory/".gdignore").read_bytes(),b"")
        self.assertFalse(result.runtime_execution_verified);self.assertFalse(result.engine_import_verified)
        jobs_before={p.name for p in (self.f.store.root/".ucc-jobs").iterdir()}
        again=self.load(result)
        self.assertEqual(result,again)
        self.assertEqual(jobs_before,{p.name for p in (self.f.store.root/".ucc-jobs").iterdir()})
        self.assertEqual(self.f.store.file.read_bytes(),source_before)
        self.assertEqual(json.loads((result.directory/"native_recipe.json").read_bytes())["project_snapshot"]["animations"],list(self.f.project.animations))
        # Retained metadata replaces dependency on transient producer job folders;
        # historical binding/current-source authority is still mandatory.
        for directory in (self.f.work,self.f.stage,self.f.fresh):
            self.assertTrue(directory.resolve().is_relative_to(self.f.root));shutil.rmtree(directory)
        self.assertEqual(self.load(result),result)

    def test_receipt_locator_or_expected_hash_cannot_select_foreign_producer(self):
        for changes in (dict(expected_production_receipt_sha256="0"*64),
                dict(preparation=replace(self.f.preparation,workdir=self.f.root)),
                dict(preparation={"directory":str(self.f.fresh)})):
            with self.subTest(changes=changes),self.assertRaises((ProjectStorageError,ValidationError)):
                self.retain(**changes)
        self.assertFalse(self.candidates())

    def test_cancel_during_copy_has_no_candidate_commit(self):
        event=Event();real=storage.copy_file
        def copy(*args):
            real(*args);event.set()
        with patch.object(storage,"copy_file",side_effect=copy):
            with self.assertRaises(ProjectStorageError):self.retain(cancel=event)
        self.assertFalse(self.candidates())

    def test_cancel_before_rename_has_no_commit(self):
        event=Event()
        def progress(phase):
            if phase=="COMMIT_PRIVATE_REGISTERED_INPUTS":event.set()
        with self.assertRaises(ProjectStorageError):self.retain(cancel=event,progress=progress)
        self.assertFalse(self.candidates())

    def test_postcommit_cancel_retains_history_with_truthful_note_and_explicit_reload(self):
        event=Event()
        def progress(phase):
            if phase=="PRIVATE_INPUTS_COMMITTED":event.set()
        with self.assertRaises(ProjectStorageError) as failure:self.retain(cancel=event,progress=progress)
        self.assertTrue(any("commit completed at" in n for n in failure.exception.__notes__))
        [directory]=self.candidates();manifest=RegisteredRuntimeManifest.from_bytes((directory/"manifest.json").read_bytes())
        event.clear()
        value=storage.load_registered_native_inputs(self.f.store,selection=self.f.selection,retention_id=manifest.retention_id,
            expected_manifest_sha256=manifest.sha256,database_path=self.f.root/"unused.sqlite",permissions=self.f.permissions)
        self.assertEqual(value.directory,directory)

    def test_existing_destination_is_preserved(self):
        ident=str(UUID(int=9000));root=self.f.store.root/".ucc-candidates"/NAMESPACE/ident
        root.mkdir(parents=True);(root/"foreign.txt").write_bytes(b"FOREIGN_PRESERVE")
        with patch.object(storage,"uuid4",return_value=UUID(int=9000)):
            with self.assertRaises(ProjectStorageError):self.retain()
        self.assertEqual((root/"foreign.txt").read_bytes(),b"FOREIGN_PRESERVE")

    def test_empty_foreign_staging_replacement_is_not_adopted(self):
        def progress(phase):
            if phase=="COPY_PRIVATE_REGISTERED_INPUTS":
                [stage]=list((self.f.store.root/".ucc-jobs").glob("registered-runtime-retention-*/inputs"))
                kept=stage.with_name("owned-inputs-kept")
                self.assertTrue(kept.resolve().is_relative_to(self.f.root));stage.rename(kept);stage.mkdir()
                self.foreign=stage
        with self.assertRaises(ProjectStorageError):self.retain(progress=progress)
        self.assertEqual(list(self.foreign.iterdir()),[])
        self.assertFalse(self.candidates())

    def test_same_byte_foreign_candidate_directory_is_preserved_and_rejected(self):
        def progress(phase):
            if phase=="PRIVATE_INPUTS_COMMITTED":
                [directory]=self.candidates();self.kept=self.f.root/"owned-candidate-kept"
                self.assertTrue(self.kept.resolve().is_relative_to(self.f.root));directory.rename(self.kept)
                shutil.copytree(self.kept,directory);self.foreign=directory
        with self.assertRaises(ProjectStorageError) as failure:self.retain(progress=progress)
        self.assertTrue(self.foreign.is_dir() and self.kept.is_dir())
        self.assertTrue(any("commit completed" in n for n in failure.exception.__notes__))
        self.assertEqual((self.foreign/"manifest.json").read_bytes(),(self.kept/"manifest.json").read_bytes())

    def test_same_byte_candidate_file_replacement_is_rejected(self):
        def progress(phase):
            if phase=="PRIVATE_INPUTS_COMMITTED":
                [directory]=self.candidates();path=directory/"character.glb"
                replacement=self.f.root/"replacement.bin";replacement.write_bytes(path.read_bytes());replacement.replace(path)
        with self.assertRaises(ProjectStorageError):self.retain(progress=progress)
        self.assertEqual(len(self.candidates()),1)

    def test_restart_load_rejects_directory_replacement_during_manifest_read(self):
        result=self.retain();real=storage.read_bytes
        def read(*args,**kwargs):
            captured=real(*args,**kwargs)
            kept=self.f.root/"restart-owned-directory-kept"
            result.directory.rename(kept);shutil.copytree(kept,result.directory)
            return captured
        with patch.object(storage,"read_bytes",side_effect=read):
            with self.assertRaises(ProjectStorageError):self.load(result)
        self.assertTrue(result.directory.is_dir())

    def test_policy_revocation_during_final_candidate_seal_is_not_missed(self):
        real=storage.seal;count=[0]
        def seal(directory,*args):
            result=real(directory,*args)
            if NAMESPACE in Path(directory).parts:
                count[0]+=1
                if count[0]==2:self.f.revoked=True
            return result
        with patch.object(storage,"seal",side_effect=seal):
            with self.assertRaises(ProjectConflict):self.retain()
        self.assertEqual(len(self.candidates()),1)

    def test_source_reference_change_during_final_seal_is_not_missed(self):
        real=storage.seal;count=[0]
        def seal(directory,*args):
            result=real(directory,*args)
            if NAMESPACE in Path(directory).parts:
                count[0]+=1
                if count[0]==2:(self.f.fresh/"runtime_source.blend").write_bytes(b"NONSHIPPING_CHANGED_REFERENCE")
            return result
        with patch.object(storage,"seal",side_effect=seal):
            with self.assertRaises(ProjectStorageError):self.retain()
        self.assertEqual(len(self.candidates()),1)

    def test_retained_extra_missing_or_changed_file_rejects_reload(self):
        result=self.retain();path=result.directory/"character.glb";original=path.read_bytes()
        path.write_bytes(original+b"!")
        with self.assertRaises(ProjectStorageError):self.load(result)
        path.write_bytes(original);extra=result.directory/"unlisted.gd";extra.write_text("# NONSHIPPING")
        with self.assertRaises(ProjectStorageError):self.load(result)
        extra.unlink();path.unlink()
        with self.assertRaises((ProjectStorageError,ValidationError)):self.load(result)

    def test_current_context_and_permission_drift_rejects_reload(self):
        result=self.retain();self.f.revoked=True
        with self.assertRaises(ProjectConflict):self.load(result)
        self.f.revoked=False
        changed=tuple(replace(p,source_only=True) if i==0 else p for i,p in enumerate(self.f.permissions))
        with self.assertRaises((ValidationError,AssetPolicyError)):self.load(result,permissions=changed)

    def test_coherent_native_error_report_rehash_still_rejects(self):
        path=self.f.fresh/"native_verification.json";report=json.loads(path.read_bytes())
        report["frames"][0]["source_error_m"]=.01;path.write_bytes(canonical_bytes(report))
        result_path=self.f.fresh/"result.json";result=json.loads(result_path.read_bytes())
        result["details"]["native_verification_sha256"]=digest(path);result_path.write_bytes(canonical_bytes(result))
        receipt=json.loads(self.f.preparation.production_receipt.read_bytes());receipt["native_verification_sha256"]=digest(path)
        self.f.preparation.production_receipt.write_bytes(canonical_bytes(receipt))
        with self.assertRaises(ValidationError):self.retain(expected_production_receipt_sha256=digest(self.f.preparation.production_receipt))
        self.assertFalse(self.candidates())
