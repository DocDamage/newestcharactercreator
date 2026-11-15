"""Non-shipping preview metadata stub, never actual geometry/cache evidence."""
from hashlib import sha256
import json

from ucc.core.expression_clip import build_expression_clip
from ucc.core.expression_library import canonical_digest
from ucc.jobs.expression_inspection import CheckedExpressionMaster
from ucc.jobs.expression_preview import ExpressionPreview


def body_runner_stub(root, source, reports):
    """Fake subprocess output for core read-back rejection tests only."""
    from types import SimpleNamespace
    import shutil
    pending = iter(reports); calls = []
    def run(request, **kwargs):
        directory = root/('unit-body-'+str(len(calls))); directory.mkdir()
        shutil.copyfile(source, directory/'candidate.blend')
        (directory/'request.json').write_text('{}', encoding='utf-8', newline='\n')
        (directory/'result.json').write_text('{}', encoding='utf-8', newline='\n')
        calls.append(request)
        return SimpleNamespace(details=next(pending)), directory
    return run, calls


def preview_stub(store, **kwargs):
    project = store.load(); master = store.root/project.master_blend
    sha = master.stem; jobs = store.root/'.ucc-jobs'; jobs.mkdir(exist_ok=True)
    stage = jobs/'unit-stage'; verify = jobs/'unit-reopen'
    stage.mkdir(); verify.mkdir()
    clip = build_expression_clip(project, sha); clip_sha = canonical_digest(clip)
    observed = {'synthetic_only': True, 'observation': {'all_keys': {
        'nose-scale-horiz-decr': {'value': 0.}, 'nose-scale-horiz-incr': {'value': 0.}}}}
    report = stage/'unit-inspection.json'
    report.write_text(json.dumps(observed, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
    inspection = CheckedExpressionMaster(master, sha, observed, report,
        sha256(report.read_bytes()).hexdigest(), 'unit-inspect-one', 'unit-inspect-two')
    return ExpressionPreview(None, project.project_id, project.revision, project.master_blend,
        sha, project.expression.library_sha256, clip_sha, {'master_sha256': sha, 'clip_sha256': clip_sha},
        {'synthetic_only': True}, stage, verify, stage.name, verify.name, inspection)
