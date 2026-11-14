"""Original native-body CI source author, independent Action reopen and faults.

Source is a non-shipping armature derived from actual MPFB joint positions,
with T-pose arms, independently assigned roll and authored 4m/400-degree travel.
It is not owner/Fab compatibility evidence. Never upload generated files.
"""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import math
import shutil
import sys

import bpy
from mathutils import Vector,Matrix

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def layout():
    rows=[("root",None,None,"BODY"),("spine05","spine03",None,"FORWARD"),
          ("spine03","spine01",None,"FORWARD"),("spine01","neck01",None,"FORWARD"),
          ("neck01","neck02",None,"FORWARD"),("neck02","head",None,"FORWARD"),
          ("head",None,"head_tip","FORWARD")]
    for suffix in (".L",".R"):
        rows.extend([("clavicle"+suffix,"upperarm01"+suffix,None,"FORWARD"),
            ("upperarm01"+suffix,"lowerarm01"+suffix,None,"FORWARD"),
            ("lowerarm01"+suffix,"wrist"+suffix,None,"FORWARD"),
            ("wrist"+suffix,"finger3-1"+suffix,"hand_tip"+suffix,"FORWARD"),
            ("upperleg01"+suffix,"lowerleg01"+suffix,None,"FORWARD"),
            ("lowerleg01"+suffix,"foot"+suffix,None,"FORWARD"),
            ("foot"+suffix,"toe3-1"+suffix,"foot_tip"+suffix,"UP")])
    return rows


def author(master: Path,folder: Path):
    folder.mkdir(parents=True,exist_ok=False)
    before=sha256(master.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False)
    target=next(o for o in bpy.data.objects if o.type=="ARMATURE")
    rows=layout();names={row[0]:f"CI_Native_{i:02}" for i,row in enumerate(rows)}
    names["root"]="@ARMATURE"
    world=target.matrix_world.copy()
    heads={b.name:world@b.head_local for b in target.data.bones}
    root=heads["root"].copy()
    adjusted={n:p.copy() for n,p in heads.items()}
    # Independent geometric T-pose construction, no production reference solver.
    for suffix,direction in ((".L",Vector((1,0,0))),(".R",Vector((-1,0,0)))):
        upper,lower,wrist="upperarm01"+suffix,"lowerarm01"+suffix,"wrist"+suffix
        adjusted[lower]=heads[upper]+direction*(heads[lower]-heads[upper]).length
        adjusted[wrist]=adjusted[lower]+direction*(heads[wrist]-heads[lower]).length
        adjusted["finger3-1"+suffix]=adjusted[wrist]+direction*(heads["finger3-1"+suffix]-heads[wrist]).length
    parent_names={}
    selected=set(names)
    for target_name in names:
        if target_name=="root":continue
        parent=target.data.bones[target_name].parent
        while parent is not None and parent.name not in selected:parent=parent.parent
        parent_names[names[target_name]]=names[parent.name] if parent else "@ARMATURE"
    rest=[];pairs=[]
    for i,(target_name,target_tip,extra,secondary) in enumerate(rows):
        source_name=names[target_name]
        if i==0:
            pairs.append({"source":source_name,"target":target_name,"source_tip":None,"target_tip":None,"secondary":secondary});continue
        tip_name=names[target_tip] if target_tip in names else "CI_Native_"+extra
        endpoint=adjusted[target_tip] if target_tip else world@target.data.bones[target_name].tail_local
        rest.append({"name":source_name,"parent":parent_names[source_name],"head":adjusted[target_name]-root,
                     "tail":endpoint-root,"roll":.17*(i%5)})
        if extra:
            rest.append({"name":tip_name,"parent":source_name,"head":endpoint-root,
                         "tail":endpoint-root+Vector((0,0,.02)),"roll":.31})
        pairs.append({"source":source_name,"target":target_name,"source_tip":tip_name,"target_tip":target_tip,"secondary":secondary})
    landmarks={key:{"source":names[name],"target":name} for key,name in (
        ("left_hip","upperleg01.L"),("right_hip","upperleg01.R"),("head","head"),
        ("left_hand","wrist.L"),("right_hand","wrist.R"),("left_foot","foot.L"),("right_foot","foot.R"))}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data=bpy.data.armatures.new("ORIGINAL_CI_NATIVE_SOURCE")
    rig=bpy.data.objects.new("Armature",data)
    bpy.context.scene.collection.objects.link(rig)
    rig.location=root
    bpy.context.view_layer.objects.active=rig;rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for row in rest:
        bone=data.edit_bones.new(row["name"]);bone.head=row["head"];bone.tail=row["tail"];bone.roll=row["roll"]
    for row in rest:
        if row["parent"]!="@ARMATURE":data.edit_bones[row["name"]].parent=data.edit_bones[row["parent"]]
    bpy.ops.object.mode_set(mode="OBJECT")
    scene=bpy.context.scene;scene.render.fps=30;scene.frame_start=1;scene.frame_end=300
    for frame in range(1,301):
        t=(frame-1)/299
        rig.location=root+Vector((4*t,0,0));rig.rotation_euler.z=math.radians(400*t)
        rig.keyframe_insert("location",frame=frame);rig.keyframe_insert("rotation_euler",frame=frame)
        for i,bone in enumerate(rig.pose.bones):
            bone.rotation_mode="XYZ"
            bone.rotation_euler.x=math.radians(3)*math.sin(2*math.pi*t+i*.2)
            if bone.name==names["upperarm01.L"]:bone.rotation_euler.x+=math.radians(7)
            bone.keyframe_insert("rotation_euler",frame=frame)
    scene.frame_set(1)
    bpy.ops.export_scene.fbx(filepath=str(folder/"original-native-body.fbx"),use_selection=True,object_types={"ARMATURE"},
        add_leaf_bones=False,bake_anim=True,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,bake_anim_simplify_factor=0.)
    (folder/"mapping-spec.json").write_text(json.dumps({"pairs":pairs,"landmarks":landmarks},indent=2))
    if sha256(master.read_bytes()).hexdigest()!=before:raise RuntimeError("Source author modified target master")
    print("ORIGINAL_CI_NATIVE_BODY_AUTHORED_NOT_OWNER_ASSET",len(pairs),300)


