"""Actual admitted MPFB bind geometry; no runtime/library or replacement assets."""
import math
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh,discard_godot_bind_mesh


def reference(bpy,human,rig,*,master_sha: str,request_sha: str,spec) -> tuple[dict,dict]:
    candidate=build_godot_bind_mesh(bpy,human,rig)
    try:
        obj=candidate.object;mesh=obj.data;mesh.calc_loop_triangles()
        names=[bone.name for bone in rig.data.bones];groups={group.index:group.name for group in obj.vertex_groups}
        points=[list(obj.matrix_world@vertex.co) for vertex in mesh.vertices]
        weights=[]
        for vertex in mesh.vertices:
            row=sorted((groups[g.group],float(g.weight)) for g in vertex.groups if groups[g.group] in names and g.weight>0)
            if not 1<=len(row)<=8 or any(not math.isfinite(w) for _,w in row) or sum(w for _,w in row)<=.0001:
                raise ValueError('Unity source has unsupported or nonfinite deform influences')
            weights.append(row)
        quads=[list(face.vertices) for face in mesh.polygons]
        if len(points)!=13380 or len(names)!=163 or len(quads)!=13378 or any(len(face)!=4 for face in quads):
            raise ValueError('Unity source differs from the admitted MPFB human topology')
        uv=mesh.uv_layers.active
        if len(mesh.uv_layers)!=1 or uv is None:raise ValueError('Unity source needs its complete original UV set')
        result={'schema_version':1,'policy':'UCC_UNITY_ORIGINAL_BIND_REFERENCE_V1','master_sha256':master_sha,'request_sha256':request_sha,
            'blender_version':bpy.app.version_string,'blender_build':bpy.app.build_hash.decode(),'material_spec':spec.to_dict(),
            'vertices':points,'quads':quads,'triangles':[list(t.vertices) for t in mesh.loop_triangles],
            'corners':[{'vertices':list(t.vertices),'uv':[list(uv.data[i].uv) for i in t.loops]} for t in mesh.loop_triangles],
            'weights':weights,'morphs':{key.name:[list(obj.matrix_world.to_3x3()@(p.co-v.co)) for p,v in zip(key.data,mesh.vertices)]
                for key in mesh.shape_keys.key_blocks if key.name!='Basis'},
            'bones':[{'name':bone.name,'parent':bone.parent.name if bone.parent else None,
                      'world':[float(value) for row in (rig.matrix_world@bone.matrix_local) for value in row]} for bone in rig.data.bones],
            'candidate_observation':candidate.observation,'engine_import_verified':False}
        if len(result['morphs'])!=12:raise ValueError('Unity source needs the twelve canonical facial controls')
        native={'schema_version':1,'policy':'UCC_UNITY_SOURCE_WEIGHTS_V1','master_sha256':master_sha,'request_sha256':request_sha,
            'vertices':[{'position':{'x':-p[0],'y':p[2],'z':-p[1]},
                         'weights':[{'bone':name,'weight':weight/sum(w for _,w in row)} for name,weight in row]}
                        for p,row in zip(points,weights)]}
        return result,native
    finally:discard_godot_bind_mesh(bpy,candidate)


def export_fbx(bpy,human,rig,path) -> None:
    from blender_bridge.triangulated_export import triangulated_copy,discard_triangulated_copy
    candidate=build_godot_bind_mesh(bpy,human,rig);triangulated=None
    selected=list(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
    try:
        triangulated=triangulated_copy(bpy,candidate.object)
        bpy.ops.object.select_all(action='DESELECT');triangulated.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=rig
        bpy.ops.export_scene.fbx(filepath=str(path),check_existing=False,use_selection=True,object_types={'ARMATURE','MESH'},
            apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',global_scale=1.,axis_forward='-Z',axis_up='Y',
            add_leaf_bones=False,use_armature_deform_only=False,bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=False,
            path_mode='AUTO',embed_textures=False)
    finally:
        if triangulated is not None:discard_triangulated_copy(bpy,triangulated)
        discard_godot_bind_mesh(bpy,candidate)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            if obj.name in bpy.data.objects:obj.select_set(True)
        bpy.context.view_layer.objects.active=active
