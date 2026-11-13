"""Independent native anatomical scope checks; no Blender dependencies."""
from ucc.core.errors import ValidationError


def expected_volume_regions(profile,parents,deform):
    paths={}
    for name in parents:
        path=[];current=name
        while current is not None:
            if current not in parents or current in path:raise ValidationError('Invalid enclosure hierarchy')
            path.append(current);current=parents[current]
        paths[name]=path
    hands={s:profile['landmarks'][s+'_hand']['target'] for s in ('left','right')}
    common=next((n for n in paths[hands['left']] if n in paths[hands['right']]),None)
    if common is None:raise ValidationError('Enclosure hands have no common ancestor')
    mapped={p['target'] for p in profile['pairs']};roots={}
    for side in ('left','right'):
        path=paths[hands[side]];chain=[n for n in path[:path.index(common)] if n in mapped]
        if len(chain)!=4:raise ValidationError('Enclosure requires a declared four-role arm chain')
        roots[side+'_arm']=chain[2];roots[side+'_leg']=profile['landmarks'][side+'_hip']['target']
    if (len(set(roots.values()))!=4 or any(n not in deform for n in roots.values()) or
        any(a in paths[b] for a in roots.values() for b in roots.values() if a!=b)):
        raise ValidationError('Enclosure limb branches differ')
    regions={s+'_hand':{n for n in deform if hands[s] in paths[n]} for s in ('left','right')}
    regions['central_body']={n for n in deform if not any(root in paths[n] for root in roots.values())}
    if (profile['landmarks']['head']['target'] not in regions['central_body'] or not all(regions.values()) or
        any(regions[a]&regions[b] for a in regions for b in regions if a<b) or
        any(roots[s+'_arm'] not in paths[n] for s in ('left','right') for n in regions[s+'_hand'])):
        raise ValidationError('Enclosure anatomical partition differs')
    return {k:sorted(v) for k,v in regions.items()},roots


def checked_ids(value,maximum,*,nonempty=False,limit=None):
    if (type(value) is not list or (nonempty and not value) or len(value)>(maximum if limit is None else limit) or
        any(type(v) is not int or not 0<=v<maximum for v in value) or value!=sorted(set(value))):
        raise ValidationError('Invalid complete enclosure identities')
    return set(value)
