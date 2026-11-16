"""Sample the actual original MPFB deformation, never the exported mesh."""
from array import array
from hashlib import sha256
import math,sys
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh,discard_godot_bind_mesh
from blender_bridge.expression_clip_action import peaks
from blender_bridge.expression_geometry import macro_context
from blender_bridge.expression_policy import keyname
from ucc.export.unity_runtime_source import VERTICES,CASES,VECTOR_BYTES

ATTRIBUTE='_UCC_UNITY_RUNTIME_SOURCE_VERTEX_V1'


def packed(vectors) -> bytes:
    values=array('f',(float(v) for point in vectors for v in point))
    if len(values)!=VERTICES*3 or any(not math.isfinite(v) for v in values):
        raise ValueError('Unity runtime source vectors are incomplete or nonfinite')
    if sys.byteorder!='little':values.byteswap()
    return values.tobytes()


def samples(bpy,human,rig,targets,parameters: dict,bind: dict):
    from mathutils import Matrix
    candidate=build_godot_bind_mesh(bpy,human,rig)
    try:expected_ids=candidate.source_vertex_ids
    finally:discard_godot_bind_mesh(bpy,candidate)
    if human.data.attributes.get(ATTRIBUTE) is not None:raise ValueError('Reserved runtime source vertex attribute already exists')
    keys={k.name:k for k in human.data.shape_keys.key_blocks if k.name.startswith('UCC_EXPR_V1_')}
    if set(keys)!=set(bind['morphs']) or len(rig.pose.bones)!=163:raise ValueError('Runtime source rig/control identities differ')
    basis={b.name:b.matrix_basis.copy() for b in rig.pose.bones};rest={b.name:b.matrix.copy() for b in rig.pose.bones}
    original_values={name:key.value for name,key in keys.items()}
    _,race=macro_context(human,targets)
    combined={keyname(role,family):value for (role,family),value in peaks(parameters,race).items()}
    cases=[('neutral',None,{})]+[('bone-'+b.name,b.name,{}) for b in rig.pose.bones]
    cases += [('shape-'+name,None,{name:.5}) for name in sorted(keys)]
    cases += [('saved-expression',None,combined),('neutral-end',None,{})]
    if len(cases)!=CASES:raise ValueError('Incomplete runtime source diagnostic cases')
    attribute=human.data.attributes.new(ATTRIBUTE,'INT','POINT')
    attribute.data.foreach_set('value',list(range(len(human.data.vertices))))
    try:
        for index,(name,bone,shapes) in enumerate(cases):
            for b in rig.pose.bones:b.matrix_basis=basis[b.name]
            for key in keys.values():key.value=0.
            if bone:rig.pose.bones[bone].matrix_basis=Matrix.Rotation(math.radians(20),4,'X')
            for control,value in shapes.items():keys[control].value=value
            bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get();obj=human.evaluated_get(graph)
            mesh=obj.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
            try:
                ids=mesh.attributes.get(ATTRIBUTE)
                if (len(mesh.vertices)!=VERTICES or len(mesh.polygons)!=13378 or ids is None
                        or tuple(row.value for row in ids.data)!=expected_ids
                        or [list(p.vertices) for p in mesh.polygons]!=bind['quads']):
                    raise ValueError('Actual runtime source lost original point/quad correspondence')
                # This profile has smooth geometric point normals, without split-normal overrides.
                normals=mesh.vertex_normals
                if any(tuple(mesh.corner_normals[loop.index].vector)!=tuple(normals[loop.vertex_index].vector) for loop in mesh.loops):
                    raise ValueError('Runtime source has unsupported split or non-geometric corner normals')
                normal_matrix=human.matrix_world.to_3x3().inverted().transposed()
                world_normals=[(normal_matrix@n.vector).normalized() for n in normals]
                if any(abs(n.length-1)>1e-4 for n in world_normals):raise ValueError('Actual runtime source normal is not unit length')
                positions=packed(human.matrix_world@v.co for v in mesh.vertices);normal_bytes=packed(world_normals)
            finally:obj.to_mesh_clear()
            delta=(rig.matrix_world@rig.pose.bones[bone].matrix@rest[bone].inverted()@rig.matrix_world.inverted()
                   if bone else Matrix.Identity(4))
            row={'name':name,'bone':bone,'delta_blender_world':[float(v) for line in delta for v in line],
                'shapes':[{'name':k,'value':float(shapes.get(k,0.))} for k in sorted(keys)],
                'positions_offset':index*VECTOR_BYTES*2,'normals_offset':index*VECTOR_BYTES*2+VECTOR_BYTES,
                'positions_sha256':sha256(positions).hexdigest(),'normals_sha256':sha256(normal_bytes).hexdigest()}
            yield row,positions,normal_bytes
    finally:
        for b in rig.pose.bones:b.matrix_basis=basis[b.name]
        for name,key in keys.items():key.value=original_values[name]
        human.data.attributes.remove(attribute);bpy.context.view_layer.update()
