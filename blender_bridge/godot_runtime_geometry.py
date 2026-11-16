"""Private bound-smoothing input construction in Blender's bundled NumPy.

This is not a shipping engine implementation or distribution/license approval.
Every produced reconstruction must be checked against actual Blender output.
"""
from pathlib import Path
from typing import Any
import numpy as np


def unit(values: np.ndarray) -> np.ndarray:
    length=np.sqrt(np.sum(values*values,axis=1,dtype=np.float32))
    return np.divide(values,length[:,None],out=np.zeros_like(values),where=length[:,None]>0.)


def smooth(points: np.ndarray, edges: np.ndarray) -> np.ndarray:
    result=points.copy();ids=edges.reshape(-1)
    count=np.bincount(ids,minlength=len(points)).astype(np.float32)
    factor=np.float32(.5)/np.maximum(count,np.float32(1.))
    for _ in range(5):
        delta=result[edges[:,1]]-result[edges[:,0]]
        values=np.stack((delta,-delta),axis=1).reshape(-1,3)
        additions=np.zeros_like(result);np.add.at(additions,ids,values)
        result=result+additions*factor[:,None]
    return result


def frames(points: np.ndarray, previous: np.ndarray, current: np.ndarray,
           following: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    left=unit(points[previous]-points[current]);right=unit(points[current]-points[following])
    normal=unit(np.cross(left,right));axis=unit(left+right);other=np.cross(normal,axis)
    matrices=np.stack((axis,other,normal),axis=2)
    angles=np.arccos(np.clip(np.sum(left*right,axis=1,dtype=np.float32),-1.,1.)).astype(np.float32)
    valid=np.any(np.abs(left-right)>np.float32(np.finfo(np.float32).eps*10),axis=1)
    angles[~valid]=0.;matrices[~valid]=np.eye(3,dtype=np.float32)
    return matrices,angles


def binding(rest: np.ndarray, edges: np.ndarray, previous: np.ndarray,
            current: np.ndarray, following: np.ndarray) -> np.ndarray:
    neutral=smooth(rest,edges);matrices,_=frames(neutral,previous,current,following)
    good=np.linalg.det(matrices)!=0.;inverse=np.transpose(matrices,(0,2,1)).copy()
    inverse[good]=np.linalg.inv(matrices[good])
    return np.einsum('nij,nj->ni',inverse,rest[current]-neutral[current]).astype(np.float32)


def reconstruct(raw: np.ndarray, edges: np.ndarray, previous: np.ndarray,
                current: np.ndarray, following: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    positions=smooth(raw,edges);matrices,weights=frames(positions,previous,current,following)
    total=np.zeros(len(raw),dtype=np.float32);np.add.at(total,current,weights)
    fractions=np.divide(weights,total[current],out=np.zeros_like(weights),where=total[current]>0.)
    correction=np.einsum('nij,nj->ni',matrices,offsets).astype(np.float32)*fractions[:,None]
    np.add.at(positions,current,correction)
    if not np.isfinite(positions).all():raise ValueError('Runtime reconstruction produced nonfinite positions')
    return positions


def sampled_mesh(bpy: Any, human: Any) -> tuple[np.ndarray,np.ndarray]:
    bpy.context.view_layer.update();obj=human.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=obj.to_mesh()
    try:
        if len(mesh.vertices)!=13380:raise ValueError('Runtime source lost complete visible surface')
        p=np.empty((13380,3),dtype=np.float32);n=np.empty_like(p)
        mesh.vertices.foreach_get('co',p.reshape(-1));mesh.vertex_normals.foreach_get('vector',n.reshape(-1))
        if not np.isfinite(p).all() or not np.isfinite(n).all():raise ValueError('Nonfinite runtime source geometry')
        return p,n
    finally:obj.to_mesh_clear()


def capture_binding(bpy: Any, human: Any, rig: Any, modifier: Any) -> dict:
    pose=rig.data.pose_position;visible=modifier.show_viewport
    try:
        rig.data.pose_position='REST';modifier.show_viewport=False;bpy.context.view_layer.update()
        obj=human.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=obj.to_mesh()
        try:
            rest=np.asarray([v.co[:] for v in mesh.vertices],dtype=np.float32)
            edges=np.asarray([e.vertices[:] for e in mesh.edges],dtype=np.int32)
            previous=[];current=[];following=[];face_ids=[];ranges=[];cursor=0
            for face in mesh.polygons:
                ids=list(face.vertices);ranges.append((cursor,len(ids)));cursor+=len(ids)
                for i,vertex in enumerate(ids):
                    previous.append(ids[i-1]);current.append(vertex);following.append(ids[(i+1)%len(ids)]);face_ids.append(face.index)
            if (rest.shape!=(13380,3) or len(ranges)!=13378 or len(current)!=53512
                    or any(not p.use_smooth for p in mesh.polygons) or any(e.use_edge_sharp for e in mesh.edges)
                    or any('normal' in a.name.lower() for a in mesh.attributes)):
                raise ValueError('Unsupported runtime topology or custom/split normal profile')
        finally:obj.to_mesh_clear()
    finally:
        modifier.show_viewport=visible;rig.data.pose_position=pose;bpy.context.view_layer.update()
    previous,current,following,face_ids=[np.asarray(x,dtype=np.int32) for x in (previous,current,following,face_ids)]
    offsets=binding(rest,edges,previous,current,following)
    return {'rest':rest,'edges':edges,'previous':previous,'current':current,'following':following,
            'face_ids':face_ids,'face_ranges':np.asarray(ranges,dtype=np.uint32),'offsets':offsets}


def write_binding(root: Path, data: dict) -> None:
    def write(name: str, values: np.ndarray) -> None:
        with (root/name).open('xb') as stream:values.tofile(stream)
    count=len(data['rest']);current=data['current'];links=[[] for _ in range(count)]
    for a,b in data['edges']:links[a].append(int(b));links[b].append(int(a))
    def packed(rows: list[list[int]],prefix: str,name: str) -> None:
        cursor=0;ranges=[];flat=[]
        for row in rows:ranges.append((cursor,len(row)));flat.extend(row);cursor+=len(row)
        write(prefix+'_ranges.u32',np.asarray(ranges,dtype='<u4'));write(name,np.asarray(flat,dtype='<u4'))
    packed(links,'neighbor','neighbors.u32');links=[[] for _ in range(count)]
    for corner,vertex in enumerate(current):links[vertex].append(corner)
    packed(links,'corner','corner_indices.u32')
    write('corners.u32',np.column_stack((data['previous'],current,data['following'],np.zeros(len(current),dtype=np.int32))).astype('<u4'))
    offsets=np.ones((len(current),4),dtype='<f4');offsets[:,:3]=data['offsets'];write('offsets_vec4.f32',offsets)
    write('face_ranges.u32',data['face_ranges'].astype('<u4'));write('face_vertices.u32',current.astype('<u4'))
    write('face_ids.u32',data['face_ids'].astype('<u4'))
