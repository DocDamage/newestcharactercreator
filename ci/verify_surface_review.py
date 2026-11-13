"""Real saved-scene surface fault and rehashed-annotation rejection gate."""
from pathlib import Path
from hashlib import sha256
import json,struct,subprocess
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure


def verify_surface_review(blender: Path,repo: Path,playback,folder: Path) -> dict:
    cache=Path(playback.private_manifest).parent
    probe=folder/'surface-fault-probe.json'
    subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','13',
        '--python',str(repo/'tests/fixtures/blender_surface_review.py'),'--','--job',str(cache),'--output',str(probe)],check=True,timeout=300)
    data=json.loads((cache/'motion_contacts.json').read_text());bindings=dict(data['bindings'])
    record=data['frames'][19]['left']
    record.update(pair_count=1,hand_triangles=[1],opposite_arm_triangles=[2],pair_sha256=sha256(struct.pack('<II',1,2)).hexdigest())
    forged=folder/'forged-surface-review.json';forged.write_text(json.dumps(data))
    options={**bindings,'surface_review_sha256':sha256(forged.read_bytes()).hexdigest()}
    staged={name:cache/name for name in ('candidate.blend','review_motion.blend','source_snapshot.json','native_mapping.json','target_timeline.json')}
    staged['motion_contacts.json']=forged
    before={n:sha256(p.read_bytes()).hexdigest() for n,p in staged.items()}
    try:
        BlenderJobRunner(blender,folder/'.surface-negative-jobs',repo/'blender_bridge/entrypoint.py').run(
            JobRequest.new('verify_native_surface_review',input_project='candidate.blend',options=options),timeout_s=300,staged_inputs=staged)
    except WorkerFailure as error:
        if 'surface review/topology differs' not in str(error):raise
    else:raise RuntimeError('Rehashed fabricated intersections were accepted')
    if before!={n:sha256(p.read_bytes()).hexdigest() for n,p in staged.items()}:raise RuntimeError('Surface negative changed staged originals')
    return {**json.loads(probe.read_text()),'rehashed_fabricated_intersections_rejected':True,'original_bound_inputs_unchanged':True}
