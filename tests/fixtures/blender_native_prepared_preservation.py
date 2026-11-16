"""Read-only prepared-key/hand/bind preservation audit on real saved scenes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from blender_bridge.expression_policy import PREFIX,TARGETS,keyname
from blender_bridge.face_geometry import key_state,mesh_coordinates,rest_state
from blender_bridge.native_fit_scene import exact_weights_digest,polygon_digest,bone_controls
from blender_bridge.face_operations import state_digest


def observe(path: Path) -> dict:
    bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False)
    human=bpy.data.objects['Human'];rig=bpy.data.objects['Human.rig']
    keys=human.data.shape_keys
    expected={keyname(role,family) for role,family,_ in TARGETS}
    if {key.name for key in keys.key_blocks if key.name.startswith(PREFIX)}!=expected:
        raise ValueError('Native saved character lost the twelve prepared expression keys')
    if any(key.value!=0. for key in keys.key_blocks if key.name in expected):
        raise ValueError('Native skeletal preview changed canonical neutral facial values')
    if keys.animation_data and (keys.animation_data.action or keys.animation_data.drivers or keys.animation_data.nla_tracks):
        raise ValueError('Native skeletal source unexpectedly animates prepared facial controls')
    uv=[]
    for layer in human.data.uv_layers:
        uv.append((layer.name,state_digest([list(row.uv) for row in layer.data])))
    return {'all_keys':{key.name:key_state(key) for key in keys.key_blocks},'mesh':mesh_coordinates(human),
        'key_order':[key.name for key in keys.key_blocks],'relative_keys':keys.use_relative,
        'weights':exact_weights_digest(human),'topology':polygon_digest(human),
        'rest':rest_state(rig),'bone_controls':bone_controls(rig),'uv':uv,
        'materials':[material.name if material else None for material in human.data.materials],
        'parent':human.parent.name if human.parent else None,
        'parent_inverse':[float(v) for row in human.matrix_parent_inverse for v in row],
        'local_matrix':[float(v) for row in human.matrix_basis for v in row]}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    paths=[args.job/'candidate.blend',args.job/'review_motion.blend']
    before={str(path):sha256(path.read_bytes()).hexdigest() for path in paths}
    master=observe(paths[0]);saved=observe(paths[1])
    different=[key for key in master if master[key]!=saved[key]]
    if different:raise ValueError('Native saved prepared-state difference: '+','.join(different))
    assert all(sha256(path.read_bytes()).hexdigest()==before[str(path)] for path in paths)
    result={'status':'REAL_PREPARED_MASTER_NATIVE_SCENE_KEYS_HAND_BIND_AND_UV_PRESERVED',
        'blender_version':bpy.app.version_string,'prepared_expression_keys':12,'total_shape_keys':len(master['all_keys']),
        'family_bones':len(master['rest']),'state_sha256':state_digest(master),
        'original_files_unchanged':before,'read_only':True,'engine_import_verified':False}
    with args.out.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(result['status'],flush=True)
