"""Isolated synthetic mapping/reader faults; never claim native/render proof."""
from hashlib import sha256
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from fixtures.godot_registered_body_draw_logic import synthetic_draw_outputs,write_measurement,png
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.jobs.godot_registered_body_draw_evidence import map_frame,verify_draw_outputs
from ucc.jobs.target_action_context import Budget


def small_mapping():
    return dict(position_bytes=struct.pack('<12f',1,2,3,1,0,0,0,1,0,1,0,1),
                normal_bytes=struct.pack('<4f',0,0,1,0)*3,
                ids_bytes=struct.pack('<4I',0,1,2,0),uv_bytes=struct.pack('<8f',0,0,1,0,0,1,1,1),
                triangles_bytes=struct.pack('<6I',0,1,2,3,2,1),source_vertices=3,imported_vertices=4)


class DrawMappingTests(unittest.TestCase):
    def test_inverse_world_basis_and_seam_duplicate_preserve_uv_indices(self):
        a=small_mapping();r=map_frame(**a);points=list(struct.iter_unpack('<3f',r['positions']))
        self.assertEqual(points[0],(1,3,-2));self.assertEqual(points[3],points[0])
        self.assertEqual(struct.unpack_from('<3f',r['normals']), (0,1,-0.))
        self.assertEqual(r['uv'],a['uv_bytes']);self.assertEqual(r['triangles'],a['triangles_bytes'])
    def test_missing_source_coverage_rejected(self):
        a=small_mapping();a['ids_bytes']=struct.pack('<4I',0,1,1,0)
        with self.assertRaises(ValidationError):map_frame(**a)
    def test_out_of_bounds_and_missing_triangle_vertex_rejected(self):
        for values in ((0,1,4,3,2,1),(0,1,2,0,2,1)):
            a=small_mapping();a['triangles_bytes']=struct.pack('<6I',*values)
            with self.subTest(values=values),self.assertRaises(ValidationError):map_frame(**a)
    def test_nonfinite_nonunit_or_wrong_homogeneous_normal_rejected(self):
        for row in ((float('nan'),0,1,0),(0,0,2,0),(0,0,1,1)):
            a=small_mapping();a['normal_bytes']=struct.pack('<4f',*row)*3
            with self.subTest(row=row),self.assertRaises(ValidationError):map_frame(**a)
    def test_wrong_position_w_or_nonfinite_UV_rejected(self):
        for key,raw in [('position_bytes',struct.pack('<4f',1,2,3,0)*3),('uv_bytes',struct.pack('<2f',float('inf'),0)*4)]:
            a=small_mapping();a[key]=raw
            with self.subTest(key=key),self.assertRaises(ValidationError):map_frame(**a)
    def test_lengths_mutable_bytes_and_bool_dimensions_rejected(self):
        for key,value in [('position_bytes',b''),('normal_bytes',bytearray(48)),('source_vertices',True)]:
            a=small_mapping();a[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):map_frame(**a)
    def test_budget_callback_propagates_cancellation(self):
        def cancel():raise RuntimeError('synthetic caller cancellation')
        with self.assertRaisesRegex(RuntimeError,'synthetic caller'):map_frame(**small_mapping(),check=cancel)


class DrawEvidenceReaderTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.folder=Path(temp.name).resolve()
        self.spec,self.hashes,self.report=synthetic_draw_outputs(self.folder)
    def verify(self):return verify_draw_outputs(self.folder,self.spec,self.hashes,Budget(None,60))
    def save(self):write_measurement(self.folder,self.report)
    def replace_output(self,name,raw):
        (self.folder/name).write_bytes(raw);self.report['frames'][0]['files'][name]={'sha256':sha256(raw).hexdigest(),'bytes':len(raw)};self.save()
    def test_full_synthetic_closure_decodes_png_and_exact_array_buffers(self):
        value=self.verify();self.assertEqual(len(value['files']),15);self.assertEqual([v['frame'] for v in value['observations']],[1,150,300]);self.assertTrue(all(v['opaque_pixels']==256 for v in value['observations']))
    def test_validly_rehashed_wrong_draw_array_rejected(self):
        name='frame001_draw_positions.f32';raw=bytearray((self.folder/name).read_bytes());struct.pack_into('<f',raw,0,9.)
        self.replace_output(name,bytes(raw))
        with self.assertRaisesRegex(ValidationError,'assigned draw arrays'):self.verify()
    def test_unpinned_staged_bytes_rejected(self):
        (self.folder/'frame001_positions.f32').write_bytes(b'x')
        with self.assertRaises(ProjectStorageError):self.verify()
    def test_widened_flag_or_unknown_measurement_key_rejected(self):
        for key,value in [('visual_quality_approved',True),('unknown',False)]:
            with self.subTest(key=key):
                old=dict(self.report);self.report[key]=value;self.save()
                with self.assertRaises(ValidationError):self.verify()
                self.report=old
    def test_duplicate_or_boolean_frame_and_invisible_mesh_rejected(self):
        for key,value in [('frame',True),('frame',150),('mesh_visible',False),('camera_current',1)]:
            row=self.report['frames'][0];old=row[key];row[key]=value;self.save()
            with self.subTest(key=key,value=value),self.assertRaises(ValidationError):self.verify()
            row[key]=old
    def test_unknown_output_and_boolean_bytecount_rejected(self):
        files=self.report['frames'][0]['files'];files['outside.png']={'sha256':'a'*64,'bytes':1};self.save()
        with self.assertRaises(ValidationError):self.verify()
        del files['outside.png'];files['frame001.png']['bytes']=True;self.save()
        with self.assertRaises(ValidationError):self.verify()
    def test_blank_and_clipped_private_PNG_rejected_even_when_rehashed(self):
        for options in ({'blank':True},{'clipped':True}):
            self.replace_output('frame001.png',png(**options))
            with self.subTest(options=options),self.assertRaises(ValidationError):self.verify()
    def test_duplicate_JSON_key_rejected_from_same_captured_bytes(self):
        raw=json.dumps(self.report);(self.folder/'measurement.json').write_text(raw[:-1]+',"schema_version":1}',encoding='utf-8')
        with self.assertRaises(ValidationError):self.verify()
    def test_between_read_input_drift_rejected_before_acceptance(self):
        import ucc.jobs.godot_registered_runtime_files as files
        real=files.read_bytes
        def race(path,*args,**kwargs):
            value=real(path,*args,**kwargs)
            if Path(path).name=='measurement.json':
                (self.folder/'imported_uv.f32').write_bytes(b'x'* (14517*8))
            return value
        with patch.object(files,'read_bytes',side_effect=race),self.assertRaises(ProjectStorageError):self.verify()
    def test_input_hash_closure_and_wrong_spec_rejected(self):
        self.hashes['foreign']='a'*64
        with self.assertRaises(ValidationError):self.verify()
        del self.hashes['foreign'];self.spec='a'*64
        with self.assertRaises(ProjectStorageError):self.verify()

    def test_overflowed_nested_JSON_number_rejected(self):
        raw=json.dumps(self.report).replace('"patch": 1','"patch": 1, "invalid_overflow": 1e999')
        (self.folder/'measurement.json').write_text(raw,encoding='utf-8')
        with self.assertRaises(ValidationError):self.verify()
    def test_hardlinked_output_rejected(self):
        import os
        path=self.folder/'frame001_draw_uv.f32';other=self.folder/'foreign-UV.bin';path.rename(other);os.link(other,path)
        with self.assertRaisesRegex(ProjectStorageError,'single-link'):self.verify()

    def test_oct_normal_quantization_within_actual_engine_bound_accepted(self):
        raw=struct.pack('<3f',0.00019,1.,0.)*14517
        self.replace_output('frame001_draw_normals.f32',raw)
        value=self.verify();error=value['observations'][0]['max_normal_vector_error']
        self.assertGreater(error,0.00018);self.assertLessEqual(error,0.0002)
        self.assertIn('OCTAHEDRAL',value['observations'][0]['normal_readback_policy'])
    def test_rehashed_unit_normal_outside_engine_bound_rejected(self):
        raw=struct.pack('<3f',0.0003,1.,0.)*14517
        self.replace_output('frame001_draw_normals.f32',raw)
        with self.assertRaisesRegex(ValidationError,'engine format bound'):self.verify()
