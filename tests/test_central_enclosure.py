"""Parser, protocol and publication faults; synthetic data is not physical proof."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from blender_bridge.anatomical_review import OPERATIONS,checked_anatomical_job
from fixtures.central_enclosure_contract import central_contract
from ucc.core.errors import ValidationError
from ucc.jobs.enclosure_fit_guard import require_enclosure_fit_guard
from ucc.jobs.protocol import JobRequest
from ucc.preview.central_enclosure import _variant,CentralEnclosure,EnclosureVariant,validate_anatomical_receipt


class CentralEnclosureTests(unittest.TestCase):
    def setUp(self):self.data,self.cache,self.body,self.polygons,self.profile=central_contract()

    def load(self,**kwargs):return _variant(self.data,self.cache,self.body,self.polygons,self.profile,**kwargs)

    def test_complete_original_geometry_reproduces_from_immutable_cache(self):
        result=self.load();self.assertEqual(len(result.inside),3)
        self.assertEqual(result.inside,((frozenset(),frozenset()),)*3)
        self.assertEqual(result.inside,result.ambiguous)

    def test_scope_topology_geometry_classification_and_budget_fabrications_reject(self):
        original=deepcopy(self.data)
        for case in ('world','root','region','membership','shared','coverage','frame','skin','triangle','body','pivot','origin',
                     'bounds','cap','boundary','volume','offset','diagonal','audit','audit_bool','adjacent','queries','bool',
                     'selection','inside','unknown','digest','missing'):
            self.data=deepcopy(original);d=self.data;row=d['frames'][0];obs=row['observation'];hit=obs['left']
            if case=='world':d['world_matrix'][0]=True
            if case=='root':d['limb_roots']['left_arm']='Lhand'
            if case=='region':d['region_bones']['central_body'].pop()
            if case=='membership':d['region_vertex_ids']['central_body'].pop()
            if case=='shared':d['region_vertex_ids']['left_hand'][0]=0
            if case=='coverage':d['frames'].pop()
            if case=='frame':row['frame']=True
            if case=='skin':row['skin_sha256']='0'*64
            if case=='triangle':row['triangle_sha256']='0'*64
            if case=='body':obs['body_triangle_ids'].pop()
            if case=='pivot':obs['pivot_local'][0]+=.1
            if case=='origin':obs['origin_world'][1]+=.1
            if case=='bounds':obs['bounds'][0][0]-=.1
            if case=='cap':obs['cap_boxes'][0][0][0]-=.1
            if case=='boundary':obs['boundaries'][0].reverse()
            if case=='volume':obs['signed_volume_world']*=2
            if case=='offset':obs['offset_world']*=2
            if case=='diagonal':obs['diagonal_world']*=2
            if case=='audit':obs['body_surface_audit']['candidate_pairs']=1000001
            if case=='audit_bool':obs['body_surface_audit']['nonadjacent_pairs']=False
            if case=='adjacent':obs['body_surface_audit']['adjacent_fold_quality_verified']=True
            if case=='queries':obs['ray_queries']=1000001
            if case=='bool':hit['selected_triangles']=[True]
            if case=='selection':hit['selected_triangles'].pop()
            if case=='inside':hit['inside_polygons']=[0]
            if case=='unknown':hit['ambiguous_triangles']=hit['selected_triangles'][:1]
            if case=='digest':hit['classification_sha256']='0'*64
            if case=='missing':obs.pop('cap_boxes')
            with self.subTest(case=case),self.assertRaises(ValidationError):self.load()

    def test_cancellation_never_returns_partial_frame_verdicts(self):
        def cancelled():raise RuntimeError('unit cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.load(cancel_check=cancelled)

    def test_combined_receipt_cannot_omit_or_substitute_either_report_binding(self):
        bindings={k:'a'*64 for k in ('source_sha256','snapshot_sha256','mapping_sha256','master_sha256','review_sha256','timeline_sha256')}
        report={'report':{'sha256':'b'*64},'enclosure_report':{'sha256':'c'*64}}
        receipt={'status':'REAL_ANATOMICAL_SAFETY_VERIFIED','bindings':{**bindings,'body_review_sha256':'b'*64,
            'enclosure_review_sha256':'c'*64},'frames_verified':3,'paired':False,'originals_unchanged':True,
            'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
        baseline={'source_frame_count':3}
        validate_anatomical_receipt(receipt,bindings,baseline,False,report)
        for fault in ('area','enclosure','old_status','approval','partial','bool','paired','extra'):
            bad=deepcopy(receipt)
            if fault=='area':bad['bindings']['body_review_sha256']='d'*64
            if fault=='enclosure':bad['bindings'].pop('enclosure_review_sha256')
            if fault=='old_status':bad['status']='REAL_NATIVE_BODY_CONTACTS_VERIFIED'
            if fault=='approval':bad['contact_quality_verified']=True
            if fault=='partial':bad['frames_verified']=2
            if fault=='bool':bad['frames_verified']=True
            if fault=='paired':bad['paired']=True
            if fault=='extra':bad['allow_unknown']=True
            with self.subTest(fault=fault),self.assertRaises(ValidationError):
                validate_anatomical_receipt(bad,bindings,baseline,False,report)

    def test_both_reports_are_required_in_closed_two_process_protocol(self):
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text(encoding='utf-8'))
        clauses={c.get('if',{}).get('properties',{}).get('operation',{}).get('const'):c for c in schema['allOf']}
        for operation,fields in OPERATIONS.items():
            self.assertIn(operation,schema['properties']['operation']['enum'])
            contract=clauses[operation]['then']['properties']['options']
            from ucc.animations.symmetric_fit import BASE_HASHES as LAYER_HASHES
            optional=LAYER_HASHES if 'fitted_sha256' in fields else set()
            self.assertEqual(set(contract['required']),fields)
            self.assertEqual(set(contract['properties']),fields|optional)
            if optional:
                self.assertEqual({k:set(v) for k,v in contract['dependentRequired'].items()},
                                 {k:optional-{k} for k in optional})
            self.assertIs(contract['additionalProperties'],False)
            options={k:'a'*64 for k in fields}
            job=JobRequest.new(operation,input_project='candidate.blend',options=options)
            self.assertEqual(checked_anatomical_job(job.as_dict()),options)
            for key in fields:
                malformed={k:v for k,v in options.items() if k!=key}
                with self.subTest(operation=operation,key=key),self.assertRaises(ValidationError):
                    JobRequest.new(operation,input_project='candidate.blend',options=malformed)
            options['allow_unknown']=True
            with self.assertRaises(ValidationError):JobRequest.new(operation,input_project='candidate.blend',options=options)
            with self.assertRaises(ValueError):checked_anatomical_job({**job.as_dict(),'options':options})

    def test_new_enclosed_or_uncertain_polygons_reject_per_hand_even_if_totals_shrink(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        paths=[root/'enclosure.json',root/'receipt.json']
        for p in paths:p.write_bytes(b'original-unit-evidence')
        source=EnclosureVariant(((frozenset({1,2}),frozenset({3})),)*3,((frozenset({4}),frozenset()),)*3)
        review=SimpleNamespace(enclosure=CentralEnclosure(source,source),fitted_playback=object(),
            original_playback=SimpleNamespace(cache=self.cache),private_enclosure_report=str(paths[0]),
            enclosure_report_sha256=sha256(paths[0].read_bytes()).hexdigest(),
            private_anatomical_verification=str(paths[1]),anatomical_verification_sha256=sha256(paths[1].read_bytes()).hexdigest())
        self.assertEqual(require_enclosure_fit_guard(review).frames_checked,3)
        for key,code,verdict in (('inside','BURIED_SKIN',((frozenset(),frozenset({1})),)*3),
                                 ('ambiguous','UNCERTAINTY',((frozenset(),frozenset({4})),)*3)):
            review.enclosure=CentralEnclosure(source,replace(source,**{key:verdict}))
            with self.assertRaisesRegex(ValidationError,code):require_enclosure_fit_guard(review)
        review.enclosure=CentralEnclosure(source,source)
        for p in paths:
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValidationError,'EVIDENCE_CHANGED'):require_enclosure_fit_guard(review)
            p.write_bytes(b'original-unit-evidence')


if __name__=='__main__':unittest.main()
