"""Closed owned PBR profile and complete GPU buffers; synthetic fixtures only."""
from dataclasses import replace
import math,struct,tempfile,unittest
from pathlib import Path
from ucc.core.errors import ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.preview.material_surface import load_material_surface
from ucc.preview.static_surface import from_full_mesh
from fixtures.material_preview_glb import write_material_triangle


class MaterialSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'UNIT_NOT_MODEL.glb';self.spec=SkinMaterialSpec((.3,.2,.1),.6)

    def load(self,mutate=lambda doc:None):
        write_material_triangle(self.path,self.spec,mutate);return load_material_surface(self.path,self.spec)

    def test_complete_smooth_normals_and_exact_material_survive_focus(self):
        mesh=self.load();surface=from_full_mesh(mesh)
        self.assertEqual(surface.material,self.spec);self.assertEqual(surface.material,surface.focused().material)
        self.assertEqual(surface.normals,surface.focused().normals)
        n=struct.unpack_from('<3f',surface.normals)
        for actual,expected in zip(n,(0.,-.894427191,-.4472135955)):self.assertAlmostEqual(actual,expected,places=6)
        self.assertEqual(len(surface.normals),len(surface.vertices))
        self.assertEqual(surface.frame(0),surface.focused().frame(0))

    def test_inverse_transpose_preserves_normal_under_nonuniform_rotation(self):
        def transform(doc):
            # Z rotation 90 degrees * positive scale (2,3,4).
            doc['nodes'][0]['matrix']=[0.,2.,0.,0.,-3.,0.,0.,0.,0.,0.,4.,0.,0.,0.,0.,1.]
        mesh=self.load(transform);normal=mesh.normals[0][0]
        expected=(.4472135955/3,0.,.894427191/4);length=math.sqrt(sum(v*v for v in expected))
        for a,b in zip(normal,expected):self.assertAlmostEqual(a,b/length,places=6)

    def test_wrong_pbr_texture_shader_mirror_or_missing_normals_reject(self):
        mutations=[lambda d:d['materials'][0]['pbrMetallicRoughness'].update(roughnessFactor=.2),
            lambda d:d['materials'][0]['pbrMetallicRoughness'].update(baseColorFactor=[1.,1.,1.,1.]),
            lambda d:d['materials'][0].update(normalTexture={'index':0}),
            lambda d:d.update(textures=[{}]),lambda d:d['materials'][0].update(extensions={'KHR_materials_unlit':{}}),
            lambda d:d['meshes'][0]['primitives'][0]['attributes'].pop('NORMAL'),
            lambda d:d['nodes'][0].update(scale=[-1.,1.,1.])]
        for mutate in mutations:
            with self.subTest(mutate=mutate),self.assertRaises((ValidationError,ValueError)):self.load(mutate)

    def test_incomplete_or_nonnormalized_surface_cannot_render_material(self):
        mesh=self.load()
        for bad in [replace(mesh,normals=()),replace(mesh,normals=(((0.,0.,0.),)*3,)),
                replace(mesh,normals=(((float('nan'),0.,1.),)*3,))]:
            with self.assertRaises(ValidationError):from_full_mesh(bad)

    def test_preview_protocol_accepts_only_closed_owned_parameters(self):
        from ucc.jobs.protocol import JobRequest
        request=JobRequest.new('export_preview_glb',input_project='candidate.blend',options={'owned_material_spec':self.spec.to_dict()})
        self.assertEqual(request.options['owned_material_spec'],self.spec.to_dict())
        for options in [{'export_textures':True},{'owned_material_spec':self.spec.to_dict(),'download':True},
                {'owned_material_spec':self.spec.to_dict()|{'roughness':float('nan')}}]:
            with self.assertRaises(ValidationError):JobRequest.new('export_preview_glb',input_project='candidate.blend',options=options)
