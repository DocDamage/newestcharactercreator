"""Exercise original regional saved-scene corruptions through the normal worker."""
import json
from pathlib import Path

from ci.regional_sources import digest, require
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner, WorkerFailure

EXPECTED = {
    'missing_layer': ('different original or owned state',),
    'reordered_layers': ('changed ordered settings or binding',),
    'unbound_layer': ('changed ordered settings or binding',),
    'coherent_factor': ('changed ordered settings or binding',),
    'bone_weight_ulp': ('original groups or exact source weights changed',),
    'coherent_mask_ulp': ('fixed original-weight formula',),
    'missing_mask': ('original groups or exact source weights changed', 'changed ordered settings or binding'),
    'boolean_schema': ('different original or owned state',),
}


def verify_faults(blender: Path, worker: Path, preview, out: Path) -> dict:
    from ci.verify_regional_skin import fixture, ROOT
    out.mkdir(exist_ok=False); job = Path(preview.private_timeline).parent
    protected = {str(p): digest(p) for p in job.iterdir() if p.is_file()}
    script = ROOT/'tests/fixtures/blender_regional_faults.py'
    fixture(blender, script, ['--mode', 'saved', '--job', job, '--outdir', out/'saved'], out/'saved.log')
    generated = json.loads((out/'saved/generated.json').read_text(encoding='utf-8'))
    require(set(generated) == set(EXPECTED), 'Original saved fault set differs')
    data = json.loads((job/'target_timeline.json').read_text(encoding='utf-8')); rejected = []
    for name, record in generated.items():
        folder = out/'saved'/name
        options = {**data['bindings'], 'review_sha256': record['review_sha256'], 'timeline_sha256': record['timeline_sha256']}
        staged = {name: job/name for name in ('candidate.blend', 'source_snapshot.json', 'native_mapping.json')}
        staged.update({name: folder/name for name in ('review_motion.blend', 'target_timeline.json')})
        before = {str(p): digest(p) for p in staged.values()}
        request = JobRequest.new('reopen_native_fbx_body', input_project='candidate.blend', options=options)
        runner = BlenderJobRunner(blender, out/'jobs', worker)
        try: runner.run(request, timeout_s=900, staged_inputs=staged)
        except WorkerFailure: pass
        else: raise RuntimeError('Original regional saved fault was accepted: '+name)
        result = json.loads((runner.jobs_root/request.job_id/'result.json').read_text(encoding='utf-8'))
        require(result['status'] == 'error' and result['error'].startswith('ValueError:') and
                any(text in result['error'] for text in EXPECTED[name]), 'Saved fault failed for an unrelated reason')
        require(all(digest(Path(p)) == h for p, h in before.items()), 'Saved fault verification changed inputs')
        rejected.append(name)
    fixture(blender, script, ['--mode', 'transaction', '--job', job, '--outdir', out/'transaction'], out/'transaction.log')
    transaction = json.loads((out/'transaction/transactions.json').read_text(encoding='utf-8'))
    require(all(digest(Path(p)) == h for p, h in protected.items()), 'Original fault checks changed accepted evidence')
    return {'saved_faults_rejected': rejected, **transaction,
            'coherently_rehashed_scenes_and_timelines': True, 'originals_unchanged': True}
