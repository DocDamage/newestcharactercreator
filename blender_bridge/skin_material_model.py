"""First-party body material construction and exact nonmaterial preservation."""
import json
from typing import Any
from blender_bridge.face_geometry import invariant_state,key_state,mesh_coordinates
from blender_bridge.face_materials import signature,properties
from blender_bridge.face_operations import state_digest
from ucc.core.skin_material import SkinMaterialSpec,POLICY,canonical_bytes

TAGS={'ucc_body_material_policy','ucc_body_material_spec','ucc_body_material_spec_sha256'}


def material_name(spec: SkinMaterialSpec) -> str:return 'UCC_BODY_MAT_V1_'+spec.sha256[:24]


def create_material(bpy: Any,spec: SkinMaterialSpec,*,name: str | None=None) -> Any:
    name=material_name(spec) if name is None else name
    if bpy.data.materials.get(name) is not None:raise ValueError('Reserved body material name already exists')
    material=bpy.data.materials.new(name);material.use_nodes=True;material.use_backface_culling=True
    material.diffuse_color=spec.linear_rgba
    if hasattr(material,'roughness'):material.roughness=spec.roughness
    if hasattr(material,'metallic'):material.metallic=0.
    material.node_tree.nodes.clear()
    shader=material.node_tree.nodes.new('ShaderNodeBsdfPrincipled');output=material.node_tree.nodes.new('ShaderNodeOutputMaterial')
    shader.inputs['Base Color'].default_value=spec.linear_rgba;shader.inputs['Roughness'].default_value=spec.roughness
    shader.inputs['Metallic'].default_value=0.;shader.inputs['Alpha'].default_value=1.
    material.node_tree.links.new(shader.outputs['BSDF'],output.inputs['Surface'])
    material['ucc_body_material_policy']=POLICY
    material['ucc_body_material_spec']=canonical_bytes(spec.to_dict()).decode()
    material['ucc_body_material_spec_sha256']=spec.sha256
    return material


def shader_snapshot(material: Any) -> dict:
    data=properties(material);data['name']='<BODY_MATERIAL>'
    if 'node_tree' in data:data['node_tree']='<BODY_TREE>'
    nodes=[]
    for node in material.node_tree.nodes:
        if getattr(node,'node_tree',None) is not None:raise ValueError('Body material cannot contain nested groups')
        nodes.append({'type':node.bl_idname,'properties':properties(node),
            'inputs':[properties(socket) for socket in node.inputs],'outputs':[properties(socket) for socket in node.outputs]})
    return {'properties':data,'nodes':nodes,'links':[(l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier) for l in material.node_tree.links],
        'tags':{name:material[name] for name in material.keys()}}


def checked_owned_material(bpy: Any,human: Any) -> SkinMaterialSpec | None:
    if not human.data.materials:
        if any(p.material_index!=0 for p in human.data.polygons):raise ValueError('Unassigned body has unexpected polygon material indices')
        return None
    if len(human.data.materials)!=1 or human.data.materials[0] is None or any(p.material_index!=0 for p in human.data.polygons):
        raise ValueError('Body material edit does not replace existing arbitrary or multiple materials')
    material=human.data.materials[0];raw=material.get('ucc_body_material_spec')
    if (material.get('ucc_body_material_policy')!=POLICY or type(raw) is not str or len(raw)>4096
            or set(material.keys())!=TAGS or material.library or material.override_library or material.users!=1):
        raise ValueError('Existing body material is not an exclusive supported first-party material')
    spec=SkinMaterialSpec.from_dict(json.loads(raw))
    if (raw!=canonical_bytes(spec.to_dict()).decode() or material.name!=material_name(spec)
            or material.get('ucc_body_material_spec_sha256')!=spec.sha256):raise ValueError('Existing body material identity differs from its explicit parameters')
    expected=create_material(bpy,spec,name='UCC_BODY_MATERIAL_INTERNAL_EXPECTED')
    try:
        if shader_snapshot(material)!=shader_snapshot(expected):raise ValueError('Existing body shader differs from the complete supported material definition')
    finally:bpy.data.materials.remove(expected)
    return spec


def nonmaterial_state(bpy: Any,human: Any,rig: Any,targets: Any,allowed_materials: set[str]) -> str:
    state=invariant_state(bpy,human,rig,targets)
    state.pop('materials');state.pop('material_state')
    state['coordinates']=mesh_coordinates(human)
    state['all_keys']={key.name:key_state(key) for key in human.data.shape_keys.key_blocks}
    state['all_key_order']=[key.name for key in human.data.shape_keys.key_blocks]
    state['active_key']=human.active_shape_key_index
    state['uv_flags']=[(layer.name,layer.active_render) for layer in human.data.uv_layers]
    materials=signature(bpy)
    materials['materials']={name:value for name,value in materials['materials'].items() if name not in allowed_materials}
    state['unrelated_materials_images']=materials
    state['object_flags_material_slots']={obj.name:{'hide_render':obj.hide_render,'hide_viewport':obj.hide_viewport,
        'hide':obj.hide_get(),'data':None if obj.data is None else obj.data.name,
        'materials':[None if slot.material is None else slot.material.name for slot in obj.material_slots] if obj!=human else []}
        for obj in bpy.data.objects}
    return state_digest(state)


def apply_material(bpy: Any,human: Any,spec: SkinMaterialSpec,previous: SkinMaterialSpec | None) -> Any:
    if previous==spec:return human.data.materials[0]
    material=create_material(bpy,spec)
    human.data.materials.clear();human.data.materials.append(material)
    return material
