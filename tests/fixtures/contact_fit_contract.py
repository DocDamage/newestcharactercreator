"""Invented boundary metadata only; never Blender, motion-pack or skin proof."""
from copy import deepcopy
from hashlib import sha256
import json
from ucc.animations.contact_fit import POLICY,HASHES,read_fit_plan,fit_frame


def matrix(head):
    return [1.,0.,0.,head[0],0.,1.,0.,head[1],0.,0.,1.,head[2],0.,0.,0.,1.]


def fixture():
    names=['root','upper','lower','hand','finger','other']
    profile={'pairs':[{'target':n} for n in names],
             'landmarks':{'right_hand':{'target':'hand'},'left_hand':{'target':'other'}},
             'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1','mesh_strain_reference':'TRUE_NEUTRAL_BIND_V2'}
    parents={'root':None,'upper':'root','helper':'upper','lower':'helper','hand':'lower','finger':'hand','other':'root'}
    baseline={'neutral_target_helpers':['helper'],'source_frame_count':5,'fps':30.,
              'target_anatomical_landmarks':{'left_hip':[.1,0.,0.],'right_hip':[-.1,0.,0.],'head':[0.,0.,1.],
                 'left_foot':[.1,0.,-1.],'right_foot':[-.1,0.,-1.]}}
    bindings={k:'a'*64 for k in HASHES}
    policy={'schema_version':1,'policy':POLICY,'bindings':bindings,'coordinate_space':'BLENDER_WORLD_METERS',
          'chain':{'side':'right','upper_arm':'upper','forearm':'lower','hand':'hand'},'fps':30.,
          'frames':[{'frame':i+1,'offset_world':[v,0.,0.]} for i,v in enumerate((0.,.001,.002,.001,0.))]}
    poses=[matrix(h) for h in ((0.,0.,0.),(0.,0.,0.),(0.,1.,0.),(0.,1.,1.),(0.,1.,1.1),(2.,0.,0.))]
    return policy,bindings,baseline,profile,parents,poses


def baseline_contract():
    policy,bindings,base,profile,parents,poses=fixture()
    base.update(source_first_frame=1,mapped_pairs=deepcopy(profile['pairs']),target_armature_world=matrix((0.,0.,0.)),
                model_baseline_diagonal_local=2.3,mesh_strain_reference='TRUE_NEUTRAL_BIND_V2',
                full_timeline_frames=[{'frame':i,'target_global_poses':deepcopy(poses),'root_world_head':[0.,0.,0.]} for i in range(1,6)])
    edge={'evaluated_edge_count':16,'measured_edge_count':16,'degenerate_baseline_edges_excluded':0,'evaluated_topology_sha256':'b'*64}
    base['bind_edge_strain']=deepcopy(edge);base['master_bind_edge_strain']=deepcopy(edge)
    return policy,bindings,base,profile,parents,poses


def reopen_report(bindings):
    return {'status':'REAL_NATIVE_BODY_REVIEW_REOPENED','bindings':dict(bindings),'frames_verified':5,
            'uncorrected_skin_frames_verified':5,'master_strain_frames_verified':5,'hip_frames_verified':0,
            'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1','original_master_unchanged':True,'review_unchanged':True,
            'retargeting_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False,
            'mesh_strain_reference':'TRUE_NEUTRAL_BIND_V2','first_pose_observation_frames_verified':5}


