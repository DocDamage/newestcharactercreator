"""NONSHIPPING loader fixture; current/native admissions explicitly stubbed."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace
from uuid import UUID
from fixtures.godot_registered_retention_logic import RetentionFixture,digest
from fixtures.godot_registered_body_draw_logic import png
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_runtime_contract import NativeRuntimeRequest
from ucc.export.godot_registered_runtime_contract import RegisteredRuntimeManifest
from ucc.export.godot_saved_preview import SelectedProofFile,CapturedPreviewFrame
from ucc.jobs.godot_registered_runtime_admission import preparation_paths,proof_references
from ucc.jobs.godot_registered_runtime_storage import _metadata_records
from ucc.jobs.godot_candidate_inputs import identity
from ucc.jobs.private_render_evidence import png_measurements
from ucc.jobs.target_action_context import Budget
from ucc.library.provenance import AssetPolicyError


class SavedPreviewFixture(RetentionFixture):
    def __init__(self,root):
        super().__init__(root)
        self.database=self.root/'SYNTHETIC_POLICY.sqlite'
        with closing(sqlite3.connect(self.database)) as db:db.execute('CREATE TABLE synthetic_policy(allowed INTEGER)');db.execute('INSERT INTO synthetic_policy VALUES(1)');db.commit()
        old_guard=self.context.guard
        def guard():
            old_guard()
            with closing(sqlite3.connect(self.database.as_uri()+'?mode=ro',uri=True)) as db:
                if db.execute('SELECT allowed FROM synthetic_policy').fetchone()[0]!=1:
                    raise AssetPolicyError('NONSHIPPING current policy revoked')
        self.context.guard=guard
        self.context.prepared_target.watched_inputs=((self.store.file,digest(self.store.file)),)
        self.context.prepared_target.watched_identities=((self.store.file,identity(self.store.file)),(self.store.root,identity(self.store.root)))
        request=NativeRuntimeRequest.from_bytes((self.work/'runtime_request.json').read_bytes())
        paths=preparation_paths(self.store,self.preparation)
        records=_metadata_records(paths,request,Budget(None,60))
        self.manifest=RegisteredRuntimeManifest(str(UUID(int=9000)),self.selection,self.receipt_sha,
            self.preparation.recipe_sha256,request.sha256,self.stage.name,self.fresh.name,records,
            proof_references(self.binding),self.permissions)
        self.retained=self.root/'EXTERNAL_RELOCATED_CANDIDATE';self.retained.mkdir()
        for row in records:
            if row.name=='.gdignore':(self.retained/row.name).write_bytes(b'')
            else:shutil.copyfile(paths[row.name],self.retained/row.name)
        (self.retained/'manifest.json').write_bytes(canonical_bytes(self.manifest.to_dict()))
        self.c=self.root/'EXTERNAL_RELOCATED_C_PROOF';self.c.mkdir();(self.c/'diagnostic_receipt.json').write_bytes(b'{"synthetic":"C_native_admission_is_stubbed"}')
        self.d=self.root/'EXTERNAL_RELOCATED_D_PROOF';self.d.mkdir();(self.d/'diagnostic_draw_receipt.json').write_bytes(b'{"synthetic":"D_native_admission_is_stubbed"}')
        self.png_raw=png();self.image=self.d/'SYNTHETIC_CAPTURE.png';self.image.write_bytes(self.png_raw)
        self.seen_reads=None;self.context_calls=0

    def current(self,*args,**kwargs):
        self.context_calls+=1;self.context.guard();return self.context

    def body(self,reads,selected,*args):
        self.seen_reads=reads;reads.metadata(selected.path,4096,selected.sha256)
        return SimpleNamespace(directory=self.c)

    def draw(self,reads,selected,*args):
        reads.metadata(selected.path,4096,selected.sha256)
        raw=reads.capture(self.image,2*1024*1024,sha256(self.png_raw).hexdigest())
        stats=png_measurements(raw,include_pixel_hash=True,expected_size=(512,512))
        return str(UUID(int=10000)),tuple(CapturedPreviewFrame(frame,raw,stats['rgba_sha256'],stats['opaque_pixels'],tuple(stats['opaque_bounds']),0.) for frame in (1,150,300))

    def args(self):
        return dict(selection=self.selection,draw_receipt=SelectedProofFile(self.d/'diagnostic_draw_receipt.json',digest(self.d/'diagnostic_draw_receipt.json')),
            body_receipt=SelectedProofFile(self.c/'diagnostic_receipt.json',digest(self.c/'diagnostic_receipt.json')),
            retained_manifest=SelectedProofFile(self.retained/'manifest.json',self.manifest.sha256),database_path=self.database,
            permissions=self.permissions,local_view_confirmed=True)
