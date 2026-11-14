"""Fitted intake identity/path gates; invented bytes are not Blender evidence."""
from dataclasses import dataclass,replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch

import test_fitted_cache as cache_fixture
from ucc.core.errors import ValidationError,ProjectConflict
from ucc.jobs.body_contact_context import fitted_body_context
from ucc.jobs.protocol import JobResult


@dataclass(frozen=True)
class UnitFitted:
    project_id: str
    revision: int
    master_sha256: str
    source_sha256: str
    original_preview: object
    fitted_preview: object
    fit_policy_sha256: str
    fitted_scene_sha256: str
    private_manifest: str
    job_id: str
    cache: object=None


class BodyContactContextTests(unittest.TestCase):
    def setUp(self):
        self.f=cache_fixture.FittedCacheTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;self.store=SimpleNamespace(root=f.root);jobs=f.root/'.ucc-jobs';jobs.mkdir()
        self.folder=jobs/str(uuid4());self.folder.mkdir();self.cache=jobs/str(uuid4());self.cache.mkdir()
        self.paths={}
        for name in ('contact_fit.json','fitted_motion.blend'):
            p=self.folder/name;p.write_bytes(b'unit-only '+name.encode());self.paths[name]=p
        digest=lambda p:sha256(p.read_bytes()).hexdigest()
        f.bindings.update(fit_sha256=digest(self.paths['contact_fit.json']),fitted_sha256=digest(self.paths['fitted_motion.blend']))
        canonical=self.folder/'fitted_timeline.json';canonical.write_text(json.dumps(f.fitted));self.paths[canonical.name]=canonical
        f.bindings['fit_report_sha256']=digest(canonical);f.data['bindings']=dict(f.bindings);f.report['bindings']=dict(f.bindings);f.rewrite()
        for name in ('fitted_skin.json','fitted_skin.bin'):(self.cache/name).write_bytes((f.root/name).read_bytes())
        receipt=JobResult(self.cache.name,'cache_native_fit','ok',f.report).as_dict()
        (self.cache/'result.json').write_text(json.dumps(receipt))
        self.preview=object();self.identity={'project_id':'unit','revision':1,'master_sha256':f.bindings['master_sha256'],'source_sha256':f.bindings['source_sha256']}
        fp=SimpleNamespace(verification={'bindings':dict(f.bindings)},fit_policy_used=str(self.paths['contact_fit.json']),
            private_fitted_scene=str(self.paths['fitted_motion.blend']),private_timeline=str(canonical),evidence={'target_rest_frames':{}})
        self.fitted=UnitFitted(**self.identity,original_preview=self.preview,fitted_preview=fp,
            fit_policy_sha256=f.bindings['fit_sha256'],fitted_scene_sha256=f.bindings['fitted_sha256'],
            private_manifest=str(self.cache/'fitted_skin.json'),job_id=self.cache.name)
        self.ctx=SimpleNamespace(playback=SimpleNamespace(**self.identity),bindings={k:v for k,v in f.bindings.items()
            if k not in ('fit_sha256','fitted_sha256','fit_report_sha256')},baseline=f.base,profile={})

    def load(self):
        # Semantic fitted-Action and PNG verification have their own contracts;
        # this fixture isolates new filesystem/receipt/full-cache intake gates.
        with (patch('ucc.jobs.body_contact_context.validate_fitted_data',return_value=(None,self.f.surface,None)),
              patch('ucc.jobs.body_contact_context.validate_fit_verification')):
            return fitted_body_context(self.store,self.ctx,self.preview,self.fitted)

    def test_current_private_fitted_cache_is_fully_decoded_not_trusted_from_memory(self):
        options,paths,hashes,data,fitted=self.load()
        self.assertEqual(fitted.cache.frame_count,3);self.assertIsNone(self.fitted.cache)
        self.assertEqual(options,self.f.bindings);self.assertEqual(data,self.f.fitted)
        self.assertEqual(set(paths),set(hashes));self.assertNotEqual(fitted.cache.frame(0),fitted.cache.frame(2))

    def test_stale_selection_hashes_paths_receipts_and_geometry_reject(self):
        for fault in ('selection','revision','binding','scene','policy','canonical','outside','manifest','receipt','geometry'):
            case=BodyContactContextTests();case.setUp()
            try:
                fp=case.fitted.fitted_preview
                if fault=='selection':case.fitted=replace(case.fitted,original_preview=object())
                if fault=='revision':case.fitted=replace(case.fitted,revision=2)
                if fault=='binding':fp.verification['bindings']['source_sha256']='e'*64
                if fault in ('scene','policy','canonical'):
                    key={'scene':'fitted_motion.blend','policy':'contact_fit.json','canonical':'fitted_timeline.json'}[fault]
                    case.paths[key].write_bytes(b'changed')
                if fault=='outside':fp.private_fitted_scene=str(case.f.root/'outside.blend')
                if fault=='manifest':case.fitted=replace(case.fitted,private_manifest=str(case.cache/'wrong.json'))
                if fault=='receipt':
                    p=case.cache/'result.json';d=json.loads(p.read_text());d['operation']='inspect_fbx_skeleton';p.write_text(json.dumps(d))
                if fault=='geometry':(case.cache/'fitted_skin.bin').write_bytes(b'changed')
                with self.subTest(fault=fault),self.assertRaises((ValidationError,ProjectConflict)):case.load()
            finally:case.doCleanups()


if __name__=='__main__':unittest.main()
