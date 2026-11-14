"""Nonshipping actual saved-scene corruption tests; never compatibility assets."""
from pathlib import Path
from hashlib import sha256
import argparse,json,sys,struct
import bpy
from mathutils import Quaternion


def author_faults(scene,policy_path,mapping_path,folder,cases=('helper_ulp','weight_ulp','deform_flag','rest_roll','action','polygon')):
    before={str(p):sha256(p.read_bytes()).hexdigest() for p in (scene,policy_path,mapping_path)}
    policy=json.loads(policy_path.read_text());mapping=json.loads(mapping_path.read_text())
    hand=policy['chain']['hand'];mapped={p['target'] for p in mapping['pairs']}
    folder.mkdir(exist_ok=False);rows=[]
    for case in cases:
        bpy.ops.wm.open_mainfile(filepath=str(scene),load_ui=False)
        rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
        human=next(o for o in bpy.data.objects if o.type=='MESH' and len(o.data.vertices)>100)
        helper=rig.data.bones[hand].parent
        if helper is None or helper.name in mapped:raise RuntimeError('Fault test needs the actual neutral wrist helper')
        if case=='helper_ulp':rig.pose.bones[helper.name].scale.x=1.+2.**-23
        if case=='deform_flag':helper.use_deform=not helper.use_deform
        if case=='weight_ulp':
            group=human.vertex_groups[helper.name]
            vertex,weight=next((v,g.weight) for v in human.data.vertices for g in v.groups if g.group==group.index and .05<g.weight<.95)
            bits=struct.unpack('<I',struct.pack('<f',weight))[0]
            changed=struct.unpack('<f',struct.pack('<I',bits+1))[0]
            group.add([vertex.index],changed,'REPLACE')
        if case=='rest_roll':
            bpy.context.view_layer.objects.active=rig;rig.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT');rig.data.edit_bones[helper.name].roll+=.05;bpy.ops.object.mode_set(mode='OBJECT')
        if case=='action':
            action=rig.animation_data.action
            curves=[c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves
                    if c.data_path==rig.pose.bones[hand].path_from_id('rotation_quaternion')]
            curves=sorted(curves,key=lambda c:c.array_index)
            assert len(curves)==4 and all(len(c.keyframe_points)>=8 for c in curves)
            q=Quaternion(tuple(c.keyframe_points[7].co.y for c in curves))@Quaternion((1,0,0),.02)
            for c,v in zip(curves,q.normalized()):c.keyframe_points[7].co.y=v
        if case=='polygon':human.data.polygons[0].flip();human.data.update()
        path=folder/f'{case}.blend'
        assert not path.exists() and 'FINISHED' in bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=False,copy=True)
        rows.append({'case':case,'scene':path.name,'sha256':sha256(path.read_bytes()).hexdigest()})
    assert before=={p:sha256(Path(p).read_bytes()).hexdigest() for p in before}
    result={'scope':'ACTUAL_SCENE_FAULT_INJECTION_NOT_ANIMATION_OR_ASSET_COMPATIBILITY','originals_unchanged':True,'faults':rows}
    (folder/'manifest.json').write_text(json.dumps(result,indent=2));print('ACTUAL_FIT_FAULT_COPIES_AUTHORED',len(rows),flush=True)


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:];parser=argparse.ArgumentParser()
    for name in ('scene','policy','mapping','folder'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--cases',nargs='+',choices=('helper_ulp','weight_ulp','deform_flag','rest_roll','action','polygon'),default=None)
    a=parser.parse_args(args)
    if a.cases is None:author_faults(a.scene,a.policy,a.mapping,a.folder)
    else:author_faults(a.scene,a.policy,a.mapping,a.folder,tuple(a.cases))
