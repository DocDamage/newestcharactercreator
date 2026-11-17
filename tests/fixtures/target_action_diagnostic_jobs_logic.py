"""NONSHIPPING job fixture: existing native/typed admission explicitly doubled."""
from hashlib import sha256
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
from types import SimpleNamespace

from ucc.animations.target_action_diagnostic import TargetActionDiagnosticSelection
from ucc.core.target_action_format import RETAINED_FILES
from ucc.jobs.godot_candidate_inputs import identity
from ucc.jobs.target_action_storage import ancestry
from ucc.library.provenance import AssetPolicyError


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class DiagnosticJobsFixture:
    def __init__(self, root: Path):
        self.root = root
        self.store = SimpleNamespace(root=root/'p')
        self.store.root.mkdir()
        catalog = root/'catalog'/'nested'; catalog.mkdir(parents=True)
        self.database = catalog/'synthetic.sqlite'
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE policy(allowed INTEGER)')
            db.execute('INSERT INTO policy VALUES(1)')
            db.commit()
        self.binding_raw = b'{"NONSHIPPING":"typed native admission is stubbed"}'
        selected = sha256(self.binding_raw).hexdigest()
        self.selection = TargetActionDiagnosticSelection('synthetic-project', 1,
            '1'*64, '2'*64, 'synthetic-original#clip-0000', selected, '3'*64, '4'*64)
        self.directory = self.store.root/'animations/actions'/selected
        self.directory.mkdir(parents=True)
        self.binding_path = self.directory/'binding.json'
        self.binding_path.write_bytes(self.binding_raw)
        self.timeline = self.directory/'body_first/target_timeline.json'
        self.timeline.parent.mkdir()
        matrix = [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]
        self.data = dict(root_motion_policy='SOURCE_HIP_MIDPOINT_V1',
            source_first_frame=2, source_frame_count=300, fps=30,
            mapped_pairs=[{'target':'synthetic-root'}], full_timeline_frames=[
                dict(frame=i+1, source_frame=i+2, root_world_head=[i/30,0.,0.],
                    hip_midpoint_world=[i/30,0.,1.], target_global_poses=[matrix])
                for i in range(300)])
        self.source = self.store.root/'synthetic-source'; self.source.write_bytes(b'original')
        self.cache_path = self.directory/'playback/motion_skin.bin'
        self.cache_path.parent.mkdir(); self.cache_path.write_bytes(b'SYNTHETIC_STUB_CACHE')
        vertices = struct.pack('<fff', 0., 0., 0.)
        self.cache = SimpleNamespace(frame_count=300, fps=30., world_matrix=tuple(matrix),
            hips=tuple((i/30,0.,1.) for i in range(300)), frame=lambda index:(vertices,b''),
            source_first_frame=2, packed=self.cache_path.read_bytes())
        self.refresh()

    def refresh(self):
        self.timeline.write_text(json.dumps(self.data), encoding='utf-8')
        paths = (self.source, self.binding_path, self.timeline, self.cache_path)
        files = {name:SimpleNamespace(sha256='a'*64, bytes=1) for name in RETAINED_FILES}
        files['body_first/target_timeline.json'] = SimpleNamespace(
            sha256=digest(self.timeline), bytes=self.timeline.stat().st_size)
        files['playback/motion_skin.bin'] = SimpleNamespace(
            sha256=digest(self.cache_path), bytes=self.cache_path.stat().st_size)
        self.binding = SimpleNamespace(sha256=self.selection.binding_sha256,
            root_motion_policy='SOURCE_HIP_MIDPOINT_V1', file_map=files, source=object())
        stamps = ancestry((*paths, self.database))
        stamps[self.database] = (*identity(self.database)[:2], 0, 0)
        stamps[self.database.parent] = identity(self.database.parent)
        self.prepared = SimpleNamespace(directory=self.directory, binding_path=self.binding_path,
            cache=self.cache, watched_inputs=tuple((p,digest(p)) for p in paths),
            watched_identities=tuple(stamps.items()))

    def logical(self, *args, **kwargs):
        with closing(sqlite3.connect(self.database.as_uri()+'?mode=ro', uri=True)) as db:
            if db.execute('SELECT allowed FROM policy').fetchone()[0] != 1:
                raise AssetPolicyError('NONSHIPPING local-preview policy revoked')

    def args(self):
        return dict(selection=self.selection, database_path=self.database,
                    local_preview_confirmed=True)
