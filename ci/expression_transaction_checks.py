"""Real preview timeout, cancellation and same-revision external edit guards."""
from hashlib import sha256
import json
from pathlib import Path
from threading import Event, Thread

from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.jobs.expression_preview import preview_saved_expressions
from ucc.jobs.runner import WorkerFailure


def require(condition, message):
    if not condition: raise RuntimeError(message)


def after_stage(store, action):
    jobs = store.root/'.ucc-jobs'; old = {p.name for p in jobs.iterdir()}
    stopped = Event(); triggered = []; errors = []
    def watch():
        while not stopped.wait(.02):
            for path in jobs.glob('*/result.json'):
                if path.parent.name in old: continue
                try:
                    request = json.loads((path.parent/'request.json').read_text())
                    result = json.loads(path.read_text())
                    if request['operation'] == 'stage_mpfb_expression_clip' and result['status'] == 'ok':
                        action(); triggered.append(True); return
                except (ValueError, FileNotFoundError): continue
                except Exception as error: errors.append(type(error).__name__); return
    thread = Thread(target=watch, daemon=True); thread.start()
    return stopped, thread, triggered, errors


def verify_guards(store, common: dict, out: Path) -> dict:
    out.mkdir(exist_ok=False)
    project = store.load(); baseline = store.file.read_bytes()
    masters = {str(p): sha256(p.read_bytes()).hexdigest() for p in (store.root/'master/versions').glob('*.blend')}
    expected = dict(expected_project_id=project.project_id, expected_revision=project.revision,
                    expected_master_blend=project.master_blend)
    cancel = Event(); cancel.set()
    try: preview_saved_expressions(store, **common, **expected, cancel=cancel)
    except ProjectStorageError: pass
    else: raise RuntimeError('Pre-cancelled expression preview was accepted')
    require(store.file.read_bytes() == baseline, 'Pre-cancel changed saved expression authority')
    try: preview_saved_expressions(store, **common, **expected, timeout_s=.05)
    except WorkerFailure as error: require('timed out' in str(error).lower(), 'Expected actual expression worker timeout')
    else: raise RuntimeError('Expression worker unexpectedly survived startup timeout')
    require(store.file.read_bytes() == baseline, 'Timeout changed expression authority')
    cancel = Event(); stopped, thread, triggered, errors = after_stage(store, cancel.set)
    try:
        try: preview_saved_expressions(store, **common, **expected, cancel=cancel)
        except (WorkerFailure, ProjectStorageError) as error:
            require('cancel' in str(error).lower(), 'Post-stage cancellation failed for an unrelated reason')
        else: raise RuntimeError('Cancelled complete expression stage returned a preview')
    finally: stopped.set(); thread.join(3)
    require(triggered and not errors and store.file.read_bytes() == baseline, 'Actual expression stage cancel lost authority')
    external = []
    def edit():
        metadata = json.loads(store.file.read_bytes())
        metadata['expression']['parameters']['mouth_open'] = .125
        store.file.write_text(json.dumps(metadata), encoding='utf-8')
        external.append(store.file.read_bytes())
    stopped, thread, triggered, errors = after_stage(store, edit)
    try:
        try: preview_saved_expressions(store, **common, **expected)
        except ProjectConflict: pass
        else: raise RuntimeError('Expression preview accepted changed same-revision strengths')
    finally: stopped.set(); thread.join(3)
    require(triggered and not errors and external and store.file.read_bytes() == external[0],
            'Actual external expression strength change was not retained')
    require(masters == {p: sha256(Path(p).read_bytes()).hexdigest() for p in masters}, 'Expression guards changed saved masters')
    return {'pre_cancel_preserved_authority': True, 'real_worker_timeout_preserved_authority': True,
            'actual_post_stage_cancel_preserved_authority': True, 'same_revision_post_stage_external_strength_retained': True,
            'all_previous_master_bytes_preserved': True}
