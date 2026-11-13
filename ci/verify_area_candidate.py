"""Real original-source eight-hash candidate negatives; never pack proof."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path

from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure


def verify_area_candidate_negatives(blender,store,playback,source_review,folder):
    folder.mkdir(exist_ok=False);repo=Path(__file__).resolve().parents[1]
    cache=Path(playback.private_manifest).parent
    report=json.loads((cache/'result.json').read_text())['details']
    area=Path(source_review.private_report);bad=json.loads(area.read_text())
    bad['polygons'][0]=list(reversed(bad['polygons'][0]))
    bad['polygon_topology_sha256']=sha256(json.dumps(bad['polygons'],separators=(',',':')).encode()).hexdigest()
    forged=folder/'rehashed-false-source-areas.json';forged.write_text(json.dumps(bad))
    options={**report['bindings'],'surface_review_sha256':report['surface_review']['sha256']}
    names=('candidate.blend','review_motion.blend','target_timeline.json','source_snapshot.json','native_mapping.json','motion_contacts.json')
    before={n:sha256((cache/n).read_bytes()).hexdigest() for n in names};project=store.load()
    def negative(case):
        label,path,reason=case;staged={n:cache/n for n in names};staged['source_body_areas.json']=path
        bound={**options,'source_body_areas_sha256':sha256(path.read_bytes()).hexdigest()}
        request=JobRequest.new('propose_native_area_contact_fit',input_project='candidate.blend',options=bound)
        try:BlenderJobRunner(blender,store.root/'.ucc-jobs',repo/'blender_bridge/entrypoint.py').run(request,timeout_s=900,staged_inputs=staged)
        except WorkerFailure as error:
            if reason not in str(error):raise
            if (store.root/'.ucc-jobs'/request.job_id/'proposed_contact_fit.json').exists():
                raise RuntimeError('Area candidate rejection left a partial policy')
            return label
        raise RuntimeError('Area candidate accepted original negative case: '+label)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rejected=list(pool.map(negative,(('no_crossings',area,'NO_CHECKED_CROSSINGS'),
            ('rehashed_false_areas',forged,'Fresh source body contact areas differ'))))
    if store.load()!=project or before!={n:sha256((cache/n).read_bytes()).hexdigest() for n in names}:
        raise RuntimeError('Area candidate negative changed original source/master/project evidence')
    return {'status':'REAL_ORIGINAL_AREA_CANDIDATE_NEGATIVES_PASSED','source_frames':300,'rejected':rejected,
        'original_inputs_unchanged':True,'partial_candidate_policies_written':False,'candidate_success_claimed':False,
        'contact_quality_approved':False,'engine_import_verified':False}
