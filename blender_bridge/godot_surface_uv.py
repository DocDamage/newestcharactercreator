"""Read-only original masked surface / saved copy / exported UV comparison."""
from array import array
from pathlib import Path
from typing import Any

from blender_bridge.godot_bind_mesh import SOURCE_ID
from ucc.export.godot_surface_uv import verify_glb_uvs


def surface(mesh: Any) -> tuple:
    if len(mesh.uv_layers)!=1 or mesh.uv_layers.active_index!=0 or not mesh.uv_layers[0].active_render:
        raise ValueError('Native UV gate requires exactly one active/render source UV layer')
    layer=mesh.uv_layers[0];values=array('f',[0.])*(len(layer.data)*2);layer.data.foreach_get('uv',values)
    return (layer.name,tuple(tuple(p.vertices) for p in mesh.polygons),
        tuple(zip(values[::2],values[1::2])),tuple(p.material_index for p in mesh.polygons),
        tuple(None if m is None else m.name for m in mesh.materials))


def verify_source_surface_uv(bpy: Any,human: Any,rig: Any,converted: Any,path: Path) -> dict:
    """Never assign a material, change UVs, or repair a saved copy."""
    if human.data.attributes.get(SOURCE_ID) is not None:raise ValueError('Reserved UV source identity already exists')
    attribute=human.data.attributes.new(SOURCE_ID,'INT','POINT')
    attribute.data.foreach_set('value',list(range(len(human.data.vertices))))
    mods=[human.modifiers[0],human.modifiers[-1]];states=[m.show_viewport for m in mods];pose=rig.data.pose_position
    try:
        rig.data.pose_position='REST'
        for modifier in mods:modifier.show_viewport=False
        bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get();obj=human.evaluated_get(graph)
        mesh=obj.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
        try:
            original=surface(mesh);ids=tuple(int(row.value) for row in mesh.attributes[SOURCE_ID].data)
            if len(ids)!=13380 or len(set(ids))!=13380:raise ValueError('Source UV mask lost vertex identity')
        finally:obj.to_mesh_clear()
    finally:
        human.data.attributes.remove(attribute);rig.data.pose_position=pose
        for modifier,state in zip(mods,states):modifier.show_viewport=state
        bpy.context.view_layer.update()
    actual=surface(converted.data)
    if actual!=original:raise ValueError('Saved raw copy changed original masked UVs or material assignments')
    name,polygons,uvs,_,materials=original
    if len(polygons)!=13378 or len(uvs)!=53512:raise ValueError('Native source UV topology differs from admitted profile')
    bind=[(float(v.co.x),float(v.co.z),-float(v.co.y)) for v in converted.data.vertices]
    report=verify_glb_uvs(path,bind,polygons,uvs,check=lambda:None)
    report.update(uv_layer=name,source_material_slots=len(materials),source_material_names=list(materials),
        source_materials_absent=not materials,source_textured_appearance_verified=False)
    return report
