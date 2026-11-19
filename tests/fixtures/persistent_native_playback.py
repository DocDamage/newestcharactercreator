"""Small non-shipping file fixtures for retained-preview proof tests."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from ucc.animations.source_clip_clock import SourceClipClock
from ucc.preview.motion_cache import MAGIC


def retained_preview_fixture(root: Path):
    job = str(uuid4())
    folder = root / '.ucc-jobs' / job
    folder.mkdir(parents=True)
    master = root / 'saved.blend'
    project = root / 'project.ucc.json'
    source = root / 'source.fbx'
    geometry = folder / 'motion_skin.bin'
    manifest = folder / 'motion_skin.json'
    packed = MAGIC + b'one' + b'two'
    bodies = {project: b'metadata', master: b'saved master', source: b'source motion',
              manifest: b'cache metadata', geometry: packed}
    for path, value in bodies.items():
        path.write_bytes(value)
    hashes = {path: sha256(raw).hexdigest() for path, raw in bodies.items()}
    metadata = dict(chunks=[[8, 3], [11, 3]], hips=[[0., 0., 0.], [0., 0., 0.]],
                    world_matrix=[1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.],
                    fps=30., vertex_count=150, triangle_count=160, radius=.5,
                    source_first_frame=7, surface_review=None)
    authority = SimpleNamespace(clock=SourceClipClock(7, 8, 2, 30.), source_path=source,
                                source_sha256=hashes[source], guard=lambda **options: True)
    return job, master, project, geometry, hashes, metadata, authority
