"""Copy actual loop triangles, UV corners, normals and keys for engine export."""
from typing import Any

NAME='UCC_Private_Triangulated_Export'


def triangulated_copy(bpy: Any,source: Any) -> Any:
    """Use Blender's measured triangulation instead of an exporter's quad split.

    The source must already be an admitted bind mesh. No target, rig, vertex
    location or weight is synthesized. The caller owns this temporary copy and
    must independently check the exported file and complete source preservation.
    """
    if bpy.data.objects.get(NAME) or bpy.data.meshes.get(NAME):raise ValueError('Reserved triangulated export name exists')
    mesh=source.data;mesh.calc_loop_triangles()
    if len(mesh.uv_layers)!=1 or len(mesh.color_attributes):raise ValueError('Triangulated export needs one UV set and no unsupported vertex colors')
    if len(source.modifiers)!=1 or source.modifiers[0].type!='ARMATURE':raise ValueError('Triangulated export needs one admitted linear skin modifier')
    triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
    uv=[tuple(mesh.uv_layers[0].data[i].uv) for t in mesh.loop_triangles for i in t.loops]
    normals=[tuple(mesh.corner_normals[i].vector) for t in mesh.loop_triangles for i in t.loops]
    polygons=[mesh.polygons[t.polygon_index] for t in mesh.loop_triangles]
    data=bpy.data.meshes.new(NAME);obj=None
    try:
        data.from_pydata([tuple(v.co) for v in mesh.vertices],[],triangles);data.update()
        if len(data.vertices)!=len(mesh.vertices) or len(data.polygons)!=len(triangles):raise ValueError('Triangulation changed vertex/triangle coverage')
        for polygon,original in zip(data.polygons,polygons):
            polygon.material_index=original.material_index;polygon.use_smooth=original.use_smooth
        for material in mesh.materials:data.materials.append(material)
        layer=data.uv_layers.new(name=mesh.uv_layers[0].name)
        for loop,value in zip(layer.data,uv):loop.uv=value
        data.normals_split_custom_set(normals)
        obj=bpy.data.objects.new(NAME,data);bpy.context.scene.collection.objects.link(obj)
        obj.parent=source.parent;obj.matrix_parent_inverse=source.matrix_parent_inverse.copy();obj.matrix_basis=source.matrix_basis.copy()
        for group in source.vertex_groups:obj.vertex_groups.new(name=group.name)
        for vertex in mesh.vertices:
            for group in vertex.groups:obj.vertex_groups[group.group].add([vertex.index],group.weight,'REPLACE')
        for original in mesh.shape_keys.key_blocks:
            key=obj.shape_key_add(name=original.name,from_mix=False)
            key.data.foreach_set('co',[value for point in original.data for value in point.co])
            key.slider_min=original.slider_min;key.slider_max=original.slider_max;key.value=original.value
            key.interpolation=original.interpolation;key.mute=original.mute;key.vertex_group=original.vertex_group
        for original in mesh.shape_keys.key_blocks:obj.data.shape_keys.key_blocks[original.name].relative_key=obj.data.shape_keys.key_blocks[original.relative_key.name]
        original=source.modifiers[0];skin=obj.modifiers.new(original.name,'ARMATURE');skin.object=original.object
        for name in ('use_vertex_groups','use_bone_envelopes','use_deform_preserve_volume','use_multi_modifier','show_viewport','show_render'):
            setattr(skin,name,getattr(original,name))
        if any(tuple(a.co)!=tuple(b.co) for a,b in zip(mesh.vertices,data.vertices)):raise ValueError('Triangulated copy moved source vertices')
        if [tuple(p.vertices) for p in data.polygons]!=triangles:raise ValueError('Triangulated copy changed measured corner order')
        return obj
    except BaseException:
        if obj is not None:bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.meshes.remove(data);raise


def discard_triangulated_copy(bpy: Any,obj: Any) -> None:
    if obj.name!=NAME or obj.data.name!=NAME:raise ValueError('Triangulated cleanup refuses an unowned object')
    data=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(data)
