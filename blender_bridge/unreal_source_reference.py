"""Original MPFB bind observations and dedicated Unreal export, never native proof."""
from hashlib import sha256
from contextlib import contextmanager
import math
import struct
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh, discard_godot_bind_mesh
from blender_bridge.unreal_fbx_metadata import unreal_bone_name, normalize_export_header
from blender_bridge.skin_material_model import material_name
from ucc.export.unreal_contract import PROFILE
from ucc.export.unreal_blender_recipe import EXPORT_OPTIONS, NORMAL_BYTES


def reference(bpy, human, rig, *, master_sha: str, request_sha: str, spec) -> tuple[dict, bytes, dict]:
    candidate = build_godot_bind_mesh(bpy, human, rig)
    try:
        obj = candidate.object; mesh = obj.data; mesh.calc_loop_triangles()
        names = [bone.name for bone in rig.data.bones]
        groups = {group.index:group.name for group in obj.vertex_groups}
        weights = []
        for vertex in mesh.vertices:
            row = sorted((groups[g.group], float(g.weight)) for g in vertex.groups
                         if groups[g.group] in names and g.weight > 0)
            if not 1 <= len(row) <= 8 or any(not math.isfinite(w) for _,w in row) or sum(w for _,w in row) <= .0001:
                raise ValueError('Unreal source has unsupported or nonfinite original deform influences')
            weights.append(row)
        quads = [list(face.vertices) for face in mesh.polygons]
        if len(mesh.vertices) != 13380 or len(names) != 163 or len(quads) != 13378 or any(len(f) != 4 for f in quads):
            raise ValueError('Unreal source differs from the admitted MPFB human topology')
        uv = mesh.uv_layers.active
        if len(mesh.uv_layers) != 1 or uv is None:
            raise ValueError('Unreal source needs its complete original UV set')
        mapping = {name:unreal_bone_name(name) for name in names}
        if len(mapping) != 163 or len(set(mapping.values())) != 163:
            raise ValueError('Unreal importer bone naming is not a bijective source identity map')
        result = {'schema_version':1, 'policy':'UCC_UNREAL_ORIGINAL_BIND_REFERENCE_V1',
            'profile':PROFILE, 'master_sha256':master_sha, 'request_sha256':request_sha,
            'blender_version':bpy.app.version_string, 'blender_build':bpy.app.build_hash.decode(),
            'material_spec':spec.to_dict(), 'vertices':[list(obj.matrix_world@v.co) for v in mesh.vertices],
            'quads':quads, 'triangles':[list(t.vertices) for t in mesh.loop_triangles],
            'corners':[{'vertices':list(t.vertices), 'uv':[list(uv.data[i].uv) for i in t.loops]} for t in mesh.loop_triangles],
            'weights':weights, 'morphs':{key.name:[list(obj.matrix_world.to_3x3()@(p.co-v.co))
                for p,v in zip(key.data, mesh.vertices)] for key in mesh.shape_keys.key_blocks if key.name != 'Basis'},
            'bones':[{'name':bone.name, 'parent':bone.parent.name if bone.parent else None,
                'world':[float(value) for row in (rig.matrix_world@bone.matrix_local) for value in row]}
                for bone in rig.data.bones], 'candidate_observation':candidate.observation,
            'source_bind_local_vertices':[[float(v) for v in vertex.co] for vertex in mesh.vertices],
            'source_bind_object_world':[float(v) for row in obj.matrix_world for v in row],
            'source_to_unreal_bone_names':mapping,
            'original_rig_world':[float(v) for row in rig.matrix_world for v in row],
            'original_rig_object_scale':[float(v) for v in rig.scale],
            'source_material_name':material_name(spec),
            'rig_basis_policy':'ORIGINAL_OBJECT_AND_REST_DATA_NO_TRANSFORM_APPLICATION_OR_BONE_NORMALIZATION',
            'engine_import_verified':False}
        if len(result['morphs']) != 12 or len(result['triangles']) != 26756:
            raise ValueError('Unreal source needs every original triangle and twelve canonical controls')
        normal_matrix = obj.matrix_world.inverted().transposed().to_3x3()
        normals = bytearray()
        for triangle in mesh.loop_triangles:
            for index in triangle.loops:
                normal = (normal_matrix@mesh.corner_normals[index].vector).normalized()
                if not all(math.isfinite(float(v)) for v in normal):
                    raise ValueError('Unreal source normal is nonfinite')
                normals.extend(struct.pack('<3f', *normal))
    finally:
        discard_godot_bind_mesh(bpy, candidate)
    if len(normals) != NORMAL_BYTES:
        raise ValueError('Unreal source corner-normal coverage is incomplete')
    info = {'schema_version':1, 'policy':'UCC_UNREAL_ORIGINAL_CORNER_NORMALS_V1',
        'request_sha256':request_sha, 'master_sha256':master_sha, 'triangles':26756,
        'corners':80268, 'bytes':len(normals), 'encoding':'FLOAT32_LITTLE_ENDIAN_XYZ',
        'space':'BLENDER_WORLD_RH_Z_UP_UNITLESS', 'sha256':sha256(normals).hexdigest(),
        'target_normal_rule':'normalize((-ny,-nx,nz))', 'engine_import_verified':False,
        'runtime_deformation_verified':False}
    return result, bytes(normals), info


@contextmanager
def portable_export_header(bpy):
    """Scope the metadata-only hook to one owned export and restore on failure."""
    from io_scene_fbx import export_fbx_bin
    original = export_fbx_bin.fbx_header_elements
    def portable(root, scene_data, time=None):
        original(root, scene_data, time=time)
        normalize_export_header(root, bpy.data.filepath)
    try:
        export_fbx_bin.fbx_header_elements = portable
        yield
    finally:
        export_fbx_bin.fbx_header_elements = original


def export_character(bpy,root,human,rig):
    from blender_bridge.godot_bind_mesh import build_godot_bind_mesh,discard_godot_bind_mesh
    from blender_bridge.triangulated_export import triangulated_copy,discard_triangulated_copy
    if bpy.data.objects.get('Armature') is not None:raise ValueError('Reserved export Armature object name is occupied')
    selected=list(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
    candidate=build_godot_bind_mesh(bpy,human,rig);tri=None;copy=None;armature_data=None
    try:
        tri=triangulated_copy(bpy,candidate.object)
        copy=rig.copy();armature_data=rig.data.copy();copy.data=armature_data
        copy.name='Armature';copy.parent=None;copy.matrix_world=rig.matrix_world.copy()
        copy.data.pose_position='REST';bpy.context.scene.collection.objects.link(copy)
        world=tri.matrix_world.copy();tri.parent=copy;tri.matrix_world=world;tri.modifiers[0].object=copy
        bpy.ops.object.select_all(action='DESELECT');tri.select_set(True);copy.select_set(True)
        bpy.context.view_layer.objects.active=copy;bpy.context.view_layer.update()
        options=dict(EXPORT_OPTIONS);options['object_types']=set(options['object_types'])
        with portable_export_header(bpy):
            bpy.ops.export_scene.fbx(filepath=str(root/'character.fbx'),**options)
    finally:
        if tri is not None:discard_triangulated_copy(bpy,tri)
        if copy is not None:bpy.data.objects.remove(copy,do_unlink=True)
        if armature_data is not None:bpy.data.armatures.remove(armature_data)
        discard_godot_bind_mesh(bpy,candidate)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            if obj.name in bpy.data.objects:obj.select_set(True)
        bpy.context.view_layer.objects.active=active

