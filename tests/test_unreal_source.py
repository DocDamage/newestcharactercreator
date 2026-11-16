"""Pure FBX closure faults using generated NONSHIPPING degenerate parser data."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import sys
from fixtures.unreal_fbx_logic import fixture, node, encoded_header, decoded_header
from blender_bridge.unreal_fbx_metadata import fbx_metadata, unreal_name, unreal_bone_name
from blender_bridge.unreal_fbx_metadata import normalize_export_header, validate_portable_header, PORTABLE_HEADER_VALUES
from blender_bridge.unreal_source_reference import portable_export_header
from blender_bridge import unreal_source_workers as workers
from ucc.export.unreal_blender_recipe import FILES, VERIFY, NORMAL_BYTES
from tempfile import TemporaryDirectory
from hashlib import sha256
from fixtures.unreal_contract_logic import request
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes


class UnrealSourceMetadataTests(TestCase):
    def observe(self, f):
        package = ModuleType('io_scene_fbx'); package.__path__ = []
        parser = SimpleNamespace(parse=lambda path:(f.tree,7400))
        with patch.dict(sys.modules, {'io_scene_fbx':package, 'io_scene_fbx.parse_fbx':parser}):
            return fbx_metadata(Path('UNIT_NOT_REAL_FBX'), f.reference)

    def test_bone_cluster_links_are_not_model_parents_and_two_poses_are_required(self):
        f = fixture(); metadata, order = self.observe(f)
        self.assertEqual(len(order), 163)
        self.assertEqual(metadata['bind_pose_nodes'], 165)
        self.assertTrue(metadata['bind_pose_covers_all_models_and_cluster_links'])
        self.assertTrue(metadata['all_original_positive_fbx_influences_preserved'])
        self.assertFalse(metadata['sdk_bind_pose_validity_observed'])
        self.assertEqual(metadata['expected_unreal_material_slot_name'], 'UNIT_MATERIAL')

    def test_duplicate_model_parent_is_rejected(self):
        f = fixture(); f.connections.elems.append(node(b'C',[b'OO',101,2]))
        with self.assertRaisesRegex(ValueError, 'parent graph'):
            self.observe(f)

    def test_bind_pose_cardinality_identity_finite_and_cluster_faults(self):
        for fault in ('missing', 'extra', 'duplicate', 'nonfinite', 'mesh_matrix', 'mesh_identity', 'cluster_matrix'):
            with self.subTest(fault=fault):
                f = fixture()
                if fault == 'missing':f.objects.elems.remove(f.partial)
                elif fault == 'extra':f.objects.elems.append(node(b'Pose',[9999,b'EXTRA',b'BindPose']))
                elif fault == 'duplicate':f.full.elems[-1].elems[0].props[0] = 100
                elif fault == 'nonfinite':f.full.elems[-1].elems[1].props[0][0] = float('nan')
                elif fault == 'mesh_matrix':f.partial.elems[1].elems[1].props[0][0] = 2.
                elif fault == 'mesh_identity':f.partial.elems[1].elems[0].props[0] = 100
                else:f.clusters[0].elems[0].props[0][0] = 2.
                with self.assertRaises(ValueError):
                    self.observe(f)

    def test_exact_original_local_vertices_triangles_and_uvs_are_enforced(self):
        for fault in ('vertex', 'winding', 'uv'):
            with self.subTest(fault=fault):
                f = fixture()
                if fault == 'vertex':f.vertices.props[0][0] = .01
                elif fault == 'winding':f.indices.props[0][0:2] = type(f.indices.props[0])('i',[1,0])
                else:f.uv.props[0][0] = .01
                with self.assertRaises(ValueError):
                    self.observe(f)

    def test_original_positive_weights_material_and_morph_identities_are_enforced(self):
        for fault in ('weight', 'material', 'morph'):
            with self.subTest(fault=fault):
                f = fixture()
                if fault == 'weight':f.clusters[0].elems[-1].props[0][0] = .5
                elif fault == 'material':f.material.props[1] = b'WRONG_MATERIAL'
                else:f.channels[0].props[1] = b'WRONG_MORPH'
                with self.assertRaises(ValueError):
                    self.observe(f)

    def test_unreal_name_composition_matches_declared_source_rules(self):
        self.assertEqual(unreal_name('prefix: Bone.Name/`%, '), ' Bone_Name____ ')
        self.assertEqual(unreal_bone_name('prefix: Bone.Name '), 'Bone_Name')
        self.assertEqual(unreal_bone_name('Bone inner space'), 'Bone-inner-space')

    def test_worker_rejects_altered_sealed_files_before_opening_master(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve(); options = {'master_sha256':'a'*64,'recipe_sha256':'b'*64}
            for name in FILES:
                path = root/name; path.write_bytes(bytes(NORMAL_BYTES) if name == 'source_corner_normals.bin' else b'UNIT_NOT_REAL_SOURCE')
                options[name.replace('.', '_')+'_sha256'] = sha256(path.read_bytes()).hexdigest()
            (root/'character.fbx').write_bytes(b'CORRUPT')
            job = {'operation':VERIFY,'input_project':'candidate.blend','options':options}
            with patch.object(workers, 'source') as open_master:
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    workers.verify(None, root, job)
                open_master.assert_not_called()

    def test_fresh_original_reference_mismatch_cannot_repair_or_reexport(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve(); options = {'master_sha256':'a'*64,'recipe_sha256':'b'*64}
            for name in FILES:
                content = bytes(NORMAL_BYTES) if name == 'source_corner_normals.bin' else canonical_bytes({'UNIT_NOT_REAL_SOURCE':True})
                path = root/name; path.write_bytes(content)
                options[name.replace('.', '_')+'_sha256'] = sha256(content).hexdigest()
            original = {name:(root/name).read_bytes() for name in FILES}
            args = (request(), SkinMaterialSpec((.3,.2,.1), .6), None, None, None, 'UNIT_STATE', 'UNIT_SHADER')
            job = {'operation':VERIFY,'input_project':'candidate.blend','options':options}
            with patch.object(workers,'source',return_value=args), patch.object(workers,'reference',
                    return_value=({'DIFFERENT_FRESH_ORIGINAL_REFERENCE':True}, bytes(NORMAL_BYTES), {})), \
                    patch.object(workers,'fbx_metadata',return_value=({},[])), \
                    patch.object(workers,'export_character') as export:
                with self.assertRaisesRegex(ValueError, 'differ from a fresh original'):
                    workers.verify(None, root, job)
                export.assert_not_called()
            self.assertEqual({name:(root/name).read_bytes() for name in FILES}, original)

    def test_four_header_strings_are_portable_and_other_metadata_is_untouched(self):
        native_file='C:/UNIT_PRIVATE_JOB/candidate.blend'
        root,fields=encoded_header(native_file)
        untouched=node(b'UNIT_GEOMETRY_MARKER',[b'UNIT_NOT_REAL_GEOMETRY'])
        root.elems.append(untouched)
        normalize_export_header(root,native_file)
        validate_portable_header(decoded_header(root))
        self.assertIs(root.elems[-1],untouched)
        self.assertEqual(untouched.props,[b'UNIT_NOT_REAL_GEOMETRY'])
        self.assertEqual({field.props[0][4:]:field.props[-1][4:] for field in fields},PORTABLE_HEADER_VALUES)

    def test_header_requires_exact_unique_known_string_fields(self):
        for fault in ('wrong_old_value','wrong_native','duplicate','wrong_type','missing'):
            with self.subTest(fault=fault):
                root,_=encoded_header('C:/UNIT_PRIVATE_JOB/candidate.blend',fault)
                with self.assertRaises(ValueError):
                    normalize_export_header(root,'C:/UNIT_PRIVATE_JOB/candidate.blend')

    def test_parsed_header_rejects_private_path_or_absolute_placeholder(self):
        for value in (b'C:/UNIT_PRIVATE_JOB/candidate.blend', b'/foobar.fbx'):
            with self.subTest(value=value):
                root,_=encoded_header('C:/UNIT_PRIVATE_JOB/candidate.blend')
                normalize_export_header(root,'C:/UNIT_PRIVATE_JOB/candidate.blend')
                parsed=decoded_header(root)
                parsed.elems[0].elems[0].elems[0].elems[0].props[-1]=value
                with self.assertRaisesRegex(ValueError,'not portable'):
                    validate_portable_header(parsed)

    def test_header_hook_calls_original_and_restores_on_success_or_any_failure(self):
        for fault in (None,'header_failure','wrong_type','operator_failure'):
            with self.subTest(fault=fault):
                package=ModuleType('io_scene_fbx');calls=[]
                def original(root,scene_data,time=None):
                    calls.append('ORIGINAL_HEADER_CALLED')
                    if fault=='header_failure':raise RuntimeError('UNIT_HEADER_FAILURE')
                    built,_=encoded_header('C:/UNIT_PRIVATE_JOB/candidate.blend',fault)
                    root.elems.extend(built.elems)
                exporter=SimpleNamespace(fbx_header_elements=original);package.export_fbx_bin=exporter
                bpy=SimpleNamespace(data=SimpleNamespace(filepath='C:/UNIT_PRIVATE_JOB/candidate.blend'))
                root=SimpleNamespace(elems=[])
                def run():
                    with portable_export_header(bpy):
                        self.assertIsNot(exporter.fbx_header_elements,original)
                        exporter.fbx_header_elements(root,None)
                        if fault=='operator_failure':raise RuntimeError('UNIT_OPERATOR_FAILURE')
                with patch.dict(sys.modules,{'io_scene_fbx':package}):
                    if fault:
                        with self.assertRaises((RuntimeError,ValueError)):run()
                    else:
                        run();validate_portable_header(decoded_header(SimpleNamespace(id=b'',props=[],props_type=bytearray(),elems=root.elems)))
                self.assertIs(exporter.fbx_header_elements,original)
                self.assertEqual(calls,['ORIGINAL_HEADER_CALLED'])
