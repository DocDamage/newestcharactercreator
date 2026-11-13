"""Complete measured torso/head complement of explicitly mapped limb branches."""
from blender_bridge.body_contact_regions import central_regions


def volume_regions(profile: dict,parents: dict,deform: set) -> tuple[dict,dict]:
    """Retain facial, breast, pelvis and other trunk helper deform bones.

    Supported native mappings declare hand, lower-arm, upper-arm and clavicle
    along each real hand ancestry. Helper joints between those mapped roles are
    preserved. A different declared chain is unsupported, never guessed by name.
    """
    landmarks=profile.get('landmarks') if type(profile) is dict else None
    pairs=profile.get('pairs') if type(profile) is dict else None
    required=('left_hand','right_hand','left_hip','right_hip','head')
    if (type(landmarks) is not dict or any(type(landmarks.get(k)) is not dict or
        type(landmarks[k].get('target')) is not str for k in required) or type(pairs) is not list or not 1<=len(pairs)<=64 or
        any(type(p) is not dict or type(p.get('target')) is not str for p in pairs)):
        raise ValueError('CENTRAL_VOLUME_MAPPING_UNAVAILABLE')
    hands={s:landmarks[s+'_hand']['target'] for s in ('left','right')};head=landmarks['head']['target']
    if type(deform) is not set:raise ValueError('CENTRAL_VOLUME_DEFORM_UNAVAILABLE')
    existing=central_regions(parents,hands,head,deform)
    def ancestors(name):
        path=[]
        while name is not None:
            if name not in parents or name in path:raise ValueError('CENTRAL_VOLUME_HIERARCHY_UNAVAILABLE')
            path.append(name);name=parents[name]
        return path
    paths={name:ancestors(name) for name in parents};mapped={p['target'] for p in pairs}
    if len(mapped)!=len(pairs) or not mapped<=set(parents):raise ValueError('CENTRAL_VOLUME_MAPPING_UNAVAILABLE')
    common=next(n for n in paths[hands['left']] if n in paths[hands['right']])
    roots={s+'_leg':landmarks[s+'_hip']['target'] for s in ('left','right')}
    for side in ('left','right'):
        path=paths[hands[side]];chain=[n for n in path[:path.index(common)] if n in mapped]
        if len(chain)!=4:raise ValueError('CENTRAL_VOLUME_MAPPED_ARM_CHAIN_UNAVAILABLE')
        roots[side+'_arm']=chain[2]
    if (len(set(roots.values()))!=4 or any(n not in deform for n in roots.values()) or
        any(a in paths[b] for a in roots.values() for b in roots.values() if a!=b)):
        raise ValueError('CENTRAL_VOLUME_LIMB_BRANCHES_UNAVAILABLE')
    limbs={n for n in deform if any(root in paths[n] for root in roots.values())};trunk=deform-limbs
    if head not in trunk or not trunk:raise ValueError('CENTRAL_VOLUME_TRUNK_UNAVAILABLE')
    for side in ('left','right'):
        if not all(roots[side+'_arm'] in paths[n] for n in existing[side+'_hand']):
            raise ValueError('CENTRAL_VOLUME_HAND_BRANCH_UNAVAILABLE')
    return {**{s+'_hand':existing[s+'_hand'] for s in ('left','right')},'central_body':trunk},roots
