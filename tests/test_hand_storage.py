"""Storage/receipt tests use synthetic bytes; never Blender/geometry evidence."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
import tempfile
import unittest

from ucc.core.errors import ProjectStorageError,ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.core.hand_parts import (build_hand_library_recipe,build_hand_manifest,canonical_digest,
                                 build_hand_receipt,validate_hand_receipt)
from ucc.jobs.hand_storage import (publish_asset,publish_manifest,load_hand_library,
                                   publish_hand_receipt,load_hand_receipt)


class HandStorageTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.store=ProjectStore(self.root/'project')
        self.jobs=self.root/'worker';self.jobs.mkdir()
        # Structural byte fixtures only; these are not usable Blender scenes.
        data=b'BLENDER'+b'not-real-geometry-unit-fixture'*80;self.source_sha=sha256(data).hexdigest()
        versions=self.store.root/'master/versions';versions.mkdir(parents=True)
        (versions/(self.source_sha+'.blend')).write_bytes(data)
        self.project=self.store.save(replace(CharacterProject.new('Storage fixture only'),
                    master_blend='master/versions/'+self.source_sha+'.blend',geometry_state='generated_unverified'))
        self.initial=self.store.file.read_bytes();assets={}
        for variant in ('shorter','longer'):
            path=self.jobs/(variant+'.blend');path.write_bytes(b'BLENDER'+variant.encode()*500)
            digest=sha256(path.read_bytes()).hexdigest()
            publish_asset(self.store,path,digest,self.jobs)
            assets[variant]={'sha256':digest,'observation_sha256':('b' if variant=='shorter' else 'c')*64}
        self.manifest=build_hand_manifest(build_hand_library_recipe(self.project,self.source_sha),assets)
        self.identity=publish_manifest(self.store,self.manifest)
        self.library=load_hand_library(self.store,self.identity)

    def test_immutable_registration_load_and_reuse_preserve_source_and_metadata(self):
        self.assertEqual(self.identity,canonical_digest(self.manifest))
        self.assertEqual(publish_manifest(self.store,self.manifest),self.identity)
        for variant,path in self.library.assets.items():
            source=self.jobs/(variant+'.blend')
            again=publish_asset(self.store,source,sha256(source.read_bytes()).hexdigest(),self.jobs)
            self.assertEqual(again,path)
            self.assertEqual(source.read_bytes(),path.read_bytes())
        self.assertEqual(self.store.file.read_bytes(),self.initial)
        self.assertEqual(self.store.load(),self.project)

    def test_changed_assets_source_and_manifest_are_rejected(self):
        path=self.library.assets['shorter'];original=path.read_bytes();path.write_bytes(original+b'changed')
        with self.assertRaises(ProjectStorageError):load_hand_library(self.store,self.identity)
        path.write_bytes(original)
        source=self.library.source_master;data=source.read_bytes();source.write_bytes(data+b'changed')
        with self.assertRaises(ProjectStorageError):load_hand_library(self.store,self.identity)
        source.write_bytes(data)
        manifest_path=self.library.manifest_path;data=manifest_path.read_bytes();manifest_path.write_bytes(data+b' ')
        with self.assertRaises(ProjectStorageError):load_hand_library(self.store,self.identity)
        self.assertEqual(self.store.file.read_bytes(),self.initial)

    def test_path_escape_and_pre_cancel_do_not_modify_project(self):
        for identity in ('../outside','F'*64,None):
            with self.assertRaises(ValidationError):load_hand_library(self.store,identity)
        outside=self.root/'outside.blend';outside.write_bytes(b'BLENDER'+b'outside'*300)
        with self.assertRaises(ProjectStorageError):
            publish_asset(self.store,outside,sha256(outside.read_bytes()).hexdigest(),self.jobs)
        cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):publish_manifest(self.store,self.manifest,cancel)
        self.assertEqual(self.store.file.read_bytes(),self.initial)

    def test_revision_receipt_is_closed_immutable_and_bound_to_library_selection(self):
        receipt=build_hand_receipt(self.identity,'d'*64,self.source_sha,'shorter','e'*64)
        path=publish_hand_receipt(self.store,receipt)
        self.assertEqual(load_hand_receipt(self.store,self.library,'d'*64,'shorter'),receipt)
        self.assertEqual(publish_hand_receipt(self.store,receipt),path)
        with self.assertRaises(ProjectStorageError):load_hand_receipt(self.store,self.library,'d'*64,'longer')
        with self.assertRaises(ProjectStorageError):load_hand_receipt(self.store,self.library,'f'*64,'shorter')
        changed=dict(receipt,observation_sha256='f'*64)
        with self.assertRaises(ProjectStorageError):publish_hand_receipt(self.store,changed)
        for key,value in [('schema_version',True),('selection','neutral'),('policy','other'),('master_sha256','../x')]:
            raw=deepcopy(receipt);raw[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):validate_hand_receipt(raw)
        self.assertEqual(self.store.file.read_bytes(),self.initial)


if __name__=='__main__':unittest.main()