def reopen(review: Path,timeline_path: Path,output: Path):
    from blender_bridge.pose_deformation import _evaluated_vertices
    from blender_bridge.bvh_review_timeline import evaluated_edges
    from blender_bridge.motion_quality import EdgeStrain
    from blender_bridge.fbx_source import pose_digest
    data=json.loads(timeline_path.read_text(encoding="utf-8"))
    before=sha256(review.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(review),load_ui=False)
    rig=next(o for o in bpy.data.objects if o.type=="ARMATURE")
    human=next(o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100)
    action=rig.animation_data.action;slot=rig.animation_data.action_slot
    if action is None or list(action.frame_range)!=[1.,float(data["source_frame_count"])]:raise RuntimeError("Private native Action lost its complete source range")
    rig.animation_data.action=None
    for bone in rig.pose.bones:bone.matrix_basis=Matrix.Identity(4)
    neutral,neutral_sha=_evaluated_vertices(bpy,human)
    if neutral_sha!=data["neutral_bind_skin_sha256"]:raise RuntimeError("Native private Action lost neutral bind geometry")
    bind=EdgeStrain(neutral,evaluated_edges(bpy,human))
    rig.animation_data.action=action;rig.animation_data.action_slot=slot
    world=rig.matrix_world.copy()
    world_values=[float(v) for row in world for v in row]
    for expected,bind_expected in zip(data["full_timeline_frames"],data["bind_relative_frames"]):
        bpy.context.scene.frame_set(expected["frame"])
        points,digest=_evaluated_vertices(bpy,human)
        if digest!=expected["evaluated_sha256"]:raise RuntimeError("Independent native Action reopen has different skin on frame "+str(expected["frame"]))
        poses=[[float(v) for row in world@rig.pose.bones[p["target"]].matrix for v in row] for p in data["mapped_pairs"]]
        if pose_digest(world_values,poses)!=expected["target_pose_sha256"]:raise RuntimeError("Independent reopened native bone poses differ")
        strain=bind.measure(points,evaluated_edges(bpy,human),expected["frame"])
        if any(abs(value-bind_expected[key])>1e-6 for key,value in strain.items()):raise RuntimeError("Independent native bind-relative edge strain differs")
    if sha256(review.read_bytes()).hexdigest()!=before:raise RuntimeError("Native Action reopen modified private copy bytes")
    output.write_text(json.dumps({"all_frames_reopened":data["source_frame_count"],"all_skin_pose_hashes_agree":True,
        "bind_relative_strain_agrees":True,"review_bytes_unchanged":True},indent=2))
    print("NATIVE_ACTION_REOPENED_ALL_SKIN_POSE_FRAMES",data["source_frame_count"])


