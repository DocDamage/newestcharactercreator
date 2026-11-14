"""Mock-worker body-review transactions; invented geometry is unit evidence only."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch

import test_native_playback as source_fixture
from fixtures.body_contact_contract import write_body_contract
from fixtures.motion_skin_contract import file_record
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.jobs.body_contact_review import review_body_contacts,review_body_contact_areas,review_anatomical_safety,review_complete_anatomical_safety
from ucc.jobs.contact_fit_context import ContactFitContext
from ucc.jobs.native_playback import NativePlayback
from ucc.library.provenance import AssetPolicyError
from ucc.preview.motion_cache import read_motion_cache


class BodyReviewCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.f=source_fixture.PlaybackCoordinatorTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;folder=f.store.root/'.ucc-jobs'/str(uuid4());folder.mkdir()
        _d,_r,_v,_b,self.base,self.profile,self.fitted_data,cache_report,arm_verified=write_body_contract(folder,True)
        cache=read_motion_cache(folder,cache_report,cache_report['bindings'],self.base,profile=self.profile,surface_verification=arm_verified)
        self.playback=NativePlayback(f.project.project_id,f.project.revision,f.preview.master_sha256,f.preview.source_sha256,
            cache,folder.name,str(folder/'motion_skin.json'),'unit-only')
        self.bindings={**f.bindings,'review_sha256':f.digest(f.folder/'review_motion.blend'),'timeline_sha256':f.digest(f.folder/'target_timeline.json')}
        staged={'candidate.blend':f.master,'review_motion.blend':f.folder/'review_motion.blend','source_snapshot.json':f.folder/'source_snapshot.json',
            'native_mapping.json':f.folder/'native_mapping.json','target_timeline.json':f.folder/'target_timeline.json','motion_contacts.json':folder/'motion_contacts.json'}
        expected={n:f.digest(p) for n,p in staged.items()}
        self.ctx=ContactFitContext(f.project,self.base,self.profile,self.bindings,staged,expected,self.playback)
        self.paths={}
        for name in ('contact_fit.json','fitted_motion.blend','fitted_timeline.json'):
            p=folder/name;p.write_bytes(b'unit-only-fitted-input');self.paths[name]=p
        self.fit_hashes={n:f.digest(p) for n,p in self.paths.items()}
        self.fit_options={**self.bindings,'fit_sha256':self.fit_hashes['contact_fit.json'],
            'fitted_sha256':self.fit_hashes['fitted_motion.blend'],'fit_report_sha256':self.fit_hashes['fitted_timeline.json']}
        self.fitted_data['bindings']={k:v for k,v in self.fit_options.items() if k!='fit_report_sha256'}
        self.fitted=SimpleNamespace(cache=cache,unit_only=True);self.operations=[];self.fault=None

    def run_review(self,paired=False,stable_areas=False,anatomical=False,complete=False,**overrides):
        if complete:anatomical=True
        f=self.f;captured={}
        def worker(request,**kw):
            self.operations.append(request.operation);out=f.store.root/'.ucc-jobs'/request.job_id;out.mkdir()
            for name,path in kw['staged_inputs'].items():(out/name).write_bytes(path.read_bytes())
            if request.operation.startswith('inspect_'):
                data,report,_receipt,*_=write_body_contract(out,paired)
                data['bindings']=dict(request.options);data['original_review_verification']['bindings']=dict(self.bindings)
                if self.fault=='partial':data['original']['frames'].pop()
                if self.fault=='topology':data['original']['frames'][0]['triangle_sha256']='e'*64
                if stable_areas or anatomical:
                    from fixtures.body_area_contract import wrap_body_areas
                    data=wrap_body_areas(data,self.playback.cache)
                p=out/'body_contacts.json';p.write_text(json.dumps(data));captured['path']=p
                report.update(bindings=dict(request.options),report=file_record(p))
                if anatomical:
                    ep=out/'central_enclosure.json';ep.write_text('{"unit_only":true}',encoding='utf-8')
                    captured['enclosure']=ep;captured['measurement']=report
                    report.update(status='REAL_ANATOMICAL_SAFETY_MEASURED',enclosure_report=file_record(ep))
                if complete:
                    fp=out/'full_trunk_contacts.json';fp.write_text('{"unit_only":true}',encoding='utf-8')
                    captured['full']=fp
                    report.update(status='REAL_COMPLETE_ANATOMICAL_SAFETY_MEASURED',full_trunk_report=file_record(fp))
                    if self.fault=='full_record':report.pop('full_trunk_report')
                if self.fault=='approval':report['contact_quality_verified']=True
                if self.fault=='binding':report['bindings']['source_sha256']='e'*64
                if self.fault=='source':f.source.write_bytes(b'changed')
                if self.fault=='staged':(out/'candidate.blend').write_bytes(b'changed')
                if self.fault=='cancel':f.cancel.set()
                if self.fault=='revision':f.store.save(replace(f.project,revision=f.project.revision+1),expected_revision=f.project.revision)
            else:
                report={'status':'REAL_NATIVE_BODY_CONTACTS_VERIFIED','bindings':dict(request.options),'frames_verified':3,'paired':paired,
                    'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
                if anatomical:
                    report['status']='REAL_ANATOMICAL_SAFETY_VERIFIED'
                    if self.fault=='enclosure_staged':(out/'central_enclosure.json').write_bytes(b'changed')
                    if self.fault=='late_enclosure':captured['enclosure'].write_bytes(b'changed')
                    if self.fault=='enclosure_receipt':report['bindings']['enclosure_review_sha256']='0'*64
                if complete:
                    report['status']='REAL_COMPLETE_ANATOMICAL_SAFETY_VERIFIED'
                    if self.fault=='full_staged':(out/'full_trunk_contacts.json').write_bytes(b'changed')
                    if self.fault=='late_full':captured['full'].write_bytes(b'changed')
                    if self.fault=='full_receipt':report['bindings'].pop('full_trunk_review_sha256')
                if self.fault=='receipt':report['frames_verified']=2
                if self.fault=='verify_staged':(out/'source_snapshot.json').write_bytes(b'changed')
                if self.fault=='late_report':captured['path'].write_bytes(b'changed')
            (out/'result.json').write_text(json.dumps({'details':report}),encoding='utf-8')
            return SimpleNamespace(details=report),out
        args={'source_fbx':f.source,'permission':f.policy,'blender_exe':Path('unit.blender'),'worker_script':Path('unit.py'),'cancel':f.cancel}
        args.update(overrides)
        def enclosure_parser(folder,measured,verified,bindings,baseline,profile,cache,areas,**kwargs):
            from ucc.preview.central_enclosure import CentralEnclosure,EnclosureVariant,validate_anatomical_receipt
            validate_anatomical_receipt(verified,bindings,baseline,paired,measured)
            variant=EnclosureVariant(((frozenset(),frozenset()),)*3,((frozenset(),frozenset()),)*3)
            return CentralEnclosure(variant,variant if paired else None)
        def complete_parser(folder,measured,verified,bindings,baseline,profile,cache,**kwargs):
            from ucc.jobs.complete_anatomical_evidence import validate_complete_receipt,CompleteAnatomicalEvidence
            from ucc.jobs.native_fit_evidence import read_json_record
            from ucc.preview.contact_areas import parse_body_contact_areas
            from ucc.preview.central_surface import CompleteSurfaceVariant,CompleteTrunkSurfaces,POLICY
            from ucc.preview.central_enclosure import CentralEnclosure,EnclosureVariant
            from ucc.preview.surface_review import SurfaceReview
            validate_complete_receipt(verified,measured,bindings,baseline,paired)
            read_json_record(folder,measured['full_trunk_report'],'full_trunk_contacts.json',64*1024*1024)
            raw,_=read_json_record(folder,measured['report'],'body_contacts.json',40*1024*1024)
            areas=parse_body_contact_areas(raw,bindings,baseline,profile,cache,**kwargs)
            empty=((frozenset(),frozenset()),)*3
            variant=EnclosureVariant(empty,empty)
            surface=SurfaceReview('CHECKED','',((),)*3,((0,0),)*3,('a'*64,)*3,POLICY)
            full=CompleteSurfaceVariant(surface,empty,empty)
            return CompleteAnatomicalEvidence(areas,CentralEnclosure(variant,variant if paired else None),
                CompleteTrunkSurfaces(full,full if paired else None,() if paired else None,() if paired else None))
        with (patch('ucc.preview.central_enclosure.read_central_enclosure',side_effect=enclosure_parser),
              patch('ucc.jobs.complete_anatomical_evidence.read_complete_anatomy',side_effect=complete_parser),
              patch('ucc.jobs.body_contact_review.contact_context',return_value=self.ctx) as context,
              patch('ucc.jobs.body_contact_review.fitted_body_context',return_value=(self.fit_options,self.paths,self.fit_hashes,self.fitted_data,self.fitted)),
              patch('ucc.jobs.body_contact_review.BlenderJobRunner.run',side_effect=worker)):
            result=(review_complete_anatomical_safety if complete else review_anatomical_safety if anatomical else review_body_contact_areas if stable_areas else review_body_contacts)(f.store,f.preview,self.playback,fitted=self.fitted if paired else None,**args)
            self.assertFalse(context.call_args.kwargs['require_crossings'])
            return result

    def test_original_and_paired_need_two_distinct_jobs_before_annotations_are_returned(self):
        result=self.run_review();self.assertEqual(self.operations,['inspect_native_body_contacts','verify_native_body_contacts'])
        self.assertEqual(len(set(result.worker_job_ids)),2);self.assertIsNone(result.contacts.fitted)
        self.assertEqual(result.metadata_sha256,self.f.digest(self.f.store.root/'project.ucc.json'))
        self.assertEqual(dict(result.bindings),self.bindings)
        self.operations=[];paired=self.run_review(True)
        self.assertEqual(self.operations,['inspect_fitted_body_contacts','verify_fitted_body_contacts'])
        self.assertEqual(paired.contacts.more_pair_frames,(2,));self.assertEqual(self.f.store.load(),self.f.project)

    def test_complete_review_binds_three_reports_and_retains_separate_legacy_scope(self):
        for paired in (False,True):
            self.operations=[];result=self.run_review(paired,complete=True)
            kind='fitted' if paired else 'native'
            self.assertEqual(self.operations,['inspect_'+kind+'_complete_anatomical_safety','verify_'+kind+'_complete_anatomical_safety'])
            self.assertEqual(result.full_trunk_report_sha256,self.f.digest(Path(result.private_full_trunk_report)))
            self.assertEqual(result.anatomical_verification_sha256,self.f.digest(Path(result.private_anatomical_verification)))
            self.assertEqual(result.contacts,result.areas.contacts)
            self.assertIsNotNone(result.full_trunk)
            self.assertEqual(result.full_trunk.fitted is not None,paired)

    def test_complete_report_or_receipt_mutation_cancellation_or_revision_never_returns_a_result(self):
        for fault in ('full_record','full_staged','late_full','full_receipt','receipt','approval','cancel','revision','verify_staged'):
            case=BodyReviewCoordinatorTests();case.setUp()
            try:
                case.fault=fault
                with self.subTest(fault=fault),self.assertRaises((ValidationError,ProjectConflict,ProjectStorageError)):
                    case.run_review(complete=True)
            finally:case.doCleanups()

    def test_combined_review_binds_both_reports_and_fresh_receipt_without_legacy_statuses(self):
        result=self.run_review(anatomical=True)
        self.assertEqual(self.operations,['inspect_native_anatomical_safety','verify_native_anatomical_safety'])
        self.assertIsNotNone(result.enclosure);self.assertIsNone(result.enclosure.fitted)
        self.assertTrue(Path(result.private_enclosure_report).is_file())
        self.assertTrue(Path(result.private_anatomical_verification).is_file())
        self.assertEqual(result.enclosure_report_sha256,self.f.digest(Path(result.private_enclosure_report)))
        self.assertEqual(result.anatomical_verification_sha256,self.f.digest(Path(result.private_anatomical_verification)))

    def test_combined_receipt_provenance_and_enclosure_edits_cannot_publish(self):
        for fault in ('enclosure_staged','late_enclosure','enclosure_receipt','receipt','partial','approval','cancel','revision'):
            case=BodyReviewCoordinatorTests();case.setUp()
            try:
                case.fault=fault
                with self.subTest(fault=fault),self.assertRaises((ValidationError,ProjectConflict,ProjectStorageError)):
                    case.run_review(anatomical=True)
            finally:case.doCleanups()

    def test_denied_license_precedes_context_or_worker(self):
        with self.assertRaises(AssetPolicyError):self.run_review(permission=replace(self.f.policy,reviewed=False))
        self.assertFalse(self.operations)

    def test_stable_face_transactions_use_distinct_closed_operations_before_areas_are_returned(self):
        original=self.run_review(stable_areas=True)
        self.assertEqual(self.operations,['inspect_native_body_areas','verify_native_body_areas'])
        self.assertIsNone(original.areas.fitted);self.operations=[]
        paired=self.run_review(True,stable_areas=True)
        self.assertEqual(self.operations,['inspect_fitted_body_areas','verify_fitted_body_areas'])
        self.assertEqual(paired.areas.new_area_frames,(2,));self.assertIs(paired.contacts,paired.areas.contacts)

    def test_stable_face_faults_never_return_partial_or_stale_comparisons(self):
        for fault in ('source','staged','partial','late_report','receipt'):
            case=BodyReviewCoordinatorTests();case.setUp()
            try:
                case.fault=fault
                with self.subTest(fault=fault),self.assertRaises((ValidationError,ProjectConflict,ProjectStorageError)):
                    case.run_review(True,stable_areas=True)
            finally:case.doCleanups()

    def test_faults_never_publish_partial_or_fabricated_annotations(self):
        for fault in ('source','staged','cancel','revision','approval','binding','partial','topology','receipt','verify_staged','late_report'):
            with self.subTest(fault=fault):
                case=BodyReviewCoordinatorTests();case.setUp()
                try:
                    case.fault=fault
                    with self.assertRaises((ValidationError,ProjectConflict,ProjectStorageError)):case.run_review()
                    if fault in ('source','staged','cancel','revision','approval','binding'):self.assertEqual(len(case.operations),1)
                finally:case.doCleanups()


if __name__=='__main__':unittest.main()
