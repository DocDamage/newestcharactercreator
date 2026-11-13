"""Real original-source body-contact gate; only aggregate JSON leaves CI."""
from dataclasses import replace
from hashlib import sha256
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.body_contact_review import review_body_contacts
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure


def verify_body_review(blender,store,preview,playback,source,permission,folder):
    folder.mkdir(exist_ok=False)
    project=store.load();digest=lambda p:sha256(Path(p).read_bytes()).hexdigest()
    originals=[source,store.root/project.master_blend,store.root/'project.ucc.json',
               Path(preview.private_visual_review_blend),Path(preview.private_timeline)]
    before=[digest(p) for p in originals]
    result=review_body_contacts(store,preview,playback,source_fbx=source,permission=permission,
        blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py')
    body=result.contacts.original
    if body.status!='CHECKED' or len(body.pairs)!=300 or result.contacts.fitted is not None:
        raise RuntimeError('Original body inspection lacks complete independently reproduced coverage')
    report=Path(result.private_report);data=json.loads(report.read_text());bad=json.loads(report.read_text())
    # Rehash a plausible but false complete report: matching input SHA is not
    # evidence that the saved geometry actually generated these annotations.
    bad['original']['frames'][7]['right']['pair_sha256']='0'*64
    forged=folder/'rehashed-false-body-contacts.json';forged.write_text(json.dumps(bad))
    original_job=report.parent
    staged={n:original_job/n for n in ('candidate.blend','review_motion.blend','source_snapshot.json',
        'native_mapping.json','target_timeline.json')}
    staged['body_contacts.json']=forged
    options={**dict(result.bindings),'body_review_sha256':digest(forged)}
    try:
        BlenderJobRunner(blender,store.root/'.ucc-jobs',ROOT/'blender_bridge/entrypoint.py').run(
            JobRequest.new('verify_native_body_contacts',input_project='candidate.blend',options=options),
            timeout_s=900,staged_inputs=staged)
    except WorkerFailure as error:
        if 'Fresh saved-scene central-body contacts/topology differ' not in str(error):raise
    else:raise RuntimeError('Rehashed fabricated central-body observations were accepted')
    probe=folder/'body-fault-probe.json'
    subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','13',
        '--python',str(ROOT/'tests/fixtures/blender_body_contact_faults.py'),'--','--job',str(original_job),
        '--output',str(probe)],check=True,timeout=300)
    if store.load()!=project or [digest(p) for p in originals]!=before:
        raise RuntimeError('Body contact gate changed source/master/project evidence')
    return {'status':'REAL_ORIGINAL_BODY_CONTACT_GATE_PASSED','source_frames':300,
        'scope':'ORIGINAL_CI_SOURCE_ON_REAL_MPFB_NOT_OWNER_OR_PACK_COMPATIBILITY',
        'independent_workers':2,'all_skin_and_topology_rows_verified':True,
        'source_flagged_frames':len(body.flagged_frames),'source_only_supported':True,
        'rehashed_fabricated_observations_rejected':True,'geometry_fault':json.loads(probe.read_text()),
        'original_inputs_unchanged':True,'assets_uploaded':False,'contact_quality_approved':False,
        'engine_import_verified':False}


def verify(blender,root):
    from ucc.jobs.humanoid_generation import generate_humanoid
    from ci.verify_native_body import verify_native_body
    root.mkdir(parents=True,exist_ok=False);store=ProjectStore(root/'project')
    project=store.save(CharacterProject.new('Original body-contact CI'))
    project=store.save(replace(project,parameters=tuple(sorted({'height':.66,'muscle':.76,'weight':.33}.items())),
        revision=project.revision+1),expected_revision=project.revision)
    generate_humanoid(store,blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',
        expected_project_id=project.project_id,expected_revision=project.revision,timeout_s=300)
    body=verify_native_body(blender,store,root/'original-native-source',hip_anchor=True,corrective=True,
        neutral_reference=True,include_hands=True,body_check=True)
    summary={'status':'REAL_ORIGINAL_BODY_CONTACT_SUITE_PASSED','native_body':body,
        'body_contacts':body['central_body_contact_contract'],'assets_uploaded':False,'engine_import_verified':False}
    (root/'body_contact_summary.json').write_text(json.dumps(summary,indent=2));return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--blender',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True);args=parser.parse_args()
    summary=verify(args.blender,args.outdir);print(json.dumps(summary))
