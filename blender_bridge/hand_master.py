"""Real asset-coordinate installation into the original continuous MPFB skin."""
import math

from blender_bridge.face_geometry import intake,evaluated,points_digest,key_state,invariant_state,rest_state
from blender_bridge.hand_assets import _source,check_saved_asset,_properties
from blender_bridge.hand_geometry import source_context,observe_asset
from blender_bridge.hand_policy import OWN_KEY,TARGETS,state_digest


def asset_payloads(bpy,root,manifest):
    """Read genuine standalone meshes before opening the master; no orphan imports."""
    payloads={}
    for variant,_,target_sha in TARGETS:
        _,_,region,expected,_=_source(bpy,root,variant,source_file='original.blend')
        row=manifest['assets'][variant]
        if state_digest(expected) != row['observation_sha256']:
            raise ValueError('Hand asset is not compatible with the bound original master')
        obj,rig=check_saved_asset(bpy,root/('hand-'+variant+'.blend'),expected,
                                  _properties(manifest['recipe'],variant,target_sha))
        payloads[variant]={'asset':observe_asset(bpy,obj,rig),'region':region}
    return payloads


def observe_master(bpy,human,rig,targets):
    full=evaluated(bpy,human,full=True);visible=evaluated(bpy,human)
    if len(full) != 19158 or len(visible) != 13380:
        raise ValueError('Hand master lost original full/visible source indexing')
    return {'invariants':invariant_state(bpy,human,rig,targets),
            'all_keys':{k.name:key_state(k) for k in human.data.shape_keys.key_blocks},
            'rest':rest_state(rig),'full_coordinates_sha256':points_digest(full),
            'visible_coordinates_sha256':points_digest(visible),
            'ownership':{k:human[k] for k in human.keys() if k.startswith('ucc_hand_')}}


def reconstruct(bpy,root,manifest,payloads,selection):
    human,rig,service,targets=source_context(bpy,root/'original.blend')
    before_keys={k.name:key_state(k) for k in human.data.shape_keys.key_blocks}
    if selection == 'neutral':
        return human,rig,targets,observe_master(bpy,human,rig,targets)
    payload=payloads[selection];asset=payload['asset'];region=payload['region']
    original=evaluated(bpy,human,full=True)
    basis=[tuple(v.co) for v in human.data.shape_keys.key_blocks[0].data]
    own=human.shape_key_add(name=OWN_KEY,from_mix=False)
    if own.name != OWN_KEY:
        raise ValueError('Hand key ownership collision')
    own.data.foreach_set('co',[x for point in basis for x in point]);own.value=.25
    for index,point in zip(asset['source_ids'],asset['key_coordinates']):
        own.data[index].co=point
    _,filename,target_sha=next(row for row in TARGETS if row[0] == selection)
    reference=targets.load_target(human,str(root/filename),weight=0.)
    try:
        for index in region['helper_ids'][selection]:
            own.data[index].co=reference.data[index].co
    finally:
        human.shape_key_remove(reference)
    service.refit(human)
    if before_keys != {k.name:key_state(k) for k in human.data.shape_keys.key_blocks if k.name != OWN_KEY}:
        raise ValueError('Hand installation changed an original body/face shape key')
    if state_digest(rest_state(rig)) != state_digest(asset['rest']):
        raise ValueError('Installed real hand does not reproduce its exact default bind rig')
    actual=evaluated(bpy,human,full=True)
    allowed=set(region['ids'])|set(region['helper_ids'][selection])
    if (max(math.dist(a,b) for i,(a,b) in enumerate(zip(original,actual)) if i not in allowed) >= 1e-6
            or max(math.dist(original[i],actual[i]) for i in region['border']) >= 1e-6
            or max(math.dist(actual[i],point) for i,point in zip(asset['source_ids'],asset['points'])) >= 1e-6):
        raise ValueError('Joined hand violates source preservation, asset coordinates or fixed wrist border')
    for name,value in _properties(manifest['recipe'],selection,target_sha).items():
        human[name]=value
    human['ucc_hand_asset_sha256']=manifest['assets'][selection]['sha256']
    human['ucc_hand_manifest_sha256']=state_digest(manifest)
    return human,rig,targets,observe_master(bpy,human,rig,targets)


def observe_saved(bpy,path):
    """Read only: never reset keys, repair the rig or apply a target here."""
    bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False)
    human,rig,_,targets=intake(bpy)
    return human,rig,targets,observe_master(bpy,human,rig,targets)
