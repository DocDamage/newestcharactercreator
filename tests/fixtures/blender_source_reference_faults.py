"""Real saved faults on an original generated neutral master; never shipping assets."""
import argparse
from hashlib import sha256
from pathlib import Path
import sys
import bpy


def create(master: Path, folder: Path) -> None:
    folder.mkdir(exist_ok=False)
    original = sha256(master.read_bytes()).hexdigest()
    for kind in ('unregistered_neutral', 'assigned_action', 'tiny_pose'):
        bpy.ops.wm.open_mainfile(filepath=str(master))
        rigs = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        if len(rigs) != 1 or bpy.data.actions:
            raise RuntimeError('Fault author requires one actual original neutral rig')
        if kind == 'unregistered_neutral':
            bpy.context.scene['ucc_original_reference_fault'] = 'unregistered neutral resave'
        elif kind == 'assigned_action':
            rigs[0].animation_data_create().action = bpy.data.actions.new('Original CI forbidden Action')
        else:
            rigs[0].pose.bones[0].location.x = .000005
        bpy.ops.wm.save_as_mainfile(filepath=str(folder/(kind+'.blend')), compress=False)
    if sha256(master.read_bytes()).hexdigest() != original:
        raise RuntimeError('Fault author changed the original master')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    create(args.master, args.folder)
