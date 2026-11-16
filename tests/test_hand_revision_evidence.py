"""Invented scalar contract fixtures only; not real geometry/pose evidence."""
from copy import deepcopy
import unittest

from ucc.core.hand_parts import POLICY,TARGETS,METADATA_SHA256
from ucc.core.errors import ValidationError
from ucc.jobs.geometry_evidence import EvidenceError
from ucc.jobs.hand_revision_evidence import validate_revision_evidence
from ucc.jobs.protocol import JobRequest


def contract():
    options={'manifest_sha256':'a'*64,'master_sha256':'b'*64,'original_master_sha256':'b'*64,
             'metadata_sha256':METADATA_SHA256,**{t.variant+'_target_sha256':t.sha256 for t in TARGETS},
             'shorter_asset_sha256':'e'*64,'longer_asset_sha256':'f'*64,
             'current_selection':'neutral','selection':'shorter'}
    common={'schema_version':1,'policy':POLICY,'manifest_sha256':'a'*64,
            'source_master_sha256':'b'*64,'original_master_sha256':'b'*64,
            'current_selection':'neutral','selection':'shorter','scene_sha256':'c'*64,
            'observation_sha256':'d'*64,'selection_changed':True,'visual_quality_approved':False,
            'penetration_quality_approved':False,'engine_import_verified':False}
    poses=[{'bone':name,'axis':axis,'degrees':angle,'skin_sha256':'2'*64,'normals_sha256':'3'*64,
            'moved_vertices_over_1um':1700,'maximum_displacement':.01,
            'potential_hand_body_overlaps':0,'potential_hand_self_overlaps':0}
           for name,axes in [('wrist.L',(0,1,2)),*[(f'finger{i}-1.L',(0,)) for i in range(1,6)],
                             ('finger2-2.L',(0,)),('finger5-2.L',(0,))]
           for axis in axes for angle in (-20,20)]
    return options,dict(common,blender_version='5.3.0'),dict(common,verified_reopen=True,
                    skin_poses=poses,all40_restores_exact=True)


class HandRevisionEvidenceTests(unittest.TestCase):
    def test_closed_scalar_receipt_keeps_quality_unapproved(self):
        options,stage,proof=contract();result=validate_revision_evidence(stage,proof,options,'c'*64)
        self.assertEqual(result['actual_skin_pose_checks'],40)
        self.assertFalse(result['penetration_quality_approved'])
        proof['skin_poses'][0]['potential_hand_self_overlaps']=2
        result=validate_revision_evidence(stage,proof,options,'c'*64)
        self.assertEqual(result['potential_overlap_poses'],1)
        self.assertFalse(result['visual_quality_approved'])

    def test_partial_rebound_forged_or_duplicate_pose_evidence_rejects(self):
        mutations=[lambda p:p.update(verified_reopen=1),lambda p:p.update(all40_restores_exact=1),
                   lambda p:p.update(selection_changed=1),lambda p:p.update(schema_version=True),
                   lambda p:p.update(penetration_quality_approved=True),
                   lambda p:p.update(observation_sha256='f'*64),lambda p:p.update(extra=True),
                   lambda p:p['skin_poses'].pop(),lambda p:p['skin_poses'][0].pop('normals_sha256'),
                   lambda p:p['skin_poses'][0].update(moved_vertices_over_1um=True),
                   lambda p:p['skin_poses'][0].update(maximum_displacement=float('nan')),
                   lambda p:p['skin_poses'][0].update(potential_hand_body_overlaps=-1),
                   lambda p:p['skin_poses'].__setitem__(0,deepcopy(p['skin_poses'][1]))]
        for mutate in mutations:
            options,stage,proof=contract();mutate(proof)
            with self.subTest(proof=proof),self.assertRaises(EvidenceError):
                validate_revision_evidence(stage,proof,options,'c'*64)

    def test_revision_protocol_requires_current_receipt_only_for_active_part(self):
        from pathlib import Path
        import json
        try:from jsonschema import Draft202012Validator
        except ImportError:Draft202012Validator=None
        schema=json.loads((Path(__file__).parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text())
        validator=Draft202012Validator(schema) if Draft202012Validator else None
        for operation in ('stage_mpfb_hand_revision','verify_mpfb_hand_revision'):
            for current in ('neutral','shorter','longer'):
                options,_,_=contract();options['current_selection']=current
                if current!='neutral':options['current_observation_sha256']='1'*64
                if operation.startswith('verify'):options.update(revised_sha256='c'*64,revision_report_sha256='d'*64)
                request=JobRequest.new(operation,input_project='candidate.blend',options=options)
                if validator:validator.validate(request.as_dict())
                for field in options:
                    broken=dict(options);del broken[field]
                    with self.subTest(operation=operation,current=current,field=field),self.assertRaises(ValidationError):
                        JobRequest.new(operation,input_project='candidate.blend',options=broken)
                    if validator:
                        raw=request.as_dict();raw['options']=broken
                        self.assertTrue(list(validator.iter_errors(raw)))
                if current=='neutral':
                    broken=dict(options,current_observation_sha256='1'*64)
                    with self.assertRaises(ValidationError):JobRequest.new(operation,input_project='candidate.blend',options=broken)
                    if validator:
                        raw=request.as_dict();raw['options']=broken
                        self.assertTrue(list(validator.iter_errors(raw)))


if __name__=='__main__':unittest.main()
