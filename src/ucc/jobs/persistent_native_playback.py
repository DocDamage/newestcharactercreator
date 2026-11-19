"""Reopen previously verified local playback with fresh catalog and file guards."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from threading import Event
from uuid import UUID

from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.preview.motion_cache import MAGIC, MAX_BYTES, MotionCache
from ucc.preview.surface_review import SurfaceReview
from .master_preview import _digest, _master_file
from .native_playback import NativePlayback
from .native_preview_profiles import find_catalog_preview_profile
from .native_source_authority import NativeProofCapture, NativeProofReceipt, NativeSourceAuthority
from .persistent_preview_index import read_index, write_index
from .source_skeleton_files import capture, watch_identity
from .target_action_context import operation_budget, protected


_VERSION = 1
_HASH_BATCH_LIMIT = 2 * 1024**2


def _hash_file(path: Path, cancel: Event | None, limit: int) -> str:
    before = watch_identity(path)
    if not path.is_file() or not 0 < before[2] <= limit:
        raise ValidationError('Playback input is missing or outside its size limit')
    digest = _digest(path, cancel)
    if watch_identity(path) != before:
        raise ValidationError('Playback input changed while hashing')
    return digest


def _worker_fingerprint(worker: Path, cancel: Event | None) -> str:
    root = protected(worker.parent.parent)
    folders = [worker.parent]
    frozen = getattr(sys, 'frozen', False)
    if not frozen:
        host = protected(root / 'src' / 'ucc')
        if not host.is_dir():
            raise ValidationError('Playback host source is missing')
        folders.extend(protected(host / name) for name in
                       ('animations', 'core', 'desktop', 'jobs', 'preview', 'library'))
    files = sorted(path for folder in folders for path in folder.glob('*.py'))
    if worker not in files or len(files) > 1600:
        raise ValidationError('Unsupported playback worker layout')
    digest = sha256(sys.implementation.cache_tag.encode('ascii'))
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(bytes.fromhex(_hash_file(path, cancel, _HASH_BATCH_LIMIT)))
    if frozen:
        digest.update(bytes.fromhex(_hash_file(Path(sys.executable).resolve(), cancel, 1024**3)))
    return digest.hexdigest()


def _uuid(value: str) -> str:
    if type(value) is not str or str(UUID(value)) != value:
        raise ValidationError('Invalid retained playback job ID')
    return value


@dataclass(frozen=True, slots=True)
class PersistentNativePreview:
    root: Path
    store: ProjectStore
    project: CharacterProject
    authority: NativeSourceAuthority
    selected_profile: Path | None
    worker: Path
    cancel: Event | None

    @property
    def _slot(self) -> str:
        subject = [str(self.store.root), self.project.project_id, str(self.authority.database_path),
                   self.authority.clip_id]
        return sha256(json.dumps(subject, ensure_ascii=True).encode('ascii')).hexdigest()

    def _context(self, blender: Path, budget) -> dict:
        self.authority.guard(cancel=budget.cancel, timeout_s=budget.remaining())
        if self.store.load() != self.project or self.project.master_blend is None:
            raise ValidationError('Saved character changed while checking retained playback')
        master, master_sha = _master_file(self.store, self.project.master_blend)
        selected = find_catalog_preview_profile(self.authority, master_sha)
        if selected != self.selected_profile:
            raise ValidationError('Current automatic mapping changed')
        return {
            'version': _VERSION, 'project_id': self.project.project_id, 'revision': self.project.revision,
            'master': str(master), 'master_sha256': master_sha,
            'source': str(self.authority.source_path), 'source_sha256': self.authority.source_sha256,
            'snapshot_sha256': self.authority.snapshot_sha256, 'receipt_sha256': self.authority.receipt_sha256,
            'clock': asdict(self.authority.clock), 'policy': self.authority.policy.to_dict(),
            'mapping': str(selected) if selected is not None else None,
            'blender': str(blender), 'blender_sha256': _hash_file(blender, budget.cancel, 1024**3),
            'worker_sha256': _worker_fingerprint(self.worker, budget.cancel),
        }

    def capture_context(self, blender: Path) -> dict:
        with operation_budget(self.cancel, 60) as budget:
            return self._context(blender, budget)

    def save(self, playback: NativePlayback, context: dict) -> None:
        cache = playback.cache
        proof = playback.proof_receipt
        if (playback.source_authority is not self.authority or type(proof) is not NativeProofReceipt
                or (playback.project_id, playback.revision, playback.master_sha256,
                    playback.source_sha256) != (self.project.project_id, self.project.revision,
                    context['master_sha256'], self.authority.source_sha256)):
            raise ValidationError('Retained preview must come from the admitted local workflow')
        with operation_budget(self.cancel, 60) as budget:
            if context != self._context(Path(context['blender']), budget):
                raise ValidationError('Playback build or input changed during initial verification')
            proof.guard(cancel=budget.cancel, timeout_s=budget.remaining())
            pins = {str(path): [pin, list(proof.watched_identities[path])]
                    for path, pin in proof.file_hashes.items()}
            manifest = Path(playback.private_manifest)
            geometry = str(manifest.with_name('motion_skin.bin'))
            if geometry not in pins or sha256(cache.packed).hexdigest() != pins[geometry][0]:
                raise ValidationError('Retained bytes differ from the admitted playback geometry')
            document = {
                'context': context, 'proof': pins, 'job': playback.job_id,
                'surface_job': playback.surface_verification_job_id,
                'cache': {
                    'chunks': cache.chunks, 'hips': cache.hips, 'world_matrix': cache.world_matrix,
                    'fps': cache.fps, 'vertex_count': cache.vertex_count,
                    'triangle_count': cache.triangle_count, 'radius': cache.radius,
                    'source_first_frame': cache.source_first_frame,
                    'surface_review': asdict(cache.surface_review) if cache.surface_review else None,
                },
            }
            budget.check()
            write_index(self.root, self._slot, document)

    def restore(self, blender: Path | None) -> NativePlayback | None:
        with operation_budget(self.cancel, 60) as budget:
            record = read_index(self.root, self._slot)
            if record is None:
                return None
            if set(record) != {'context', 'proof', 'job', 'surface_job', 'cache'}:
                raise ValidationError('Unexpected retained playback fields')
            saved = record['context']
            original_blender = Path(saved['blender'])
            if blender is not None and blender != original_blender:
                return None
            current = self._context(original_blender, budget)
            if saved != current:
                return None
            return self._restore_record(record, current, budget)

    def _restore_record(self, record: dict, context: dict, budget) -> NativePlayback:
        job = _uuid(record['job'])
        surface_job = _uuid(record['surface_job']) if record['surface_job'] else ''
        jobs = protected(self.store.root / '.ucc-jobs')
        folder = jobs / job
        manifest = folder / 'motion_skin.json'
        geometry = folder / 'motion_skin.bin'
        external = {self.store.file, Path(context['master']), self.authority.source_path}
        if self.selected_profile is not None:
            external.add(self.selected_profile)
        required = external | {manifest, geometry}
        pins = record['proof']
        if not 5 <= len(pins) <= 48 or any(str(path) not in pins for path in required):
            raise ValidationError('Retained preview is missing its proof files')
        if (pins[str(self.authority.source_path)][0] != self.authority.source_sha256
                or pins[context['master']][0] != context['master_sha256']):
            raise ValidationError('Retained preview source or master identity differs')

        proof = NativeProofCapture(budget)
        # Capture every original identity before reading any corresponding bytes.
        for name, (digest, stamp) in pins.items():
            path = Path(name)
            if (not is_sha256(digest) or (path not in external and
                    (path.parent.parent != jobs or _uuid(path.parent.name) != path.parent.name))):
                raise ValidationError('Retained playback proof escapes the original job namespace')
            proof.before(path)
            if list(proof.identities[path]) != stamp:
                raise ValidationError('An original playback proof file was replaced')
        for name, (digest, _) in pins.items():
            proof.admit(Path(name), digest)
        packed, _ = capture(geometry, MAX_BYTES, budget, expected=pins[str(geometry)][0], retain=True)
        cache = _restore_frames(packed, record['cache'], self.authority)
        receipt = proof.seal()
        self.authority.guard(cancel=budget.cancel, timeout_s=budget.remaining())
        if (not receipt.identities_current() or self.store.load() != self.project
                or find_catalog_preview_profile(self.authority, context['master_sha256']) != self.selected_profile):
            raise ValidationError('Retained preview context changed before it could be displayed')
        budget.check()
        return NativePlayback(self.project.project_id, self.project.revision, context['master_sha256'],
                              self.authority.source_sha256, cache, job, str(manifest), surface_job,
                              self.authority, receipt)


def _restore_frames(packed: bytes, metadata: dict, authority: NativeSourceAuthority) -> MotionCache:
    # The signed metadata was captured from the full native validator. Confirm
    # the partition and source clock against the same hashed bytes before use.
    clock = authority.clock
    rows = tuple(tuple(row) for row in metadata['chunks'])
    hips = tuple(tuple(row) for row in metadata['hips'])
    if (len(rows) != clock.frame_count or len(hips) != clock.frame_count
            or metadata['fps'] != clock.fps or metadata['source_first_frame'] != clock.source_first_frame
            or not packed.startswith(MAGIC)):
        raise ValidationError('Retained playback differs from the current source clock')
    end = len(MAGIC)
    for start, count in rows:
        if start != end or count <= 0:
            raise ValidationError('Retained playback frame ranges differ')
        end += count
    if end != len(packed):
        raise ValidationError('Retained playback frames do not cover the verified bytes')
    surface = metadata['surface_review']
    if surface is not None:
        surface = SurfaceReview(surface['status'], surface['reason'],
            tuple(tuple(row) for row in surface['triangles']), tuple(tuple(row) for row in surface['pairs']),
            tuple(surface['triangle_hashes']), surface['policy'])
    return MotionCache(packed, rows, hips, tuple(metadata['world_matrix']), metadata['fps'],
                       metadata['vertex_count'], metadata['triangle_count'], metadata['radius'],
                       clock.source_first_frame, surface)
