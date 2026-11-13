"""Actual original-source MPFB skin observations and rehashed-fabrication rejection."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from ucc.jobs.skin_inclusion import review_skin_inclusion
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure

ROOT=Path(__file__).resolve().parents[1]


def verify_skin_review(blender,store,preview,playback,source,permission,folder):
    folder.mkdir(exist_ok=False);project=store.load();digest=lambda p:sha256(Path(p).read_bytes()).hexdigest()
    originals=[source,store.root/project.master_blend,store.root/'project.ucc.json',
        Path(preview.private_visual_review_blend),Path(preview.private_timeline)]
    before=[digest(p) for p in originals]
    result=review_skin_inclusion(store,preview,playback,source_fbx=source,permission=permission,
        blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',timeout_s=1800)
    original=result.observations.original
    if original.status!='CHECKED' or len(original.nonzero)!=300 or len(original.ambiguous)!=300 or result.observations.fitted is not None:
        raise RuntimeError('Original skin inclusion lacks complete independently reproduced observations')
    report=Path(result.private_report);bad=json.loads(report.read_text(encoding='utf-8'))
    # A plausible changed diagnostic with a freshly matching SHA still must be
    # reproduced from the saved Action, never trusted as a self-signed verdict.
    bad['original']['frames'][7]['observation']['ray_queries']+=1
    forged=folder/'rehashed-false-skin-observations.json';forged.write_text(json.dumps(bad),encoding='utf-8')
    staged={n:report.parent/n for n in ('candidate.blend','review_motion.blend','source_snapshot.json','native_mapping.json','target_timeline.json')}
    staged['body_contacts.json']=forged
    options={**dict(result.bindings),'body_review_sha256':digest(forged)}
    try:
        BlenderJobRunner(blender,store.root/'.ucc-jobs',ROOT/'blender_bridge/entrypoint.py').run(
            JobRequest.new('verify_native_skin_inclusion',input_project='candidate.blend',options=options),timeout_s=1800,staged_inputs=staged)
    except WorkerFailure as error:
        if 'Fresh saved-scene closed-skin observations differ' not in str(error):raise
    else:raise RuntimeError('Rehashed false closed-skin observations were accepted')
    probe=folder/'skin-inclusion-fault-summary.json'
    subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','13',
        '--python',str(ROOT/'tests/fixtures/blender_skin_inclusion_faults.py'),'--','--job',str(report.parent),'--output',str(probe)],
        check=True,timeout=600)
    if store.load()!=project or before!=[digest(p) for p in originals]:raise RuntimeError('Skin inclusion changed original project/source/master')
    return {'status':'REAL_ORIGINAL_SKIN_INCLUSION_GATE_PASSED','source_frames':300,'independent_workers':2,
        'scope':'ORIGINAL_CI_SOURCE_ON_REAL_MPFB_NOT_OWNER_OR_PACK_COMPATIBILITY','all_skin_and_topology_rows_verified':True,
        'rehashed_fabricated_observations_rejected':True,'geometry_faults':json.loads(probe.read_text(encoding='utf-8')),
        'original_inputs_unchanged':True,'assets_uploaded':False,'contact_quality_approved':False,'engine_import_verified':False}
