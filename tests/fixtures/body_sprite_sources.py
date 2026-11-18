"""NONSHIPPING records; retained native admission and source workers are doubles."""
from dataclasses import replace
import json
from pathlib import Path
import shutil

from fixtures.target_action_logic import TargetFixture, clock_snapshot
from fixtures.fbx_snapshot_contract import report
from ucc.core.body_sprites import BodySpriteRequest, BodySpriteWindow, body_sprite_sources
from ucc.core.expressions import ExpressionState
from ucc.core.sprite_render import SpritePermission, SpriteSettings
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.target_action import TargetActionFile
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.target_action_context import source_review, operation_budget
from ucc.jobs.protocol import JobRequest, JobResult
from ucc.jobs.master_preview import _digest
from ucc.jobs.body_sprite_provenance import OriginalMotionProvenance


class BodySourceFixture:
    def __init__(self, root):
        self.f = TargetFixture(root); self.store = self.f.store
        self.expression = root/'UNIT_NOT_REAL_EXPRESSION_MANIFEST'; self.expression.write_bytes(b'UNIT_ONLY_PROVENANCE_BOUNDARY')
        before = self.store.load()
        self.project = self.store.save(replace(before, schema_version=3,
            expression=ExpressionState(_digest(self.expression)), revision=before.revision+1), expected_revision=before.revision)
        self.f.project = self.project
        with operation_budget(None,30) as budget:
            self.f.review = source_review(self.store,self.f.database,self.f.clip_id,self.project.project_id,
                self.project.revision,self.project.master_blend,_digest(self.store.file),budget)
        directory, binding = self.f.payload()
        self.data = clock_snapshot(); self.data['source_sha256'] = self.f.source_sha
        self.payload = json.dumps(self.data).encode()
        (directory/'source_snapshot.json').write_bytes(self.payload)
        for role in ('first','second'):
            (directory/'neutral'/f'{role}_result.json').write_text(json.dumps({'details':{'expression_key_count':12}}))
        files = tuple(TargetActionFile(name,_digest(directory/name),(directory/name).stat().st_size) for name in sorted(binding.file_map))
        binding = replace(binding, mapping_sha256=_digest(directory/'native_mapping.json'), files=files,
                          producer=replace(binding.producer,blender_executable_sha256=_digest(self.f.executable)))
        (directory/'binding.json').write_bytes(canonical_bytes(binding.to_dict()))
        self.directory = directory.with_name(binding.sha256); directory.rename(self.directory); self.binding = binding
        self.paths = {'master':self.store.root/self.project.master_blend,'expression_library':self.expression}
        permissions = tuple(SpritePermission(name,digest,'UNIT_ONLY_PRIVATE_SPRITE_AUTHORIZATION',True,True)
                            for name,digest in body_sprite_sources(self.project,binding))
        from uuid import uuid4
        self.request = BodySpriteRequest(str(uuid4()),canonical_bytes(self.project.to_dict()),binding,
            BodySpriteWindow(1,2),SpriteSettings(128,4),SkinMaterialSpec((.56,.60,.67),1.),permissions,
            'NONSHIPPING body-sprite source boundary only',True)
        from ucc.export.godot_native_recipe import build_native_recipe
        from ucc.export.godot_candidate_contract import EngineInputPermission
        from ucc.export.godot_runtime_contract import CODE_FILES,CAPABILITY
        # A historical declaration fixture, not a rewritten rendering project.
        historical = replace(self.project,animations=())
        source_bindings = {'master':binding.target.master_sha256,'expression_library':self.project.expression.library_sha256,
                           'motion:unit-original':self.f.source_sha}
        author_policy = replace(self.f.policy,can_use_non_unreal=True,source_uri='ucc-original-diagnostic://unit/original')
        author_permissions = tuple(EngineInputPermission(name,digest,author_policy,False) for name,digest in source_bindings.items())
        record = build_native_recipe(historical,binding.target.project_sha256,source_bindings,
            {name:binding.source.snapshot_sha256 if name=='source_snapshot' else 'e'*64
             for name in ('source_snapshot','native_review','native_timeline','native_mapping')},
            {name:'c'*64 for name in CODE_FILES},author_permissions,'motion:unit-original',CAPABILITY)
        self.author_record = root/'UNIT_ORIGINAL_AUTHOR_RECORD.json'; self.author_record.write_bytes(canonical_bytes(record))
        self.provenance = OriginalMotionProvenance(self.author_record,_digest(self.author_record),'motion:unit-original',
            ((author_policy.source_uri,self.f.policy.source_uri),))
        self.calls = []; self.fault = None; self.after_first = None

    def intake(self, source, **kwargs):
        first = None; details = None
        for index in range(2):
            kwargs['source_guard']()
            job = JobRequest.new('inspect_fbx_animation',options={'source_sha256':self.f.source_sha})
            folder = kwargs['jobs_root']/job.job_id; folder.mkdir(parents=True)
            data = json.loads(self.payload)
            if self.fault == 'coherent_snapshot': data['action'] = 'UNIT_DIFFERENT_COMPLETE_TRAJECTORY'
            payload = json.dumps(data).encode(); details = report(data,payload)|{'first_frame':2,'last_frame':301}
            path = folder/'source_snapshot.json'; path.write_bytes(payload)
            shutil.copyfile(source,folder/'source.fbx')
            result = JobResult(job.job_id,job.operation,'ok',details)
            (folder/'request.json').write_text(json.dumps(job.as_dict()))
            (folder/'result.json').write_text(json.dumps(result.as_dict()))
            kwargs['observer'](job,result,folder); self.calls.append(job)
            if first is None: first = path
            if index == 0 and self.after_first: self.after_first()
        return details|{'private_snapshot':str(first),'source_path':str(source),'policy':kwargs['permission'].to_dict(),
                        'two_workers_agree':True,'source_bytes_unchanged':True}
