"""Original native-body CI source author, independent Action reopen and faults.

Source is a non-shipping armature derived from actual MPFB joint positions,
with T-pose body/hand anatomy, independently retained hand planes and bone rolls
and authored 4m/400-degree travel.
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


def layout(include_hands=False):
    rows=[("root",None,None,"BODY"),("spine05","spine03",None,"FORWARD"),
          ("spine03","spine01",None,"FORWARD"),("spine01","neck01",None,"FORWARD"),
          ("neck01","neck02",None,"FORWARD"),("neck02","head",None,"FORWARD"),
          ("head",None,"head_tip","FORWARD")]
    for suffix in (".L",".R"):
        rows.extend([("clavicle"+suffix,"upperarm01"+suffix,None,"FORWARD"),
            ("upperarm01"+suffix,"lowerarm01"+suffix,None,"FORWARD"),
            ("lowerarm01"+suffix,"wrist"+suffix,None,"FORWARD"),
            ("wrist"+suffix,"finger3-1"+suffix,None if include_hands else "hand_tip"+suffix,"FORWARD"),
            ("upperleg01"+suffix,"lowerleg01"+suffix,None,"FORWARD"),
            ("lowerleg01"+suffix,"foot"+suffix,None,"FORWARD"),
            ("foot"+suffix,"toe3-1"+suffix,"foot_tip"+suffix,"UP")])
    if include_hands:
        for suffix in (".L",".R"):
            for digit in range(1,6):
                if digit>1:rows.append((f"metacarpal{digit-1}{suffix}",f"finger{digit}-1{suffix}",None,"FORWARD"))
                for joint in range(1,4):
                    name=f"finger{digit}-{joint}{suffix}"
                    rows.append((name,f"finger{digit}-{joint+1}{suffix}" if joint<3 else None,
                                 "tip_"+name if joint==3 else None,"FORWARD"))
    return rows


def author(master: Path,folder: Path,*,origin="target-root",corrective_challenge=False,posed_origin_challenge=False,include_hands=False,symmetric_challenge=False):
    folder.mkdir(parents=True,exist_ok=False)
    before=sha256(master.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False)
    target=next(o for o in bpy.data.objects if o.type=="ARMATURE")
    rows=layout(include_hands);names={row[0]:f"CI_Native_{i:02}" for i,row in enumerate(rows)}
    names["root"]="@ARMATURE"
    world=target.matrix_world.copy()
    heads={b.name:world@b.head_local for b in target.data.bones}
    root=heads["root"].copy()
    if origin=="hip":root=(heads["upperleg01.L"]+heads["upperleg01.R"])/2
    if origin=="ground":
        root=(heads["upperleg01.L"]+heads["upperleg01.R"])/2
        root.z=0.
    adjusted={n:p.copy() for n,p in heads.items()}
    tails={b.name:world@b.tail_local for b in target.data.bones}
    # Independent geometric T-pose construction, no production reference solver.
    for suffix,direction in ((".L",Vector((1,0,0))),(".R",Vector((-1,0,0)))):
        upper,lower,wrist="upperarm01"+suffix,"lowerarm01"+suffix,"wrist"+suffix
        adjusted[lower]=heads[upper]+direction*(heads[lower]-heads[upper]).length
        adjusted[wrist]=adjusted[lower]+direction*(heads[wrist]-heads[lower]).length
        adjusted["finger3-1"+suffix]=adjusted[wrist]+direction*(heads["finger3-1"+suffix]-heads[wrist]).length
        if include_hands:
            # Preserve the complete original palm geometry through one rigid
            # hand rotation, independently of the production plane solver.
            rotation=(heads["finger3-1"+suffix]-heads[wrist]).rotation_difference(direction)
            for name in names:
                if name.endswith(suffix) and name.startswith(("finger","metacarpal")):
                    adjusted[name]=adjusted[wrist]+rotation@(heads[name]-heads[wrist])
                    tails[name]=adjusted[wrist]+rotation@(tails[name]-heads[wrist])
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
        endpoint=adjusted[target_tip] if target_tip else tails[target_name]
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
        if origin!="target-root":rig.rotation_euler.x=math.radians(20)*math.sin(2*math.pi*t)
        rig.keyframe_insert("location",frame=frame);rig.keyframe_insert("rotation_euler",frame=frame)
        for i,bone in enumerate(rig.pose.bones):
            bone.rotation_mode="XYZ"
            bone.rotation_euler.x=math.radians(3)*math.sin(2*math.pi*t+i*.2)
            if bone.name==names["upperarm01.L"]:bone.rotation_euler.x+=math.radians(7)
            if symmetric_challenge and bone.name in {names['lowerarm01.L'],names['lowerarm01.R']}:
                # This separate nonshipping test needs two stable elbow poles.
                # Retain all prior fixture variants and production IK guards.
                bone.rotation_euler.x+=math.radians(12)*math.sin(math.pi*t)**2
            if corrective_challenge and bone.name in {names["spine05"],names["upperleg01.L"]}:
                # Original analytic opposing bend, not sampled owner motion.
                # V2 starts in the already-tested opposing-bend pose and
                # recovers. A posed origin is deliberately not a neutral bind.
                amplitude=(1+math.cos(math.pi*t))/2 if posed_origin_challenge else math.sin(math.pi*t)
                bone.rotation_euler.x+=math.radians(20)*amplitude
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
    original=None;original_stack=None
    if "skin_deformation" in data:
        from blender_bridge.native_skin_stack import source_stack
        master=timeline_path.parent/"candidate.blend"
        if master.is_symlink() or sha256(master.read_bytes()).hexdigest()!=data["bindings"]["master_sha256"]:
            raise RuntimeError("Independent corrective reopen master binding differs")
        bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False)
        human=next(o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100)
        rig=next(o for o in bpy.data.objects if o.type=="ARMATURE")
        original,original_sha=_evaluated_vertices(bpy,human)
        if original_sha!=data["skin_deformation"]["source_neutral_sha256"]:raise RuntimeError("Corrective original neutral proof differs")
        original_stack=source_stack(human,rig)
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
    if original is not None:
        proof=data["skin_deformation"];mods=tuple(human.modifiers);corrective=mods[-1]
        if len(mods)!=len(original_stack)+1 or source_stack(human,rig,modifiers=mods[:-1])!=original_stack:
            raise RuntimeError("Corrective review source modifier/mask stack differs")
        for key,value in proof["modifier"].items():
            actual=corrective.is_bind if key=="is_bound" else getattr(corrective,key)
            if type(actual) is not type(value) or actual!=value:raise RuntimeError("Corrective review settings or binding differ")
        if max(math.dist(a,b) for a,b in zip(original,neutral))>1e-6:raise RuntimeError("Corrective neutral rest shape changed")
        master_bind=EdgeStrain(original,evaluated_edges(bpy,human))
    rig.animation_data.action=action;rig.animation_data.action_slot=slot
    first_pose_strain=None
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
        if data.get("mesh_strain_reference")=="TRUE_NEUTRAL_BIND_V2":
            if first_pose_strain is None:first_pose_strain=EdgeStrain(points,evaluated_edges(bpy,human))
            observed=first_pose_strain.observe(points,evaluated_edges(bpy,human),expected["frame"])
            first_expected=data["first_pose_relative_frames"][expected["frame"]-1]
            if any(abs(v-first_expected[k])>1e-6 for k,v in observed.items()) or first_pose_strain.report()!=data["first_pose_edge_strain"]:
                raise RuntimeError("Independent original posed-origin observations differ")
            if any(abs(v-expected[k])>1e-6 for k,v in strain.items()):raise RuntimeError("V2 main quality is not neutral-bound")
        if original is not None:
            from blender_bridge.pose_deformation import _movement
            master_strain=master_bind.measure(points,evaluated_edges(bpy,human),expected["frame"])
            if any(abs(value-data["master_relative_frames"][expected["frame"]-1][key])>1e-6 for key,value in master_strain.items()):
                raise RuntimeError("Independent corrective original-master strain differs")
            corrective.show_viewport=False
            try:raw,raw_sha=_evaluated_vertices(bpy,human)
            finally:corrective.show_viewport=True
            moved,maximum=_movement(raw,points);correction=expected["skin_correction"]
            if raw_sha!=correction["uncorrected_sha256"] or moved!=correction["corrected_vertices"] or abs(maximum-correction["max_correction_local"])>1e-8:
                raise RuntimeError("Independent uncorrected/corrected skin evidence differs")
        if "hip_anchor" in data:
            actual=[world@rig.pose.bones[name].matrix.translation for name in data["hip_anchor"]["target_bones"]]
            center=[sum(p[i] for p in actual)/2 for i in range(3)]
            if math.dist(center,expected["hip_midpoint_world"])>1e-6:raise RuntimeError("Reopened actual native hip trajectory differs")
    if sha256(review.read_bytes()).hexdigest()!=before:raise RuntimeError("Native Action reopen modified private copy bytes")
    extra={} if original is None else {"bound_skin_and_masks_reopened":True,"uncorrected_frames_reproduced":data["source_frame_count"],"original_master_strain_reproduced":True}
    if first_pose_strain is not None:extra["posed_origin_observations_reproduced"]=data["source_frame_count"]
    output.write_text(json.dumps({**extra,"all_frames_reopened":data["source_frame_count"],"all_skin_pose_hashes_agree":True,
        "bind_relative_strain_agrees":True,"review_bytes_unchanged":True},indent=2))
    print("NATIVE_ACTION_REOPENED_ALL_SKIN_POSE_FRAMES",data["source_frame_count"])


def fault(master: Path,job: Path,folder: Path):
    from blender_bridge.native_retarget import retarget_native
    from blender_bridge.refit_revision import rig_fingerprint
    from blender_bridge.pose_deformation import _evaluated_vertices
    from blender_bridge.fbx_source import pose_digest
    original=sha256(master.read_bytes()).hexdigest()
    from contextlib import nullcontext
    from unittest.mock import patch
    from blender_bridge.native_corrective import CorrectiveSkin
    base_profile=json.loads((job/"native_mapping.json").read_text())
    corrected=base_profile.get("skin_deformation_policy")=="BOUND_CORRECTIVE_SMOOTH_V1"
    kinds=("translation","scale","bind_failure","settings_change") if corrected else ("translation","scale")
    if "hand_reference_planes" in base_profile:kinds+=("palm_branch",)
    for kind in kinds:
        stage=folder/("fault-"+kind);stage.mkdir(parents=True,exist_ok=False)
        shutil.copy2(master,stage/"candidate.blend")
        source=json.loads((job/"source_snapshot.json").read_text())
        profile=json.loads((job/"native_mapping.json").read_text())
        if kind=="palm_branch":
            wrong=next(p for p in profile["pairs"] if p["target"]=="finger2-2.L")
            profile["hand_reference_planes"]["planes"]["left"]["pinky"]={k:wrong[k] for k in ("source","target")}
        name=profile["pairs"][1]["source"];index=next(i for i,b in enumerate(source["bones"]) if b["name"]==name)
        row=source["frames"][19]
        if kind=="translation":row["poses"][index][3]+=1.
        elif kind=="scale":
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
        before_stack=[(m.name,m.type,m.show_viewport,m.show_render) for m in human.modifiers]
        original_measure=CorrectiveSkin.measure_raw
        samples=[0]
        def changed(state,*args):
            samples[0]+=1
            if samples[0]==20:state.modifier.factor=.6
            return original_measure(state,*args)
        inject=(patch("blender_bridge.native_corrective._bind",return_value={"CANCELLED"}) if kind=="bind_failure" else
                patch.object(CorrectiveSkin,"measure_raw",changed) if kind=="settings_change" else nullcontext())
        try:
            with inject:retarget_native(bpy,stage,options)
        except ValueError as error:
            expected=("same wrist branch" if kind=="palm_branch" else "did not bind" if kind=="bind_failure" else "corrective binding" if kind=="settings_change" else "unsupported animated joint translation/scale")
            if expected not in str(error):raise
        else:raise RuntimeError("Actual native worker accepted unsupported animated "+kind)
        human=next(o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100)
        rig=next(o for o in bpy.data.objects if o.type=="ARMATURE")
        if (rig.animation_data and rig.animation_data.action) or len(bpy.data.actions) or (stage/"review_motion.blend").exists():
            raise RuntimeError("Failed native source left a partial Action/review")
        if rig_fingerprint(bpy,human)!=before_fp or _evaluated_vertices(bpy,human)[1]!=before_skin:
            raise RuntimeError("Failed native source did not restore real target skin/rest state")
        if [(m.name,m.type,m.show_viewport,m.show_render) for m in human.modifiers]!=before_stack:
            raise RuntimeError("Failed native corrective preview left a modifier or changed source masks")
    if sha256(master.read_bytes()).hexdigest()!=original:raise RuntimeError("Native faults changed master bytes")
    if corrected:
        from blender_bridge.native_review_reopen import reopen_native
        good_review=sha256((job/"review_motion.blend").read_bytes()).hexdigest()
        new_reference=base_profile.get("mesh_strain_reference")=="TRUE_NEUTRAL_BIND_V2"
        kinds=("settings","world","rest_roll","observations") if new_reference else ("settings","world","rest_roll")
        if "hand_reference_planes" in base_profile:kinds+=("palm_geometry",)
        for kind in kinds:
            stage=folder/("fault-saved-"+kind);stage.mkdir(exist_ok=False)
            for name in ("candidate.blend","review_motion.blend","target_timeline.json","source_snapshot.json","native_mapping.json"):
                shutil.copy2(job/name,stage/name)
            if kind not in {"observations","palm_geometry"}:
                bpy.ops.wm.open_mainfile(filepath=str(stage/"review_motion.blend"),load_ui=False)
                human=next(o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100)
                if kind=="settings":human.modifiers[-1].factor=.6
                elif kind=="rest_roll":
                    rig=next(o for o in bpy.data.objects if o.type=="ARMATURE")
                    bpy.context.view_layer.objects.active=rig;rig.select_set(True)
                    bpy.ops.object.mode_set(mode="EDIT")
                    rig.data.edit_bones["lowerarm02.L"].roll+=.05
                    bpy.ops.object.mode_set(mode="OBJECT")
                else:human.location.x+=.1
                bpy.ops.wm.save_as_mainfile(filepath=str(stage/"review_motion.blend"),compress=False,copy=True)
            data=json.loads((stage/"target_timeline.json").read_text())
            data["visual_review_blend"]={"name":"review_motion.blend","bytes":(stage/"review_motion.blend").stat().st_size,
                "sha256":sha256((stage/"review_motion.blend").read_bytes()).hexdigest()}
            if kind=="observations":data["first_pose_relative_frames"][19]["max_edge_stretch_ratio"]+=.5
            if kind=="palm_geometry":
                corners=data["hand_plane_proofs"]["planes"]["left"]["target_points"]
                # Preserve the plane's normal and all Action/skin data: only
                # actual rest-corner verification can detect this forged ray.
                corners["index"]=[corners["wrist"][i]+1.1*(corners["index"][i]-corners["wrist"][i]) for i in range(3)]
            (stage/"target_timeline.json").write_text(json.dumps(data))
            options={**data["bindings"],"review_sha256":data["visual_review_blend"]["sha256"],
                "timeline_sha256":sha256((stage/"target_timeline.json").read_bytes()).hexdigest()}
            try:reopen_native(bpy,stage,options)
            except ValueError as error:
                expected={"settings":"corrective binding, settings","world":"object transforms differ","rest_roll":"rig rest frames differ","observations":"first-pose observations differ","palm_geometry":"palm rest geometry differs"}[kind]
                if expected not in str(error):raise
            else:raise RuntimeError("Actual saved-skin "+kind+" tamper was accepted after rehashing")
        if sha256((job/"review_motion.blend").read_bytes()).hexdigest()!=good_review or sha256(master.read_bytes()).hexdigest()!=original:
            raise RuntimeError("Saved-skin negative test changed original evidence/master bytes")
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
    parser.add_argument("--origin",choices=("target-root","hip","ground"),default="target-root")
    parser.add_argument("--corrective-challenge",action="store_true")
    parser.add_argument("--posed-origin-challenge",action="store_true")
    parser.add_argument("--include-hands",action="store_true")
    parser.add_argument('--symmetric-challenge',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    if args.mode=="author":author(args.master,args.folder,origin=args.origin,corrective_challenge=args.corrective_challenge,posed_origin_challenge=args.posed_origin_challenge,include_hands=args.include_hands,symmetric_challenge=args.symmetric_challenge)
    elif args.mode=="reopen":reopen(args.review,args.timeline,args.output)
    else:fault(args.master,args.job,args.folder)
