"""Blender-only faults on disposable real hand revisions; never shipping assets."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Quaternion

OWN='UCC_HAND_ASSET_LEFT_V1'
FAULTS=('one-ulp-value','key-coordinate','one-ulp-weight','rest-roll','uv','material','saved-pose','unrelated-key')


def next_float(value):
    bits=struct.unpack('<I',struct.pack('<f',value))[0]
    return struct.unpack('<f',struct.pack('<I',bits+1))[0]


def corrupt(source,output,fault):
    if output.exists() or output.is_symlink():raise ValueError('Fault fixture refuses to overwrite output')
    bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
    humans=[o for o in bpy.data.objects if o.type=='MESH' and o.parent and o.parent.type=='ARMATURE']
    if len(humans)!=1:raise ValueError('Real hand fault fixture needs one bound humanoid')
    human=humans[0];rig=human.parent;key=human.data.shape_keys.key_blocks[OWN]
    basis=human.data.shape_keys.key_blocks[0]
    if fault=='one-ulp-value':key.value=next_float(key.value)
    elif fault=='key-coordinate':
        index=next(i for i,v in enumerate(key.data) if tuple(v.co)!=tuple(basis.data[i].co))
        key.data[index].co.x+=.0005
    elif fault=='one-ulp-weight':
        vertex=next(v for v in human.data.vertices if tuple(key.data[v.index].co)!=tuple(basis.data[v.index].co)
                    and any(.01<g.weight<.99 for g in v.groups))
        group=next(g for g in vertex.groups if .01<g.weight<.99)
        human.vertex_groups[group.group].add([vertex.index],next_float(group.weight),'REPLACE')
    elif fault=='rest-roll':
        bpy.context.view_layer.objects.active=rig;rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT');rig.data.edit_bones['wrist.L'].roll+=.001;bpy.ops.object.mode_set(mode='OBJECT')
    elif fault=='uv':human.data.uv_layers[0].data[100].uv.x+=.001
    elif fault=='material':human.data.materials.append(bpy.data.materials.new('UCC_TEST_MATERIAL_FAULT'))
    elif fault=='saved-pose':
        bone=rig.pose.bones['wrist.L'];bone.rotation_mode='QUATERNION';bone.rotation_quaternion=Quaternion((1.,0.,0.),.01)
    elif fault=='unrelated-key':
        extra=human.shape_key_add(name='UCC_TEST_UNRELATED_KEY_FAULT',from_mix=False);extra.value=.1;extra.data[0].co.x+=.001
    else:raise ValueError('Unknown hand revision fault')
    bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=False)
    if not output.is_file() or output.stat().st_size<1024:raise ValueError('Fault scene was not saved')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    source=args.source.resolve(strict=True);before=sha256(source.read_bytes()).hexdigest()
    args.output.mkdir(exist_ok=False);rows={}
    for fault in FAULTS:
        path=args.output/(fault+'.blend');corrupt(source,path,fault)
        rows[fault]={'file':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}
    if sha256(source.read_bytes()).hexdigest()!=before:raise ValueError('Fault fixture changed source')
    with (args.output/'faults.json').open('x') as stream:json.dump(rows,stream,indent=2)
    print('EIGHT_REAL_HAND_REVISION_FAULTS_CREATED_ORIGINAL_UNCHANGED',flush=True)


if __name__=='__main__':main()
