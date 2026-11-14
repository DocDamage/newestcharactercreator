"""Non-shipping synthetic DB/header fixtures; never actual Blender evidence."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from fixtures.fbx_snapshot_contract import snapshot, report
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.catalog_clip import VerifiedCatalogClip
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.catalog_clip import _saved_reference
from ucc.jobs.neutral_master import NeutralMasterInspection
from ucc.library.provenance import LicensePolicy


class ReferenceFixture:
    def __init__(self, root: Path):
        self.root = root; self.database = root/'catalog.sqlite3'
        self.source = root/'source.fbx'; self.source.write_bytes(b'SYNTHETIC_NOT_ACTUAL_FBX')
        self.source_sha = sha256(self.source.read_bytes()).hexdigest(); self.clip_id = 'fixture-source#clip-0000'
        self.policy = LicensePolicy('Original', 'CC0', 'local-original://unit', reviewed=True, local_preview_allowed=True, no_ai=True)
        data = snapshot(); data['source_sha256'] = self.source_sha
        measured = {**report(data, json.dumps(data).encode()), 'two_workers_agree': True,
                    'source_bytes_unchanged': True, 'policy': self.policy.to_dict()}
        with AnimationCatalog(self.database) as c:
            c.index_file('fixture-source', self.source, self.policy)
            c.record_fbx_intake('fixture-source', data, measured, expected_entry=c.library.get('fixture-source'))
        entry, indexed, receipt, receipt_sha = _saved_reference(self.database, self.clip_id, self.source_sha, self.policy)
        self.reference = VerifiedCatalogClip(self.clip_id, entry.asset_id, entry.sha256, entry.policy,
            receipt['snapshot_sha256'], receipt_sha, receipt['skeleton_fingerprint'], 1, 4, indexed.clips[0])
        self.store = ProjectStore(root/'character')
        self.master_bytes = b'BLENDER'+b'SYNTHETIC_HEADER_ONLY_NOT_BLENDER'*70
        self.master_sha = sha256(self.master_bytes).hexdigest()
        self.relative = 'master/versions/'+self.master_sha+'.blend'; self.master = self.store.root/self.relative
        self.master.parent.mkdir(parents=True); self.master.write_bytes(self.master_bytes)
        self.project = self.store.save(replace(CharacterProject.new('Reference unit fixture'),
            master_blend=self.relative, geometry_state='generated_unverified'))
        self.executable = root/'not-executed.exe'; self.executable.write_bytes(b'UNIT_ONLY')
        self.script = root/'not-executed.py'; self.script.write_bytes(b'# UNIT_ONLY')

    def kwargs(self):
        project = self.store.load()
        return dict(blender_exe=self.executable, worker_script=self.script, expected_project_id=project.project_id,
                    expected_revision=project.revision, expected_master_blend=project.master_blend)

    def neutral(self, store, **kwargs):
        project = store.load()
        return NeutralMasterInspection(project.project_id, project.revision,
            sha256(store.file.read_bytes()).hexdigest(), self.master_sha,
            {'state_sha256': 'c'*64, 'source_provenance_verified': False,
             'project_action_admission_verified': False, 'engine_import_verified': False}, ('unit-one', 'unit-two'))
