"""NONSHIPPING source/storage fixture; native Action/cache admission is stubbed."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from fixtures.fbx_snapshot_contract import snapshot, report
from fixtures.project_reference_contract import ReferenceFixture
from fixtures.target_action_contract import metadata_pair
from ucc.core.target_action import TargetActionBinding, TargetActionFile, TargetActionTarget
from ucc.core.target_action_format import RETAINED_FILES, canonical_bytes
from ucc.core.target_action_request import TargetActionRequest
from ucc.jobs.animation_reference_storage import publish_source_binding
from ucc.jobs.master_preview import _digest
from ucc.jobs.target_action_context import review_target_action_source
from ucc.jobs.target_action_storage import action_root


def clock_snapshot():
    data = snapshot(); originals = data['frames']
    data.update(first_frame=2, last_frame=301, fps=30.)
    data['frames'] = [{**deepcopy(originals[i % len(originals)]), 'frame':i+2} for i in range(300)]
    return data


class TargetFixture(ReferenceFixture):
    def __init__(self, root):
        def measured(data, payload):
            return report(data, payload)|{'first_frame':2, 'last_frame':301}
        with (patch('fixtures.project_reference_contract.snapshot', side_effect=clock_snapshot),
              patch('fixtures.project_reference_contract.report', side_effect=measured)):
            super().__init__(Path(root).resolve())
        script_bytes=self.script.read_bytes();self.script.unlink()
        self.script=self.root/'worker/blender_bridge/entrypoint.py'
        self.script.parent.mkdir(parents=True);self.script.write_bytes(script_bytes)
        self.reference = replace(self.reference, first_frame=2, last_frame=301)
        publish_source_binding(self.store, self.project.project_id, self.reference)
        self.project = self.store.save(replace(self.project, animations=(self.clip_id,), revision=self.project.revision+1),
            expected_revision=self.project.revision)
        self.review = review_target_action_source(self.store, database_path=self.database,
            clip_id=self.clip_id, **self.context())
        for folder, names in (
            ('5.3/scripts/addons_core/io_scene_fbx',('__init__.py','import_fbx.py','export_fbx_bin.py','fbx_utils.py','parse_fbx.py')),
            ('5.3/scripts/modules/bpy_extras',('__init__.py','anim_utils.py','io_utils.py','node_shader_utils.py','image_utils.py'))):
            directory = self.executable.parent/folder; directory.mkdir(parents=True)
            for name in names: (directory/name).write_text('# NONSHIPPING installed-layout marker only\n')
        (self.executable.parent/'5.3/scripts/modules/rna_prop_ui.py').write_text('# NONSHIPPING installed-layout marker only\n')

    def context(self):
        return {'expected_project_id':self.project.project_id, 'expected_revision':self.project.revision,
            'expected_master_blend':self.project.master_blend, 'expected_project_sha256':_digest(self.store.file)}

    def load_args(self):
        return {**self.context(), 'database_path':self.database, 'expected_clip_id':self.clip_id,
            'expected_source_binding_sha256':self.review.source.source_binding_sha256,
            'expected_catalog_record_sha256':self.review.source.catalog_record_sha256}

    def payload(self):
        _, prototype = metadata_pair()
        request = TargetActionRequest(prototype.producer.body_reopen_job_id, self.project.project_id,
            self.project.revision, _digest(self.store.file), self.master_sha, self.review.source,
            prototype.mapping_sha256, prototype.root_motion_policy, prototype.producer.blender_executable_sha256,
            prototype.producer.worker_resources_sha256, 'NONSHIPPING storage boundary test only', True)
        staged = self.root/'retained-markers'; staged.mkdir()
        for name in RETAINED_FILES:
            path = staged/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('NONSHIPPING_NOT_NATIVE_EVIDENCE:'+name).encode())
        (staged/'preparation_request.json').write_bytes(canonical_bytes(request.to_dict()))
        for role in ('first', 'second'):
            (staged/'neutral'/f'{role}_result.json').write_text(json.dumps({'details':{'expression_key_count':0}}))
        binding = TargetActionBinding(request.sha256, self.review.source,
            TargetActionTarget(self.project.project_id, self.project.revision, _digest(self.store.file),
                self.master_sha, '7'*64, '8'*64), prototype.mapping_sha256, prototype.root_motion_policy,
            prototype.producer, tuple(TargetActionFile(name, _digest(staged/name), (staged/name).stat().st_size)
                for name in sorted(RETAINED_FILES)))
        (staged/'binding.json').write_bytes(canonical_bytes(binding.to_dict()))
        destination = action_root(self.store, create=True)/binding.sha256
        staged.rename(destination)
        return destination, binding