def fault(master: Path,job: Path,folder: Path):
    from blender_bridge.native_retarget import retarget_native
    from blender_bridge.refit_revision import rig_fingerprint
    from blender_bridge.pose_deformation import _evaluated_vertices
    from blender_bridge.fbx_source import pose_digest
    original=sha256(master.read_bytes()).hexdigest()
    for kind in ("translation","scale"):
        stage=folder/("fault-"+kind);stage.mkdir(parents=True,exist_ok=False)
        shutil.copy2(master,stage/"candidate.blend")
        source=json.loads((job/"source_snapshot.json").read_text())
        profile=json.loads((job/"native_mapping.json").read_text())
        name=profile["pairs"][1]["source"];index=next(i for i,b in enumerate(source["bones"]) if b["name"]==name)
        row=source["frames"][19]
        if kind=="translation":row["poses"][index][3]+=1.
        else:
            for i in range(3):
                for j in range(3):row["poses"][index][i*4+j]*=1.1
        row["pose_sha256"]=pose_digest(row["armature_world"],row["poses"])
        payload=json.dumps(source).encode();(stage/"source_snapshot.json").write_bytes(payload)
        profile["snapshot_sha256"]=sha256(payload).hexdigest()
        payload=json.dumps(profile).encode();(stage/"native_mapping.json").write_bytes(payload)
        options={k:profile[k] for k in ("source_sha256","snapshot_sha256","master_sha256")}
        options.update(mapping_sha256=sha256(payload).hexdigest(),render_private_frames=False)
        bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False)
        human=next(o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100)
        before_fp=rig_fingerprint(bpy,human);before_skin=_evaluated_vertices(bpy,human)[1]
        try:retarget_native(bpy,stage,options)
        except ValueError as error:
            if "unsupported animated joint translation/scale" not in str(error):raise
        else:raise RuntimeError("Actual native worker accepted unsupported animated "+kind)
        human=next(o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100)
        rig=next(o for o in bpy.data.objects if o.type=="ARMATURE")
        if (rig.animation_data and rig.animation_data.action) or len(bpy.data.actions) or (stage/"review_motion.blend").exists():
            raise RuntimeError("Failed native source left a partial Action/review")
        if rig_fingerprint(bpy,human)!=before_fp or _evaluated_vertices(bpy,human)[1]!=before_skin:
            raise RuntimeError("Failed native source did not restore real target skin/rest state")
    if sha256(master.read_bytes()).hexdigest()!=original:raise RuntimeError("Native faults changed master bytes")
    print("NATIVE_PARTIAL_ACTION_FAULTS_REJECTED_RESTORED_ORIGINALS_UNCHANGED")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("author","reopen","fault"),required=True)
    parser.add_argument("--master",type=Path)
    parser.add_argument("--folder",type=Path)
    parser.add_argument("--review",type=Path)
    parser.add_argument("--timeline",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--job",type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    if args.mode=="author":author(args.master,args.folder)
    elif args.mode=="reopen":reopen(args.review,args.timeline,args.output)
    else:fault(args.master,args.job,args.folder)
