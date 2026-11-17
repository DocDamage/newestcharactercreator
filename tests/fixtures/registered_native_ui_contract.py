"""NONSHIPPING source/catalog/skin fixtures; no real FBX, Blender or GPU proof."""
from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace

from fixtures.fbx_snapshot_contract import snapshot, report
from fixtures.motion_skin_contract import write_cache
from ucc.animations.catalog import AnimationCatalog
from ucc.core.master_versions import stage_unverified_master
from ucc.jobs.native_body import NativeBodyPreview
from ucc.jobs.native_playback import NativePlayback
from ucc.library.provenance import LicensePolicy
from ucc.preview.motion_cache import read_motion_cache


def synthetic_canvas_type():
    """Explicit renderer stand-in for transport tests; never GPU evidence."""
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QWidget
    class Canvas(QWidget):
        failed = Signal(str)
        def __init__(self, cache, parent=None, *, paint_guard=None):
            super().__init__(parent)
            self.cache=cache; self.frame=0; self._paint_guard=paint_guard
            self.released=False; self.yaw=self.pitch=0.; self.zoom=1.; self.pan=(0.,0.)
            self.submissions=[]; self.error=''
        def update(self): self.submissions.append(self.frame)
        def release(self): self.released=True; self.cache=None
        def reset_view(self): self.yaw=self.pitch=0.; self.zoom=1.; self.pan=(0.,0.)
    return Canvas


def synthetic_environment(root, controller):
    controller.create(root/'p', 'NONSHIPPING registered-source UI test')
    master = root/'synthetic-not-real.blend'
    master.write_bytes(b'BLENDER_NONSHIPPING_UI_BOUNDARY_ONLY')
    staged = stage_unverified_master(controller.store, master, authorized_source_root=root)
    controller.open(root/'p')
    source = root/'synthetic-not-real.fbx'; source.write_bytes(b'NONSHIPPING_NOT_FBX')
    source_sha = sha256(source.read_bytes()).hexdigest()
    policy = LicensePolicy('Original test', 'Synthetic nonshipping', 'test://registered-native-ui',
        reviewed=True, no_ai=True, local_preview_allowed=True)
    data = snapshot(); data['source_sha256'] = source_sha
    payload = json.dumps(data).encode()
    observed = report(data, payload) | {'two_workers_agree':True,
        'source_bytes_unchanged':True, 'policy':policy.to_dict()}
    database = root/'owned-catalog.sqlite3'
    with AnimationCatalog(database) as catalog:
        catalog.index_file('source', source, policy)
        catalog.record_fbx_intake('source', data, observed, expected_entry=catalog.library.get('source'))
    folder = controller.store.root/'.ucc-jobs/nonshipping-ui-boundary'
    folder.mkdir(parents=True)
    (folder/'source_snapshot.json').write_bytes(payload)
    (folder/'native_mapping.json').write_text('{}')
    evidence = {'source_frame_count':4,'fps':30.,'mapped_pairs':[],
        'omitted_source_bones':[], 'root_motion_metrics':{'max_distance_from_bind_world':0.},
        'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1'}
    (folder/'target_timeline.json').write_text(json.dumps(evidence))
    (folder/'review_motion.blend').write_bytes(b'NONSHIPPING_NOT_AN_ANIMATION')
    cache_folder = root/'nonshipping-cache'; cache_folder.mkdir()
    _, cache_report, bindings, timeline = write_cache(cache_folder)
    cache = read_motion_cache(cache_folder, cache_report, bindings, timeline)
    cache = replace(cache, chunks=(cache.chunks[0],)*4, hips=(cache.hips[0],)*4,
                    source_first_frame=1, fps=30.)
    project = controller.require_project()
    def proof(include_cache=False):
        from ucc.jobs.native_source_authority import NativeProofCapture
        from ucc.jobs.target_action_context import operation_budget
        paths = [controller.store.file, staged.master_path, *folder.iterdir()]
        if include_cache: paths.extend(cache_folder.iterdir())
        with operation_budget(None, 5) as budget:
            captured = NativeProofCapture(budget)
            for path in paths:
                captured.before(path)
                captured.admit(path, sha256(path.read_bytes()).hexdigest())
            return captured.seal()
    def preview(authority, proof_receipt=None):
        return NativeBodyPreview(project.project_id,project.revision,sha256(staged.master_path.read_bytes()).hexdigest(),
            source_sha,evidence,str(folder/'review_motion.blend'),'',str(folder/'target_timeline.json'),
            ('nonshipping-fk-one','nonshipping-fk-two'),str(folder/'native_mapping.json'),
            source_authority=authority,proof_receipt=proof_receipt)
    def playback(authority, proof_receipt=None):
        return NativePlayback(project.project_id,project.revision,sha256(staged.master_path.read_bytes()).hexdigest(),
            source_sha,cache,'nonshipping-cache-job',str(cache_folder/'motion_skin.json'),
            source_authority=authority,proof_receipt=proof_receipt)
    return SimpleNamespace(source=source,source_sha=source_sha,policy=policy,database=database,
        project=project,folder=folder,cache_folder=cache_folder,cache=cache,preview=preview,
        playback=playback,proof=proof)
