"""Real original-source trunk enclosure and surface-area two-process contract."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from ucc.jobs.body_contact_review import review_anatomical_safety
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure

ROOT=Path(__file__).resolve().parents[1]


def verify_anatomical_review(blender,store,preview,playback,source,permission,folder):
    folder.mkdir(exist_ok=False);project=store.load();digest=lambda p:sha256(Path(p).read_bytes()).hexdigest()
    originals=[source,store.root/project.master_blend,store.root/'project.ucc.json',
        Path(preview.private_visual_review_blend),Path(preview.private_timeline)]
    before=[digest(p) for p in originals]
    result=review_anatomical_safety(store,preview,playback,source_fbx=source,permission=permission,
        blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',timeout_s=1800)
    if (result.areas.status!='CHECKED' or result.enclosure.fitted is not None or
        len(result.enclosure.original.inside)!=300 or len(result.enclosure.original.ambiguous)!=300):
        raise RuntimeError('Anatomical review lacks independently reproduced complete source coverage')
    report=Path(result.private_enclosure_report);bad=json.loads(report.read_text(encoding='utf-8'))
    # Rehashed metadata still must match actual fresh saved-Action measurements.
    bad['original']['frames'][7]['observation']['ray_queries']+=1
    forged=folder/'rehashed-false-enclosure.json';forged.write_text(json.dumps(bad),encoding='utf-8')
    staged={n:report.parent/n for n in ('candidate.blend','review_motion.blend','source_snapshot.json',
        'native_mapping.json','target_timeline.json','body_contacts.json')}
    staged['central_enclosure.json']=forged
    options={**dict(result.bindings),'body_review_sha256':result.report_sha256,'enclosure_review_sha256':digest(forged)}
    try:
        BlenderJobRunner(blender,store.root/'.ucc-jobs',ROOT/'blender_bridge/entrypoint.py').run(
            JobRequest.new('verify_native_anatomical_safety',input_project='candidate.blend',options=options),
            timeout_s=1800,staged_inputs=staged)
    except WorkerFailure as error:
        if 'Fresh anatomical surface/enclosure evidence differs' not in str(error):raise
    else:raise RuntimeError('Rehashed false anatomical enclosure was accepted')
    probe=folder/'central-enclosure-fault-summary.json'
    subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','13',
        '--python',str(ROOT/'tests/fixtures/blender_central_enclosure_faults.py'),'--','--job',str(report.parent),
        '--output',str(probe)],check=True,timeout=600)
    if store.load()!=project or before!=[digest(p) for p in originals]:raise RuntimeError('Anatomical gate changed protected originals')
    return {'status':'REAL_ORIGINAL_ANATOMICAL_SAFETY_GATE_PASSED','source_frames':300,'independent_workers':2,
        'scope':'ORIGINAL_CI_SOURCE_ON_REAL_MPFB_NOT_OWNER_OR_PACK_COMPATIBILITY',
        'all_skin_and_topology_rows_verified':True,'stable_surface_areas_and_enclosure_reproduced_together':True,
        'rehashed_fabricated_enclosure_rejected':True,'geometry_faults':json.loads(probe.read_text(encoding='utf-8')),
        'original_inputs_unchanged':True,'assets_uploaded':False,'contact_quality_approved':False,'engine_import_verified':False}
