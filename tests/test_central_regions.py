"""Original nonshipping hierarchy cases, never actual-rig compatibility proof."""
from copy import deepcopy
import unittest

from blender_bridge.central_regions import volume_regions


def hierarchy():
    parents={'root':None,'spine':'root','head':'spine','jaw':'head','breast':'spine','pelvis':'root'}
    for s in ('L','R'):
        parents.update({f'clav{s}':'spine',f'upper{s}':f'clav{s}',f'twist{s}':f'upper{s}',
            f'lower{s}':f'twist{s}',f'hand{s}':f'lower{s}',f'finger{s}':f'hand{s}',
            f'hip{s}':'pelvis',f'shin{s}':f'hip{s}',f'foot{s}':f'shin{s}'})
    landmarks={f'{side}_{role}':{'target':f'{prefix}{suffix}'} for side,suffix in (('left','L'),('right','R'))
        for role,prefix in (('hand','hand'),('hip','hip'))};landmarks['head']={'target':'head'}
    mapped=set(parents)-{'twistL','twistR','jaw','breast','pelvis'}
    profile={'landmarks':landmarks,'pairs':[{'target':n} for n in sorted(mapped)]}
    return profile,parents,set(parents)


class CentralRegionTests(unittest.TestCase):
    def test_complete_trunk_keeps_helpers_and_excludes_all_four_limbs(self):
        profile,parents,deform=hierarchy();regions,roots=volume_regions(profile,parents,deform)
        self.assertEqual(roots,{'left_arm':'upperL','right_arm':'upperR','left_leg':'hipL','right_leg':'hipR'})
        self.assertEqual(regions['central_body'],{'root','spine','head','jaw','breast','pelvis','clavL','clavR'})
        self.assertEqual(regions['left_hand'],{'handL','fingerL'});self.assertEqual(regions['right_hand'],{'handR','fingerR'})
        self.assertNotIn('twistL',regions['central_body'])

    def test_no_helper_or_source_name_guess_replaces_missing_declared_arm_roles(self):
        profile,parents,deform=hierarchy();profile['pairs']=[p for p in profile['pairs'] if p['target']!='clavL']
        with self.assertRaisesRegex(ValueError,'MAPPED_ARM_CHAIN'):volume_regions(profile,parents,deform)
        profile,parents,deform=hierarchy();profile['pairs'].append({'target':'twistL'})
        with self.assertRaisesRegex(ValueError,'MAPPED_ARM_CHAIN'):volume_regions(profile,parents,deform)

    def test_cycles_multiple_roots_unknown_targets_and_nested_legs_reject(self):
        for case in ('cycle','roots','unknown','nested','duplicate','head_in_arm'):
            profile,parents,deform=hierarchy()
            if case=='cycle':parents['spine']='head'
            if case=='roots':parents['breast']=None
            if case=='unknown':profile['pairs'].append({'target':'missing'})
            if case=='nested':profile['landmarks']['left_hip']['target']='clavL'
            if case=='duplicate':profile['pairs'].append(deepcopy(profile['pairs'][0]))
            if case=='head_in_arm':parents['head']='handL'
            with self.subTest(case=case),self.assertRaises(ValueError):volume_regions(profile,parents,deform)

    def test_roles_are_bound_to_actual_explicit_names_without_suffix_aliases(self):
        profile,parents,deform=hierarchy();renamed={n:f'actual_{i}' for i,n in enumerate(parents)}
        new_parents={renamed[n]:renamed[p] if p is not None else None for n,p in parents.items()}
        for row in profile['pairs']:row['target']=renamed[row['target']]
        for row in profile['landmarks'].values():row['target']=renamed[row['target']]
        regions,roots=volume_regions(profile,new_parents,{renamed[n] for n in deform})
        self.assertIn(renamed['breast'],regions['central_body']);self.assertEqual(roots['right_arm'],renamed['upperR'])
