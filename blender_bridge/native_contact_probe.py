"""Actual disposable skin evaluation for bounded contact candidate search."""
from array import array
from hashlib import sha256
import sys
from typing import Any,Iterable
from blender_bridge.motion_quality import EdgeStrain,MotionQualityError,swing_twist_degrees
from blender_bridge.native_fit_policy import fitted_world_poses
from blender_bridge.native_fit_scene import original_skin_references
from blender_bridge.native_surface_review import SurfaceInspector
from blender_bridge.pose_deformation import _evaluated_vertices,_movement
from blender_bridge.bvh_review_timeline import evaluated_edges
from blender_bridge.contact_candidate_policy import MAX_POSE_TESTS


class CandidateBudgetExceeded(ValueError):pass


class CandidateProbe:
    def __init__(self,bpy: Any,human: Any,rig: Any,baseline: dict,profile: dict,*,mesh_guard=None):
        self.bpy=bpy;self.human=human;self.rig=rig;self.baseline=baseline;self.profile=profile;self.tested=0
        state=original_skin_references(bpy,human,rig,baseline);edges=evaluated_edges(bpy,human)
        self.bound=EdgeStrain(state['neutral'],edges);self.master=EdgeStrain(state['original'],edges)
        self.diagonal=baseline['model_baseline_diagonal_local']
        self.ordered=sorted(rig.pose.bones,key=lambda b:len(b.parent_recursive))
        self.mapped={p['target'] for p in profile['pairs']};self.inverse=rig.matrix_world.inverted()
        self.mesh_guard=mesh_guard

    def frame(self,plan: dict,frame: int) -> int:
        from mathutils import Matrix
        if self.tested>=MAX_POSE_TESTS:raise CandidateBudgetExceeded('CANDIDATE_POSE_BUDGET_EXCEEDED')
        self.tested+=1;bpy=self.bpy;rig=self.rig;human=self.human
        for pb in rig.pose.bones:pb.matrix_basis=Matrix.Identity(4)
        bpy.context.scene.frame_set(frame)
        expected=fitted_world_poses(plan,self.baseline['full_timeline_frames'][frame-1]['target_global_poses'],frame)
        computed={}
        for pb in self.ordered:
            kw={'parent_matrix':computed[pb.parent.name],'parent_matrix_local':pb.parent.bone.matrix_local} if pb.parent else {}
            if pb.name in plan['chain'] and any(plan['offsets'][frame-1]):
                basis=pb.bone.convert_local_to_pose(self.inverse@expected[pb.name],pb.bone.matrix_local,invert=True,**kw)
                if basis.translation.length>1e-5 or max(abs(v-1) for v in basis.to_scale())>1e-4:
                    raise ValueError('CANDIDATE_ACTUAL_HIERARCHY_TRANSLATION_OR_SCALE')
                pb.rotation_quaternion=basis.to_quaternion().normalized();pb.location=(0.,0.,0.);pb.scale=(1.,1.,1.)
                swing,twist=swing_twist_degrees(tuple(pb.rotation_quaternion))
                if swing>150. or twist>90.:raise MotionQualityError('Candidate joint exceeds unchanged safety bounds')
            elif pb.name not in self.mapped:pb.matrix_basis=Matrix.Identity(4)
            computed[pb.name]=pb.bone.convert_local_to_pose(pb.matrix_basis,pb.bone.matrix_local,**kw)
        bpy.context.view_layer.update()
        for name,wanted in expected.items():
            actual=rig.matrix_world@rig.pose.bones[name].matrix
            if (actual.translation-wanted.translation).length>1e-5 or max(abs(actual[i][j]-wanted[i][j]) for i in range(3) for j in range(3))>1e-4:
                raise ValueError('CANDIDATE_ACTUAL_POSE_MISMATCH')
        points,skin=_evaluated_vertices(bpy,human);edges=evaluated_edges(bpy,human)
        self.bound.measure(points,edges,frame);self.master.measure(points,edges,frame)
        mod=human.modifiers[-1];mod.show_viewport=False
        try:raw,_sha=_evaluated_vertices(bpy,human)
        finally:mod.show_viewport=True;bpy.context.view_layer.update()
        if _movement(raw,points)[1]>self.diagonal*.03:raise ValueError('CANDIDATE_SKIN_CORRECTION_EXCEEDED')
        graph=bpy.context.evaluated_depsgraph_get();evaluated=human.evaluated_get(graph)
        mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
        try:
            mesh.calc_loop_triangles();inspector=SurfaceInspector(self.profile,rig,human)
            indices=array('I',[0])*(len(mesh.loop_triangles)*3);mesh.loop_triangles.foreach_get('vertices',indices)
            if sys.byteorder!='little':indices.byteswap()
            topology=sha256(indices.tobytes()).hexdigest()
            inspector.inspect(mesh,frame,skin,topology)
            if inspector.status!='CHECKED':raise ValueError('CANDIDATE_SURFACE_UNAVAILABLE')
            pairs=sum(inspector.rows[-1][side]['pair_count'] for side in ('left','right'))
            if not pairs and self.mesh_guard is not None:return self.mesh_guard(bpy,human,rig,mesh,frame,skin,topology)
            return pairs
        finally:evaluated.to_mesh_clear()

    def evaluate(self,plan: dict,frames: Iterable[int]) -> dict:
        checked=0
        try:
            for frame in frames:
                pairs=self.frame(plan,frame);checked+=1
                if pairs:return {'pairs':pairs,'checked':checked,'failed_frame':frame,'reason':'SURFACE_CROSSINGS'}
            return {'pairs':0,'checked':checked,'reason':''}
        except CandidateBudgetExceeded:raise
        except (ValueError,MotionQualityError) as error:
            return {'pairs':5_000_001,'checked':checked,'reason':str(error)}
