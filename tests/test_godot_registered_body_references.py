"""Small nonshipping reference records; no actual geometry or engine proof."""
from hashlib import sha256
from pathlib import Path
import struct
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from ucc.jobs import godot_registered_body_references as references
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.jobs.godot_registered_body_references import convert_reference
from ucc.jobs.godot_registered_body_references import verify_import_configuration
import json
from ucc.jobs.target_action_context import Budget


class RegisteredBodyReferenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.source=self.root/'NONSHIPPING_REFERENCE.bin';self.target=self.root/'converted.bin'

    def convert(self,raw,normal=False,**kwargs):
        self.source.write_bytes(raw)
        return convert_reference(self.source,self.target,sha256(raw).hexdigest(),normal=normal,
            budget=Budget(None,60),frames=2,vertices=2,**kwargs)

    def test_exact_reference_conversion_preserves_every_xyz_and_homogeneous_tag(self):
        raw=struct.pack('<12f',*range(12));record=self.convert(raw)
        self.assertEqual(record['bytes'],64)
        rows=list(struct.iter_unpack('<4f',self.target.read_bytes()))
        self.assertEqual(rows,[(0.,1.,2.,1.),(3.,4.,5.,1.),(6.,7.,8.,1.),(9.,10.,11.,1.)])
        self.assertEqual(self.source.read_bytes(),raw)

    def test_normal_stream_has_unit_bound_and_zero_w(self):
        self.convert(struct.pack('<12f',*([0.,0.,1.]*4)),normal=True)
        self.assertTrue(all(row[3]==0. for row in struct.iter_unpack('<4f',self.target.read_bytes())))

    def test_rehashed_nonfinite_or_out_of_bounds_values_do_not_gain_admission(self):
        for value in (float('nan'),float('inf'),101.):
            with self.subTest(value=value),self.assertRaises(ValidationError):self.convert(struct.pack('<12f',*([value]*12)))
            self.target.unlink(missing_ok=True)
        with self.assertRaises(ValidationError):self.convert(struct.pack('<12f',*([0.]*12)),normal=True)

    def test_short_trailing_wrong_hash_existing_destination_and_cancel_reject(self):
        for raw in (b'123',b'0'*49):
            with self.assertRaises((ValidationError,ProjectStorageError)):self.convert(raw)
        raw=struct.pack('<12f',*range(12));self.source.write_bytes(raw)
        with self.assertRaises(ValidationError):convert_reference(self.source,self.target,'0'*64,normal=False,budget=Budget(None,60),frames=2,vertices=2)
        self.target.write_bytes(b'FOREIGN_PRESERVE')
        with self.assertRaises(FileExistsError):self.convert(raw)
        self.assertEqual(self.target.read_bytes(),b'FOREIGN_PRESERVE')
        self.target.unlink();event=Event();event.set()
        with self.assertRaises(ProjectStorageError):convert_reference(self.source,self.target,sha256(raw).hexdigest(),normal=False,budget=Budget(event,60),frames=2,vertices=2)

    def test_same_byte_foreign_replacement_after_descriptor_close_is_rejected(self):
        raw=struct.pack('<12f',*range(12));real=references.hash_file
        def hashed(path,*args):
            if path==self.target:
                replacement=self.root/'foreign.bin';replacement.write_bytes(path.read_bytes());replacement.replace(path)
            return real(path,*args)
        with patch.object(references,'hash_file',side_effect=hashed):
            with self.assertRaises(ProjectStorageError):self.convert(raw)
        self.assertEqual(self.target.stat().st_size,64)

    def test_import_configuration_uses_typed_checked_values_not_incidental_text(self):
        raw=b'# animation/fps=30.0 "optimizer/enabled": false "compression/enabled": false\n'
        (self.root/'character.glb.import').write_bytes(raw)
        report=dict(schema_version=1,phase='POST_REIMPORT',animation_fps=30.,optimizer_enabled=True,
            compression_enabled=False,import_settings_sha256=sha256(raw).hexdigest())
        path=self.root/'import_configuration.json';path.write_text(json.dumps(report))
        with self.assertRaises(ValidationError):verify_import_configuration(self.root,'POST_REIMPORT',Budget(None,60))
        report['optimizer_enabled']=False;path.write_text(json.dumps(report))
        self.assertFalse(verify_import_configuration(self.root,'POST_REIMPORT',Budget(None,60))['optimizer_enabled'])
        (self.root/'character.glb.import').write_bytes(raw+b'CHANGED')
        with self.assertRaises(ProjectStorageError):verify_import_configuration(self.root,'POST_REIMPORT',Budget(None,60))
