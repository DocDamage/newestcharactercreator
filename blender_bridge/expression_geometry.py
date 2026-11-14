"""Actual neutral keys and independent gzip/float32 reference construction."""
from array import array
import gzip
import importlib
import math

from blender_bridge.expression_policy import TARGETS, FAMILIES, PREFIX, filename, keyname
from blender_bridge.face_geometry import (
    evaluated, float32, invariant_state, key_state, points_digest, rest_state,
)
from blender_bridge.face_operations import state_digest


def target_rows(path) -> dict:
    rows = {}
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for raw in stream:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            words = line.split()
            if len(words) != 4:
                raise ValueError('Invalid expression target row')
            index = int(words[0]); x, y, z = map(float, words[1:])
            if index in rows or not 0 <= index < 19158 or not all(math.isfinite(v) for v in (x, y, z)):
                raise ValueError('Invalid expression target index or displacement')
            rows[index] = (x, -z, y)
    if not rows:
        raise ValueError('Empty expression target')
    return rows


def source_state(bpy, human, rig, targets, *, strip_expression: bool = False) -> dict:
    invariant = invariant_state(bpy, human, rig, targets)
    all_keys = {k.name: key_state(k) for k in human.data.shape_keys.key_blocks}
    if strip_expression:
        invariant['keys'] = {n: v for n, v in invariant['keys'].items() if not n.startswith(PREFIX)}
        invariant['key_order'] = [n for n in invariant['key_order'] if not n.startswith(PREFIX)]
        all_keys = {n: v for n, v in all_keys.items() if not n.startswith(PREFIX)}
    full = evaluated(bpy, human, full=True); visible = evaluated(bpy, human)
    if len(full) != 19158 or len(visible) != 13380:
        raise ValueError('Expression preparation requires pinned full and masked skin indexing')
    return {'invariants_sha256': state_digest(invariant), 'all_keys': all_keys,
            'rest_sha256': state_digest(rest_state(rig)), 'active_key_index': human.active_shape_key_index,
            'full_sha256': points_digest(full), 'visible_sha256': points_digest(visible)}


def build_keys(bpy, root, human, targets, *, manual: bool) -> tuple:
    keys = human.data.shape_keys.key_blocks
    if any(k.name.startswith(PREFIX) for k in keys):
        raise ValueError('Expression preparation refuses existing or ambiguous reserved keys')
    module = importlib.import_module(targets.__module__)
    scale = module.GeneralObjectProperties.get_value('scale_factor', entity_reference=human)
    race = targets.get_macro_info_dict_from_basemesh(human)['race']
    if (type(scale) not in (int, float) or not math.isfinite(scale) or abs(scale-.1) > 1e-6
            or type(race) is not dict or set(race) != set(FAMILIES)
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in race.values())
            or not .98 <= sum(race.values()) <= 1.02):
        raise ValueError('Unsupported MPFB expression scale or actual race mix')
    basis = keys['Basis']; active = human.active_shape_key_index
    base = array('f', [0.])*(len(basis.data)*3); basis.data.foreach_get('co', base)
    loaded = {}; support = {}
    for role, family, _ in TARGETS:
        name = keyname(role, family); path = root/filename(role, family)
        rows = target_rows(path)
        support.setdefault(role, set()).update(i for i, d in rows.items() if any(d))
        if manual:
            values = array('f', base)
            for index, delta in rows.items():
                for axis in range(3):
                    values[index*3+axis] = float32(base[index*3+axis]+delta[axis]*scale)
            key = human.shape_key_add(name=name, from_mix=False)
            key.relative_key = basis; key.data.foreach_set('co', values); key.value = 0.
        else:
            key = targets.load_target(human, str(path), weight=0., name=name)
        if key.name != name or key.relative_key != basis or key.value != 0.:
            raise ValueError('Expression loader did not create the exact neutral key')
        loaded[(role, family)] = key
    human.active_shape_key_index = active
    bpy.context.view_layer.update()
    return loaded, support, race, scale


def exercise(bpy, human, rig, targets, loaded: dict, support: dict, race: dict, baseline: dict) -> dict:
    """Check bounded real skin motion and exact restoration; never certify appearance."""
    base = evaluated(bpy, human, full=True); result = {}
    for role in support:
        rows = []
        for strength in (0., .25, .5, .25, 0.):
            for (other, family), key in loaded.items():
                key.value = strength*race[family] if other == role else 0.
            bpy.context.view_layer.update()
            full = evaluated(bpy, human, full=True); visible = evaluated(bpy, human)
            distances = [math.dist(a, b) for a, b in zip(base, full)]
            if (len(full) != len(base) or max(distances) > .03
                    or max((d for i, d in enumerate(distances) if i not in support[role]), default=0.) > 1e-6
                    or state_digest(rest_state(rig)) != baseline['rest_sha256']
                    or any(key_state(human.data.shape_keys.key_blocks[n]) != v for n, v in baseline['all_keys'].items())
                    or any(k.value != float32(strength*race[f] if r == role else 0.) for (r, f), k in loaded.items())):
                raise ValueError('Expression motion violates its original-key/rig/support/displacement bounds')
            full_sha = points_digest(full); visible_sha = points_digest(visible)
            moved = sum(d > 1e-6 for d in distances)
            if strength:
                if moved < 16 or full_sha == baseline['full_sha256']:
                    raise ValueError('Expression target produced no meaningful real deformation')
            elif full_sha != baseline['full_sha256'] or visible_sha != baseline['visible_sha256']:
                raise ValueError('Expression did not restore exact original neutral skin')
            rows.append({'strength': strength, 'full_sha256': full_sha, 'visible_sha256': visible_sha,
                         'maximum_displacement': max(distances), 'moved_vertices_over_1um': moved})
        if len({r['full_sha256'] for r in rows}) != 3 or rows[1] != rows[3]:
            raise ValueError('Expression skin samples are not deterministic')
        result[role] = {'support_vertices': len(support[role]), 'samples': rows}
    if source_state(bpy, human, rig, targets, strip_expression=True) != baseline:
        raise ValueError('Expression exercise changed original character state')
    return result
