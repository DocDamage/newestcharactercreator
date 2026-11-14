"""Synthetic skin-contract and setup-failure tests; real Blender gate is separate."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.native_body_contract import contract
from blender_bridge.native_corrective import CorrectiveSkin, SETTINGS, POLICY
from blender_bridge.native_skin_stack import source_stack
from blender_bridge.native_review_reopen import same_world
from blender_bridge.native_inputs import validate_profile as worker_profile
from ucc.animations.native_profile import validate_native_profile
from ucc.core.errors import ValidationError
from ucc.jobs.native_evidence import validate_native_timeline
from ucc.jobs.native_skin_evidence import SETTINGS as EVIDENCE_SETTINGS
from ucc.jobs.native_skin_evidence import validate_reopen_report
from ucc.jobs.protocol import JobRequest


def corrective_contract():
    data,report,source,profile,bindings=contract()
    profile["skin_deformation_policy"]=POLICY
    data["skin_deformation_policy"]=POLICY
    data["skin_deformation"]={"schema_version":1,"policy":POLICY,"source_modifier_count":1,"review_modifier_count":2,
        "modifier":deepcopy(EVIDENCE_SETTINGS),"source_armature":{"name":"Synthetic armature","type":"ARMATURE",
            "rig_object":"Synthetic rig","use_vertex_groups":True,"use_bone_envelopes":False,
            "use_deform_preserve_volume":False,"use_multi_modifier":False,"show_viewport":True,"show_render":True},
        "source_neutral_sha256":"e"*64,"bound_neutral_sha256":data["neutral_bind_skin_sha256"],
        "neutral_vertex_count":1000,"max_neutral_displacement_local":1e-7}
    data["skin_deformation"]["source_modifiers"]=[deepcopy(data["skin_deformation"]["source_armature"])]
    data["master_relative_frames"]=deepcopy(data["bind_relative_frames"])
    data["master_bind_edge_strain"]=deepcopy(data["bind_edge_strain"])
    for row in data["full_timeline_frames"]:
        row["skin_correction"]={"uncorrected_sha256":f"{row['frame']+100:064x}","corrected_vertices":100,"max_correction_local":.01}
    report["skin_state_restored"]=True
    return data,report,source,profile,bindings


class CorrectiveEvidenceTests(unittest.TestCase):
    def test_static_helper_mask_metadata_is_required_and_immutable(self):
        args=corrective_contract();proof=args[0]["skin_deformation"]
        mask={"name":"Unit static mask","type":"MASK","mode":"VERTEX_GROUP","vertex_group":"body",
            "invert_vertex_group":False,"threshold":0.,"use_smooth":False,"show_viewport":True,"show_render":True,
            "source_mesh_vertices":1200,"vertex_group_sha256":"c"*64}
        proof["source_modifiers"].append(mask);proof["source_modifier_count"]=2;proof["review_modifier_count"]=3
        validate_native_timeline(*args)
        for field,value in (("mode","ARMATURE"),("use_smooth",True),("source_mesh_vertices",999),("vertex_group_sha256","bad")):
            bad=deepcopy(args);bad[0]["skin_deformation"]["source_modifiers"][-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValidationError):validate_native_timeline(*bad)

    def test_reopen_protocol_and_complete_actual_frame_report_are_closed(self):
        data=corrective_contract()[0]
        bindings={k:"a"*64 for k in ("source_sha256","snapshot_sha256","mapping_sha256","master_sha256","review_sha256","timeline_sha256")}
        JobRequest.new("reopen_native_fbx_body",input_project="candidate.blend",options=bindings)
        for options in ({**bindings,"render_private_frames":False},{**bindings,"path":"../review.blend"},{**bindings,"timeline_sha256":None}):
            with self.assertRaises(ValidationError):JobRequest.new("reopen_native_fbx_body",input_project="candidate.blend",options=options)
        report={"status":"REAL_NATIVE_BODY_REVIEW_REOPENED","bindings":bindings,"frames_verified":5,
            "uncorrected_skin_frames_verified":5,"master_strain_frames_verified":5,"hip_frames_verified":0,
            "skin_deformation_policy":POLICY,"original_master_unchanged":True,"review_unchanged":True,
            "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}
        validate_reopen_report(report,bindings,data)
        for field,value in (("frames_verified",True),("uncorrected_skin_frames_verified",4),("review_unchanged",False),
                            ("retargeting_verified",True),("bindings",{}),("extra",True)):
            with self.subTest(field=field),self.assertRaises(ValidationError):validate_reopen_report({**report,field:value},bindings,data)

    def test_complete_skin_policy_and_legacy_profiles_validate(self):
        args=corrective_contract();self.assertIs(validate_native_timeline(*args),args[0])
        args=contract();args[3]["skin_deformation_policy"]="MASTER_MODIFIERS_V1"
        validate_native_timeline(*args)

    def test_unknown_untyped_or_unrequested_skin_policy_rejects(self):
        profile=contract()[3]
        for value in (POLICY,"MASTER_MODIFIERS_V1", "AUTO", None, [POLICY], True):
            p=deepcopy(profile);p["skin_deformation_policy"]=value
            if type(value) is str and value in {POLICY,"MASTER_MODIFIERS_V1"}:
                validate_native_profile(p,"a"*64,"b"*64,"c"*64);worker_profile(p,"a"*64,"b"*64,"c"*64)
            else:
                with self.assertRaises(ValidationError):validate_native_profile(p,"a"*64,"b"*64,"c"*64)
                with self.assertRaises(ValueError):worker_profile(p,"a"*64,"b"*64,"c"*64)
        args=corrective_contract();del args[3]["skin_deformation_policy"]
        with self.assertRaisesRegex(ValidationError,"Unrequested"):validate_native_timeline(*args)

    def test_binding_settings_rest_shape_source_stack_and_cleanup_are_required(self):
        for fault in ("missing","cleanup","factor","iterations","bound","neutral_hash","neutral_error","topology","armature","count"):
            data,report,source,profile,bindings=corrective_contract();proof=data["skin_deformation"]
            if fault=="missing":del data["skin_deformation"]
            if fault=="cleanup":report["skin_state_restored"]=False
            if fault=="factor":proof["modifier"]["factor"]=.6
            if fault=="iterations":proof["modifier"]["iterations"]=True
            if fault=="bound":proof["modifier"]["is_bound"]=False
            if fault=="neutral_hash":proof["bound_neutral_sha256"]="f"*64
            if fault=="neutral_error":proof["max_neutral_displacement_local"]=.00001
            if fault=="topology":data["master_bind_edge_strain"]["evaluated_topology_sha256"]="a"*64
            if fault=="armature":proof["source_armature"]["use_bone_envelopes"]=True
            if fault=="count":proof["neutral_vertex_count"]=999
            with self.subTest(fault=fault),self.assertRaises(ValidationError):validate_native_timeline(data,report,source,profile,bindings)

    def test_original_master_strain_and_correction_caps_cannot_be_hidden_by_healthy_derived_skin(self):
        for fault in ("missing_frames","original_stretch","original_collapse","missing_raw","raw_hash","excess_correction","count","no_effect"):
            data,report,source,profile,bindings=corrective_contract()
            if fault=="missing_frames":data["master_relative_frames"].pop()
            if fault=="original_stretch":data["master_relative_frames"][-1]["max_edge_stretch_ratio"]=4.001
            if fault=="original_collapse":data["master_relative_frames"][-1]["min_edge_length_ratio"]=.049
            if fault=="missing_raw":del data["full_timeline_frames"][-1]["skin_correction"]
            if fault=="raw_hash":data["full_timeline_frames"][-1]["skin_correction"]["uncorrected_sha256"]="not a digest"
            if fault=="excess_correction":data["full_timeline_frames"][-1]["skin_correction"]["max_correction_local"]=.061
            if fault=="count":data["full_timeline_frames"][-1]["skin_correction"]["corrected_vertices"]=1001
            if fault=="no_effect":
                for row in data["full_timeline_frames"]:row["skin_correction"].update(corrected_vertices=0,max_correction_local=0.)
            with self.subTest(fault=fault),self.assertRaises(ValidationError):validate_native_timeline(data,report,source,profile,bindings)


class CorrectiveSetupTests(unittest.TestCase):
    def test_saved_object_world_motion_or_nonfinite_values_cannot_hide_behind_local_skin_hashes(self):
        values=[float(i==j) for i in range(4) for j in range(4)]
        obj=SimpleNamespace(matrix_world=[values[i:i+4] for i in range(0,16,4)])
        self.assertTrue(same_world(obj,values))
        obj.matrix_world[0][3]=.1
        self.assertFalse(same_world(obj,values))
        obj.matrix_world[0][3]=0.;obj.matrix_world[2][2]=float("nan")
        self.assertFalse(same_world(obj,values))

    def test_mask_membership_hash_and_worker_stack_restrictions_are_real(self):
        bpy,human,rig,_=self.setup_scene()
        group=SimpleNamespace(group=4,weight=1.)
        human.vertex_groups={"body":SimpleNamespace(index=4)}
        human.data=SimpleNamespace(vertices=[SimpleNamespace(index=0,groups=[group])])
        mask=SimpleNamespace(name="Unit mask",type="MASK",mode="VERTEX_GROUP",use_smooth=False,armature=None,
            show_viewport=True,show_render=True,threshold=0.,vertex_group="body",invert_vertex_group=False)
        human.modifiers.append(mask)
        before=source_stack(human,rig)
        group.weight=.5
        self.assertNotEqual(before[-1]["vertex_group_sha256"],source_stack(human,rig)[-1]["vertex_group_sha256"])
        for field,value in (("mode","ARMATURE"),("use_smooth",True),("vertex_group","missing"),("show_render",False)):
            old=getattr(mask,field);setattr(mask,field,value)
            with self.subTest(field=field),self.assertRaises(ValueError):source_stack(human,rig)
            setattr(mask,field,old)

    def setup_scene(self):
        rig=SimpleNamespace(name="Unit rig",mode="OBJECT",data=SimpleNamespace(pose_position="POSE"))
        arm=SimpleNamespace(name="Unit armature",type="ARMATURE",object=rig,use_vertex_groups=True,
            use_bone_envelopes=False,use_deform_preserve_volume=False,use_multi_modifier=False,show_viewport=True,show_render=True)
        class Modifiers(list):
            def new(self,name,kind):
                mod=SimpleNamespace(name=name,type=kind,is_bind=False);self.append(mod);return mod
        human=SimpleNamespace(mode="OBJECT",modifiers=Modifiers([arm]))
        active=object();layer=SimpleNamespace(objects=SimpleNamespace(active=active),update=lambda:None)
        def bind(**kwargs):human.modifiers[-1].is_bind=True;return {"FINISHED"}
        bpy=SimpleNamespace(context=SimpleNamespace(view_layer=layer),ops=SimpleNamespace(object=SimpleNamespace(correctivesmooth_bind=bind)))
        return bpy,human,rig,active

    def test_actual_setup_cleanup_logic_restores_context_and_owned_modifier_on_bind_failure(self):
        for failure in ("operator","neutral_shape","success"):
            bpy,human,rig,active=self.setup_scene();original=((0.,0.,0.),(1.,0.,0.),(0.,1.,0.))
            points=original if failure!="neutral_shape" else ((0.,0.,.01),*original[1:])
            if failure=="operator":bpy.ops.object.correctivesmooth_bind=lambda **kw:{"CANCELLED"}
            with (patch("blender_bridge.native_corrective._evaluated_vertices",return_value=(points,"a"*64)),
                  patch("blender_bridge.native_corrective.evaluated_edges",return_value=((0,1),(1,2)))):
                if failure=="success":
                    state=CorrectiveSkin(bpy,human,rig,original,"a"*64)
                    self.assertTrue(state.proof["modifier"]["is_bound"])
                    state.remove()
                else:
                    with self.assertRaises(ValueError):CorrectiveSkin(bpy,human,rig,original,"a"*64)
            self.assertEqual(len(human.modifiers),1)
            self.assertIs(bpy.context.view_layer.objects.active,active)
            self.assertEqual(rig.data.pose_position,"POSE")

    def test_raw_comparison_restores_visibility_even_when_displacement_is_rejected(self):
        bpy,human,rig,_=self.setup_scene();original=((0.,0.,0.),(1.,0.,0.),(0.,1.,0.))
        with (patch("blender_bridge.native_corrective._evaluated_vertices",return_value=(original,"a"*64)),
              patch("blender_bridge.native_corrective.evaluated_edges",return_value=((0,1),(1,2)))):
            state=CorrectiveSkin(bpy,human,rig,original,"a"*64)
            with self.assertRaisesRegex(ValueError,"three percent"):
                state.measure_raw(((0.,0.,.1),*original[1:]),1.)
            self.assertTrue(state.modifier.show_viewport)
            state.remove()
