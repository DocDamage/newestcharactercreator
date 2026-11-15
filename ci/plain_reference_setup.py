"""Fresh original MPFB targets and authored source; no external animation assets."""
from dataclasses import replace
import json
from pathlib import Path

from ci.regional_sources import require, digest, expected, protected_inputs
from ci.source_reference_checks import clone
from ci.reference_creator_positive import jobs, objects
from ci.verify_regional_skin import fixture
from ucc.animations.catalog import AnimationCatalog
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.animation_reference_storage import check_registered_source
from ucc.jobs.customized_humanoid import generate_customized_humanoid
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.face_revision import bundled_face_assets
from ucc.jobs.fbx_catalog import measure_catalog_fbx
from ucc.jobs.hand_library import build_hand_library
from ucc.jobs.hand_revision import apply_hand_revision
from ucc.jobs.hand_storage import installed_inputs
from ucc.jobs.project_animation_references import attach_catalog_reference
from ucc.library.provenance import LicensePolicy

ROOT = Path(__file__).resolve().parents[1]


def setup(blender: Path, out: Path):
    original = ProjectStore(out/'original')
    initial = original.save(replace(CharacterProject.new('Original unprepared reference acceptance'),
        schema_version=2, parameters=(('height', .5), ('muscle', .5), ('weight', .5)),
        facial_parameters=(('nose_width', .5),)))
    data = discover_face_data(original, blender_exe=blender, worker_script=ROOT/'blender_bridge/entrypoint.py')
    common = dict(blender_exe=blender, worker_script=ROOT/'blender_bridge/entrypoint.py', mpfb_data_dir=data, timeout_s=900)
    installed = {str(p): digest(p) for p, _ in bundled_face_assets(data).values()}
    installed.update({str(p): digest(p) for p in installed_inputs(data).values()})
    generate_customized_humanoid(original, **common, expected_project_id=initial.project_id,
                                 expected_revision=initial.revision)
    require(original.load().expression is None, 'Raw generation introduced prepared expressions')
    nohand = clone(original, out/'nohand-base')
    library = build_hand_library(original, **common, **expected(original.load())).library
    apply_hand_revision(original, manifest_sha256=library.sha256, selection='shorter',
                        **common, **expected(original.load()))
    require(original.load().parts and original.load().expression is None, 'Raw selected-hand target incomplete')
    protected = protected_inputs({'original': original, 'nohand-base': nohand})
    protected[str(original.file)] = digest(original.file)
    protected[str(nohand.file)] = digest(nohand.file)
    authored = out/'authored-source'; project = original.load()
    fixture(blender, ROOT/'tests/fixtures/blender_native_body.py',
        ['--mode', 'author', '--master', original.root/project.master_blend, '--folder', authored,
         '--origin', 'ground', '--corrective-challenge', '--posed-origin-challenge', '--include-hands'],
        out/'author.log', 300)
    source = authored/'original-native-body.fbx'; source_sha = digest(source)
    protected[str(source)] = source_sha
    policy = LicensePolicy('Original UCC plain-reference acceptance armature', 'CC0',
        'ci-original://plain-reference-master', reviewed=True, local_preview_allowed=True, no_ai=True)
    database = out/'catalog.sqlite3'
    with AnimationCatalog(database) as catalog: catalog.index_file('original', source, policy)
    runtime = {k: v for k, v in common.items() if k != 'mpfb_data_dir'}
    measured = measure_catalog_fbx(database, 'original', jobs_root=authored/'.ucc-jobs', **runtime)
    require(len(measured['clips']) == 1, 'Authored source must have exactly one measured real Action')
    source_jobs = set((authored/'.ucc-jobs').glob('*/request.json'))
    clip = measured['clips'][0]['clip_id']; stores = {}
    for name, source_store in (('hand', original), ('nohand', nohand)):
        store = clone(source_store, out/name); current = store.load()
        before_jobs = jobs(store)
        result = attach_catalog_reference(store, database, clip, expected_source_sha256=source_sha,
            expected_policy=policy, **runtime, **expected(current))
        require(result.changed and result.project.expression is None, 'Source attachment altered raw state')
        binding = check_registered_source(store, database, current.project_id, clip)
        require(binding['license'] == policy.to_dict() and binding['source_only'] is True
                and all(binding[k] is False for k in ('editing_authorized', 'target_preview_verified', 'engine_import_verified')),
                'Raw reference gained editing or engine rights')
        stores[name] = store
        source_jobs.update(p for p in jobs(store)-before_jobs
                           if json.loads(p.read_text(encoding='utf-8'))['operation'] == 'inspect_fbx_animation')
        baseline = clone(store, out/('registered-'+name))
        protected[str(baseline.file)] = digest(baseline.file)
        protected.update({str(baseline.root/p): sha for p, sha in objects(baseline).items()})
    require(len(source_jobs) == 6, 'Plain setup lacks paired measurement and both fresh attachments')
    for request in source_jobs:
        raw = json.loads(request.read_text(encoding='utf-8'))
        reply = json.loads((request.parent/'result.json').read_text(encoding='utf-8'))
        snapshot = json.loads((request.parent/'source_snapshot.json').read_text(encoding='utf-8'))
        require(reply['status'] == 'ok' and reply['job_id'] == raw['job_id']
                and reply['operation'] == raw['operation'] == 'inspect_fbx_animation'
                and len(snapshot['bones']) == 71
                and [f['frame'] for f in snapshot['frames']] == list(range(2, 302))
                and digest(request.parent/'source.fbx') == source_sha, 'Incomplete real setup source evidence')
    print('REAL_ORIGINAL_PLAIN_REFERENCE_SETUP_PASSED', flush=True)
    protected.update(installed)
    return stores, database, common, protected, source_sha
