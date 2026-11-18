"""Independent decoded pixel/cache/atlas faults using clearly invented fixtures."""
from pathlib import Path
import json
import math
import shutil
import struct
import tempfile
import unittest

from fixtures.body_sprite_images import image_evidence
from ucc.core.errors import ValidationError
from ucc.sprites.body_evidence import checked_body_evidence,checked_body_atlas,annotate_body_atlas,atlas_side
from ucc.sprites.plan import build_plan,CameraProfile
from ucc.sprites.atlas import pack_frames


class BodySpriteEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.request,self.cache,self.options,self.report,self.proof,self.write=image_evidence(self.root)

    def test_complete_selected_clock_and_geometry_are_checked_against_actual_cache_bytes(self):
        report,proof=checked_body_evidence(self.root,self.request,self.options,self.cache)
        self.assertEqual(report,self.report);self.assertEqual(proof,self.proof)

    def test_actual_RNA_float32_world_strength_is_admitted_without_tolerance(self):
        observed=0.15000000596046448  # Public renderer setting as stored by Blender RNA.
        self.assertEqual(self.report['configuration']['world_nodes'][1],observed)
        checked_body_evidence(self.root,self.request,self.options,self.cache)
        bits=struct.unpack('<I',struct.pack('<f',observed))[0]
        neighbors=[struct.unpack('<f',struct.pack('<I',bits+step))[0] for step in (-1,1)]
        for strength in (*neighbors,math.nextafter(observed,-math.inf),math.nextafter(observed,math.inf),.15,.16):
            self.report['configuration']['world_nodes'][1]=strength;self.write()
            with self.subTest(strength=strength),self.assertRaisesRegex(ValidationError,'deterministic renderer'):
                checked_body_evidence(self.root,self.request,self.options,self.cache)

    def test_rehashed_scene_report_cannot_substitute_other_geometry_or_clock(self):
        for key,value in (('positions_sha256','e'*64),('triangles_sha256','f'*64)):
            old=self.report['frames'][0]['geometry'][key];self.report['frames'][0]['geometry'][key]=value;self.write()
            with self.subTest(key=key),self.assertRaises(ValidationError):checked_body_evidence(self.root,self.request,self.options,self.cache)
            self.report['frames'][0]['geometry'][key]=old
        self.report['frames'][0]['source_frame']=149;self.write()
        with self.assertRaises(ValidationError):checked_body_evidence(self.root,self.request,self.options,self.cache)

    def test_partial_full_source_or_saved_reopen_proof_is_rejected(self):
        self.proof['full_source_frames_verified']=299
        (self.root/'body_sprite_verification.json').write_text(json.dumps(self.proof))
        with self.assertRaises(ValidationError):checked_body_evidence(self.root,self.request,self.options,self.cache)

    def test_pixels_cannot_change_after_bound_render(self):
        path=self.root/self.report['frames'][0]['file'];path.write_bytes(path.read_bytes()+b'UNIT_TRAILING')
        with self.assertRaises(ValidationError):checked_body_evidence(self.root,self.request,self.options,self.cache)

    def atlas(self):
        frames=self.root/'atlas-inputs';output=self.root/'atlas'
        for direction in range(4):
            directory=frames/f'body_sample/dir-{direction:02d}';directory.mkdir(parents=True)
            for index,target in enumerate(self.request.window.target_frames):
                shutil.copyfile(self.root/f'body-{direction:02d}-{target:04d}.png',directory/f'frame-{index:04d}.png')
        plan=build_plan({'body_sample':2},CameraProfile(directions=4),width=128,height=128,fps=30)
        pack_frames(plan,frames,output,max_sheet_side=atlas_side(self.request),pivot_x=.5,pivot_y=.9)
        annotate_body_atlas(output,self.request);return output

    def test_real_atlas_crop_and_absolute_sample_labels_roundtrip(self):
        atlas=self.atlas();data=checked_body_atlas(atlas,self.root,self.request,self.report)
        self.assertEqual(data['frames'][0]['target_frame'],149)
        self.assertEqual(data['frames'][0]['source_frame_number'],150)
        self.assertEqual(data['frames'][1]['timestamp_s'],round(1/30,7))

    def test_rehashed_atlas_metadata_cannot_shift_to_source_origin_one(self):
        atlas=self.atlas();path=atlas/'sprite_atlas.json';data=json.loads(path.read_text())
        data['frames'][0]['source_frame_number']=149;path.write_text(json.dumps(data))
        with self.assertRaises(ValidationError):checked_body_atlas(atlas,self.root,self.request,self.report)


if __name__=='__main__':unittest.main()
