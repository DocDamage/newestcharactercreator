"""Original non-shipping multi-root FBX fixture; not humanoid/pack evidence."""
from pathlib import Path
import math
import sys

import bpy


def author(output: Path) -> None:
    output.mkdir(parents=True,exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.render.fps=30
    arm=bpy.data.armatures.new("SyntheticNativeFbx")
    rig=bpy.data.objects.new("Armature",arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    a=arm.edit_bones.new("RootA");a.head=(0,0,0);a.tail=(0,0,1)
    b=arm.edit_bones.new("ChildA");b.head=(0,0,1);b.tail=(0,0,2);b.parent=a
    c=arm.edit_bones.new("RootB");c.head=(1,0,0);c.tail=(1,0,1)
    bpy.ops.object.mode_set(mode="OBJECT")
    for frame in range(1,301):
        rig.location.x=(frame-1)*.003
        rig.keyframe_insert("location",frame=frame)
        for i,bone in enumerate(rig.pose.bones):
            bone.rotation_mode="XYZ"
            bone.rotation_euler.x=.15*math.sin((frame-1)*.02+i)
            bone.keyframe_insert("rotation_euler",frame=frame)
    scene.frame_start,scene.frame_end=1,300
    options={"use_selection":True,"object_types":{"ARMATURE"},"add_leaf_bones":False,
             "bake_anim":True,"bake_anim_use_nla_strips":False,"bake_anim_use_all_actions":False,
             "bake_anim_simplify_factor":0.}
    bpy.ops.export_scene.fbx(filepath=str(output/"original-synthetic.fbx"),**options)
    second=rig.animation_data.action.copy();second.name="Ambiguous second take"
    options["bake_anim_use_all_actions"]=True
    bpy.ops.export_scene.fbx(filepath=str(output/"ambiguous-synthetic.fbx"),**options)
    # An actual referenced image must be denied by skeleton-only intake, even
    # with recursive image searching disabled. All files are original fixtures.
    bpy.ops.mesh.primitive_plane_add(size=1)
    plane=bpy.context.object
    material=bpy.data.materials.new("SyntheticImageReference")
    material.use_nodes=True
    image=bpy.data.images.new("Synthetic security pixels",width=2,height=2)
    image.filepath_raw=str(output/"external-test-image.png")
    image.file_format="PNG";image.save();image.source="FILE"
    texture=material.node_tree.nodes.new("ShaderNodeTexImage");texture.image=image
    material.node_tree.links.new(texture.outputs["Color"],material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    plane.data.materials.append(material);rig.select_set(True)
    options.update(object_types={"ARMATURE","MESH"},bake_anim_use_all_actions=False)
    bpy.ops.export_scene.fbx(filepath=str(output/"image-reference-synthetic.fbx"),**options)
    print("ORIGINAL_SYNTHETIC_FBX_CREATED_300_FRAMES_NOT_PRODUCTION_ASSET")


if __name__=="__main__":
    author(Path(sys.argv[sys.argv.index("--")+1]))
