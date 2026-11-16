"""Separate exact Blender source weights from deliberate glTF serialization.

Source geometry stays under the fixed 1um check. Exported relative weights
stay under the existing 1e-6 weight check and require actual engine geometry
verification; their float32 normalization is not original Blender arithmetic.
"""
from pathlib import Path
from typing import Any
import math,struct
import numpy as np
from blender_bridge.godot_bind_mesh import SOURCE_ID
from blender_bridge.godot_skin_weights import normalize_weights,serialization_weights
from ucc.export.godot_skin_evidence import _DenseSkin


def original_weights(human: Any,rig: Any,ids: tuple) -> list[tuple]:
    deform={b.name for b in rig.data.bones if b.use_deform};groups={g.index:g.name for g in human.vertex_groups}
    return [tuple((groups[g.group],float(g.weight)) for g in human.data.vertices[int(i)].groups
                  if groups[g.group] in deform and g.weight>0) for i in ids]


def apply_weights(target: Any,weights: list[tuple],*,serialized: bool) -> None:
    for index,rows in enumerate(weights):
        values=serialization_weights(normalize_weights(rows)[0]) if serialized else rows
        for name,weight in values:target.vertex_groups[name].add([index],weight,'REPLACE')


def source_ids(bpy: Any,human: Any,rig: Any) -> tuple[int,...]:
    if human.data.attributes.get(SOURCE_ID) is not None:raise ValueError('Reserved source ID attribute already exists')
    attribute=human.data.attributes.new(SOURCE_ID,'INT','POINT');attribute.data.foreach_set('value',list(range(len(human.data.vertices))))
    mods=[human.modifiers[0],human.modifiers[-1]];states=[m.show_viewport for m in mods];pose=rig.data.pose_position
    try:
        rig.data.pose_position='REST'
        for mod in mods:mod.show_viewport=False
        bpy.context.view_layer.update();obj=human.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=obj.to_mesh()
        try:
            data=mesh.attributes.get(SOURCE_ID)
            if data is None:raise ValueError('Source mask lost original indexing')
            ids=tuple(int(row.value) for row in data.data)
            if len(ids)!=13380 or len(set(ids))!=13380:raise ValueError('Source mask changed complete vertex IDs')
            return ids
        finally:obj.to_mesh_clear()
    finally:
        human.data.attributes.remove(attribute);rig.data.pose_position=pose
        for mod,state in zip(mods,states):mod.show_viewport=state
        bpy.context.view_layer.update()


def verify_original_weights(converted: Any,rig: Any,weights: list[tuple]) -> None:
    deform={b.name for b in rig.data.bones if b.use_deform};groups={g.index:g.name for g in converted.vertex_groups}
    for vertex,expected in zip(converted.data.vertices,weights):
        actual={groups[g.group]:float(g.weight) for g in vertex.groups if groups[g.group] in deform and g.weight>0}
        if actual!=dict(expected):raise ValueError('Saved Blender raw copy lost exact original source weights')


def verify_serialized_weights(path: Path,bind: np.ndarray,weights: list[tuple]) -> float:
    reader=_DenseSkin(path);doc=reader.document;primitive=doc['meshes'][0]['primitives'][0];attrs=primitive['attributes']
    joints=doc['skins'][0]['joints'];names=[doc['nodes'][i]['name'] for i in joints]
    def key(point):return struct.pack('<3f',*(0. if v==0 else v for v in point)).hex()
    indices={key(point):index for index,point in enumerate(bind)}
    positions=reader.rows(attrs['POSITION'],'VEC3',(5126,))
    bone_rows=[reader.rows(attrs['JOINTS_'+str(i)],'VEC4',(5121,5123)) for i in range(2)]
    values=[reader.rows(attrs['WEIGHTS_'+str(i)],'VEC4',(5126,)) for i in range(2)]
    maximum=0.;covered=set()
    for vertex,position in enumerate(positions):
        index=indices.get(key(position))
        if index is None:raise ValueError('GLB weight check lost exact bind/source identity')
        covered.add(index);expected=dict(normalize_weights(weights[index])[0]);actual={}
        for row in range(2):
            for bone,weight in zip(bone_rows[row][vertex],values[row][vertex]):
                if weight:
                    if not 0<=bone<len(names) or names[bone] in actual:raise ValueError('GLB has invalid/duplicate positive influence')
                    actual[names[bone]]=weight
        if set(actual)!=set(expected):raise ValueError('GLB changed original positive influence identities')
        error=max(abs(actual[name]-value) for name,value in expected.items())
        if not math.isfinite(error) or error>1e-6 or abs(sum(actual.values())-1.)>1e-6:
            raise ValueError('GLB serialization exceeds fixed original relative-weight limit')
        maximum=max(maximum,error)
    if len(covered)!=13380:raise ValueError('GLB weight check lost full original surface coverage')
    return maximum
