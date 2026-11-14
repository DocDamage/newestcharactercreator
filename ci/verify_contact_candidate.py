"""Real original-source negative gates; no owner assets or contact success claim."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import struct

from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure


def verify_candidate_negatives(blender: Path,store,folder: Path) -> dict:
    folder.mkdir(exist_ok=False);repo=Path(__file__).resolve().parents[1];jobs=store.root/'.ucc-jobs'
    candidates=[]
    for result in jobs.glob('*/result.json'):
        data=json.loads(result.read_text())
        if data['operation']=='cache_native_fbx_body' and data['status']=='ok':candidates.append((result.parent,data['details']))
    if len(candidates)!=1:raise RuntimeError('Original candidate-negative gate needs one unambiguous verified source cache')
    original,report=candidates[0];options={**report['bindings'],'surface_review_sha256':report['surface_review']['sha256']}
    contact=json.loads((original/'motion_contacts.json').read_text())
    if contact['status']!='CHECKED' or any(r[s]['pair_count'] for r in contact['frames'] for s in ('left','right')):
        raise RuntimeError('Original no-contact negative fixture unexpectedly contains crossings')
    forged=json.loads(json.dumps(contact));forged['frames'][7]['left']={'pair_count':1,
        'pair_sha256':sha256(struct.pack('<II',1,2)).hexdigest(),'hand_triangles':[1],'opposite_arm_triangles':[2]}
    fake=folder/'rehashed-false-contacts.json';fake.write_text(json.dumps(forged))
    names=('candidate.blend','review_motion.blend','target_timeline.json','native_mapping.json','source_snapshot.json','motion_contacts.json')
    before={name:sha256((original/name).read_bytes()).hexdigest() for name in names};project=store.load()
    def negative(case):
        label,reason=case;staged={n:original/n for n in names};bound=dict(options)
        if label=='fabricated_source_contacts':
            staged['motion_contacts.json']=fake;bound['surface_review_sha256']=sha256(fake.read_bytes()).hexdigest()
        request=JobRequest.new('propose_native_contact_fit',input_project='candidate.blend',options=bound)
        try:BlenderJobRunner(blender,jobs,repo/'blender_bridge/entrypoint.py').run(request,timeout_s=600,staged_inputs=staged)
        except WorkerFailure as error:
            if reason not in str(error):raise
            return label
        raise RuntimeError('Contact proposal accepted an original negative case: '+label)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rejected=list(pool.map(negative,(('no_checked_crossings','NO_CHECKED_CROSSINGS'),
            ('fabricated_source_contacts','Fresh saved-scene surface review/topology differs'))))
    if store.load()!=project or before!={n:sha256((original/n).read_bytes()).hexdigest() for n in names}:
        raise RuntimeError('Contact negative gate changed source/master/project inputs')
    return {'status':'REAL_ORIGINAL_CANDIDATE_NEGATIVES_PASSED','source_frames':contact['frame_count'],
            'rejected':rejected,'original_inputs_unchanged':True,'candidate_success_claimed':False,
            'contact_quality_approved':False,'engine_import_verified':False}
