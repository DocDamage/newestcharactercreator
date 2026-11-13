"""Closed request/policy contracts; synthetic metadata is not Blender evidence."""
from copy import deepcopy
import unittest
from jsonschema import Draft202012Validator
import json
from pathlib import Path

from fixtures.contact_fit_contract import fixture
from ucc.animations.contact_fit import read_fit_plan,HASHES
from ucc.jobs.protocol import JobRequest
from ucc.core.errors import ValidationError
from blender_bridge.native_fit_policy import parse_fit,checked_job,job_hashes

ROOT=Path(__file__).resolve().parents[1]


class NativeFitProtocolTests(unittest.TestCase):
    def test_policy_matches_both_independent_boundaries_and_published_schema(self):
        v=fixture();application=read_fit_plan(*v[:5]);worker=parse_fit(*v[:5])
        self.assertEqual(application.chain,worker['chain']);self.assertEqual(application.offsets,tuple(worker['offsets']))
        Draft202012Validator(json.loads((ROOT/'docs/schemas/native-fit.v1.schema.json').read_text())).validate(v[0])

    def test_explicit_render_frames_are_sha_bound_ordered_and_closed(self):
        for frames in ([1,2,3,4,5],None,[1,2,3,4],[1,2,3,4,6],[1,2,3,3,5],[True,2,3,4,5],[5,4,3,2,1]):
            v=deepcopy(fixture());v[0]['render_frames']=frames
            if frames==[1,2,3,4,5] and type(frames[0]) is int:
                self.assertEqual(read_fit_plan(*v[:5]).render_frames,tuple(frames));self.assertEqual(parse_fit(*v[:5])['render_frames'],frames)
            else:
                with self.subTest(frames=frames),self.assertRaises(ValidationError):read_fit_plan(*v[:5])
                with self.assertRaises(ValueError):parse_fit(*v[:5])

    def test_worker_rejects_bad_numeric_hierarchy_fps_coverage_and_schema(self):
        for case in ('bool','huge','nan','amplitude','step','cycle','side','root','fps','crop','field','version'):
            v=deepcopy(fixture());d,b,base,profile,parents,_=v
            if case=='bool':d['frames'][2]['offset_world'][0]=True
            if case=='huge':d['frames'][2]['offset_world'][0]=10**400
            if case=='nan':d['frames'][2]['offset_world'][0]=float('nan')
            if case=='amplitude':d['frames'][2]['offset_world'][0]=.031
            if case=='step':d['frames'][2]['offset_world'][0]=.02
            if case=='cycle':parents['helper']='hand'
            if case=='side':d['chain']['side']='left'
            if case=='root':d['chain']['upper_arm']='root'
            if case=='fps':d['fps']=24.
            if case=='crop':d['frames'].pop()
            if case=='field':d['allow_bad_skin']=True
            if case=='version':d['schema_version']=True
            with self.subTest(case=case),self.assertRaises(ValueError):parse_fit(*v[:5])
            with self.assertRaises(ValidationError):read_fit_plan(*v[:5])

    def test_render_selection_cannot_hide_the_entire_fitting_interval(self):
        v=deepcopy(fixture());v[2]['source_frame_count']=8
        v[0]['frames'].extend({'frame':i,'offset_world':[0.,0.,0.]} for i in (6,7,8))
        v[0]['render_frames']=[1,5,6,7,8]
        with self.assertRaises(ValidationError):read_fit_plan(*v[:5])
        with self.assertRaises(ValueError):parse_fit(*v[:5])

    def test_all_three_jobs_have_exact_hashes_fixed_paths_and_no_override_flags(self):
        schema=Draft202012Validator(json.loads((ROOT/'docs/schemas/worker-job.v1.schema.json').read_text()))
        for operation in ('fit_native_fbx_body','measure_native_fit','verify_native_fit'):
            options={k:'a'*64 for k in job_hashes(operation)}
            request=JobRequest.new(operation,input_project='candidate.blend',options=options)
            self.assertEqual(checked_job(request.as_dict()),options);schema.validate(request.as_dict())
            for fault in ('missing','extra','bool_hash','wrong_path','weak_hash'):
                bad=deepcopy(request.as_dict())
                if fault=='missing':bad['options'].pop('fit_sha256')
                if fault=='extra':bad['options']['skip_reopen']=True
                if fault=='bool_hash':bad['options']['fit_sha256']=True
                if fault=='wrong_path':bad['input_project']='review_motion.blend'
                if fault=='weak_hash':bad['options']['fit_sha256']='a'*63
                with self.subTest(operation=operation,fault=fault),self.assertRaises(ValidationError):JobRequest.from_dict(bad)
                with self.assertRaises(ValueError):checked_job(bad)
                self.assertTrue(list(schema.iter_errors(bad)))


if __name__=='__main__':unittest.main()
