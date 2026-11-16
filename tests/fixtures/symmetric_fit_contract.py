"""Invented numeric branches only; no Blender, skin or asset compatibility proof."""
from copy import deepcopy
import math
from ucc.animations.contact_fit import HASHES, POLICY as BASE_POLICY, read_fit_plan, fit_frame
from ucc.animations.symmetric_fit import POLICY, BASE_HASHES
from .contact_fit_contract import matrix


def fixture():
    names = ['root', 'clavL', 'upperL', 'lowerL', 'handL', 'fingerL',
             'clavR', 'upperR', 'lowerR', 'handR', 'fingerR', 'head', 'footL', 'footR']
    positions = [(0.,0.,0.), (.1,0.,1.5), (.25,0.,1.5), (.45,.1,1.3), (.3,.2,1.1), (.22,.23,1.08),
                 (-.1,0.,1.5), (-.25,0.,1.5), (-.45,.1,1.3), (-.3,.2,1.1), (-.22,.23,1.08),
                 (0.,0.,1.7), (.1,0.,0.), (-.1,0.,0.)]
    poses = [matrix(p) for p in positions]
    parents = {'root':None, 'head':'root', 'footL':'root', 'footR':'root'}
    for side in ('L','R'):
        parents.update({f'clav{side}':'root', f'upper{side}':f'clav{side}',
                        f'helper{side}':f'upper{side}', f'lower{side}':f'helper{side}',
                        f'hand{side}':f'lower{side}', f'finger{side}':f'hand{side}'})
    profile = {'pairs':[{'target':n} for n in names],
               'landmarks':{'left_hand':{'target':'handL'}, 'right_hand':{'target':'handR'}},
               'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1',
               'mesh_strain_reference':'TRUE_NEUTRAL_BIND_V2'}
    baseline = {'neutral_target_helpers':['helperL','helperR'], 'source_frame_count':21, 'fps':30.,
                'mapped_pairs':deepcopy(profile['pairs']), 'target_anatomical_landmarks':{
                    'head':[0.,0.,1.7], 'left_foot':[.1,0.,0.], 'right_foot':[-.1,0.,0.]}}
    source_bindings = {k:'a'*64 for k in HASHES}
    base_policy = {'schema_version':1, 'policy':BASE_POLICY, 'bindings':source_bindings,
                   'coordinate_space':'BLENDER_WORLD_METERS', 'fps':30.,
                   'chain':{'side':'right','upper_arm':'upperR','forearm':'lowerR','hand':'handR'},
                   'frames':[{'frame':f,'offset_world':[({2:.0005,3:.001,4:.0005}.get(f,0.)),0.,0.]} for f in range(1,22)]}
    base = read_fit_plan(base_policy, source_bindings, baseline, profile, parents)
    bindings = {**source_bindings, **{k:'b'*64 for k in BASE_HASHES}}
    frames = []
    for f in range(1,22):
        bump = math.sin(math.pi*(f-7)/14)**2 if 7 < f < 21 else 0.
        row = {'frame':f}
        for side,sign in (('left',1.),('right',-1.)):
            row[side+'_offset_world'] = [sign*.003*bump,-.005*bump,0.]
            row[side+'_clavicle_rotation_world_degrees'] = [0.,0.,sign*bump]
            row[side+'_hand_rotation_local_degrees'] = [v*bump for v in ((0.,0.,0.) if side=='left' else (.2,-.1,.3))]
        frames.append(row)
    data = {'schema_version':1,'policy':POLICY,'bindings':deepcopy(bindings),'coordinate_space':'BLENDER_WORLD_METERS',
            'fps':30.,'chains':{s:{'clavicle':'clav'+t,'upper_arm':'upper'+t,'forearm':'lower'+t,'hand':'hand'+t}
                               for s,t in (('left','L'),('right','R'))},'frames':frames,'render_frames':[1,8,14,20,21]}
    originals = [deepcopy(poses) for _ in frames]
    bases = [fit_frame(base, p, f) for f,p in enumerate(originals,1)]
    return data,bindings,baseline,profile,parents,base,originals,bases