def fitted_contract(bindings=None,baseline=None):
    policy,original_bindings,base,profile,parents,poses=baseline_contract()
    if bindings is not None:original_bindings={k:bindings[k] for k in HASHES}
    if baseline is not None:base=deepcopy(baseline)
    policy['bindings']=original_bindings
    options={**original_bindings,'fit_sha256':'c'*64,'fitted_sha256':'d'*64}
    if bindings is not None:options.update(bindings)
    rest={n:{'parent':p,'matrix':matrix((0.,0.,0.))} for n,p in parents.items()}
    plan=read_fit_plan(policy,original_bindings,base,profile,parents)
    rows=[]
    for frame in range(1,6):
        rows.append({'frame':frame,'source_frame':frame,'target_global_poses':fit_frame(plan,poses,frame),
            'skin_sha256':f'{frame:064x}','raw_skin_sha256':f'{frame+10:064x}','triangle_sha256':f'{frame+20:064x}',
            'vertex_count':120,'triangle_count':120,'moved_vertices':0 if frame==1 else 20,
            'max_displacement_local':0. if frame==1 else .002,'max_bind_displacement_local':.2,
            'adjacent_max_displacement_local':0. if frame==1 else .001,
            'bind_strain':{'min_edge_length_ratio':.5,'max_edge_stretch_ratio':2.},
            'master_strain':{'min_edge_length_ratio':.5,'max_edge_stretch_ratio':2.},
            'skin_correction':{'corrected_vertices':30,'max_correction_local':.002}})
    joints=[{'bone':p['target'],'frames_measured':5,'max_swing_degrees':1.,'max_swing_frame':2,
             'max_twist_degrees':1.,'max_twist_frame':2,'max_step_degrees':1.,'max_step_frame':2} for p in profile['pairs'][1:]]
    # This deliberately declares UNAVAILABLE, not invented collision clearance.
    surface={'schema_version':1,'policy':'HAND_OPPOSITE_UPPER_LIMB_TRIANGLES_V1','bindings':dict(options),
             'status':'UNAVAILABLE','reason':'HAND_BRANCHES_UNAVAILABLE','hands':{'left':'other','right':'hand'},
             'region_bones':{},'region_vertex_counts':{},'frame_count':5,
             'frames':[{'frame':r['frame'],'skin_sha256':r['skin_sha256'],'triangle_sha256':r['triangle_sha256'],'left':None,'right':None} for r in rows],
             'contact_quality_verified':False,'engine_import_verified':False}
    data={'schema_version':1,'policy':POLICY,'bindings':dict(options),'measurement':'FRESH_SAVED_ACTION_V1',
          'frame_count':5,'source_first_frame':1,'fps':30.,'target_rest_frames':rest,'source_polygon_sha256':'e'*64,
          'mesh_world':matrix((0.,0.,0.)),'rig_world':matrix((0.,0.,0.)),
          'original_review_verification':reopen_report(original_bindings),'bind_edge_strain':deepcopy(base['bind_edge_strain']),
          'master_edge_strain':deepcopy(base['master_bind_edge_strain']),'frames':rows,'joint_motion_metrics':joints,
          'surface_review':surface,'angular_correction_metrics':{'max_speed_degrees_s':1.,'max_acceleration_degrees_s2':10.},
          'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    return policy,options,base,profile,rest,data


def record(path):return {'name':path.name,'bytes':path.stat().st_size,'sha256':sha256(path.read_bytes()).hexdigest()}


def stage_report(options,rest):
    return {'status':'REAL_NATIVE_FIT_ACTION_STAGED','bindings':dict(options),'frames':5,
            'original_review_verification':reopen_report({k:options[k] for k in HASHES}),
            'fitted_scene':{},'target_rest_frames':rest,'max_ik_residual':0.,'max_unkeyed_translation':0.,'max_scale_error':0.,
            'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}


def write_render_report(folder,options,data,images):
    """Synthetic bitmaps validate IO only; they are never physical render proof."""
    from ucc.jobs.private_render_evidence import png_measurements,VIEWS
    root=folder/'review_frames';root.mkdir()
    manifest={'schema_version':1,'method':'CYCLES_CPU_EVALUATED_SKIN_CLAY_V1','fit_bindings':dict(options),
              'scope':'BOUNDED_TARGET_FIT_NOT_SOURCE_FK_OR_CONTACT_APPROVAL','source_frame_count':5,
              'rendered_frames':[1,2,3,4,5],'animation_visual_quality_verified':False,'images':[]}
    for frame,image in enumerate(images,1):
        for view in VIEWS:
            path=root/f'frame_{frame:04}_{view}.png';path.write_bytes(image)
            manifest['images'].append({**record(path),'frame':frame,'view':view,'width':256,'height':384,
                **png_measurements(image),'evaluated_sha256':data['frames'][frame-1]['skin_sha256'],
                'camera_root_offset_world':[0.,0.,0.]})
    path=root/'manifest.json';path.write_text(json.dumps(manifest));index=root/'index.html';index.write_bytes(b'UNIT_ONLY_NOT_A_RENDERED_REVIEW')
    return {'status':'REAL_NATIVE_FIT_VERIFIED','bindings':dict(options),'frames_verified':5,
            'private_review_renders':{'manifest':record(path),'index':record(index),'image_count':15,'animation_visual_quality_verified':False},
            'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
