"""Build original MPFB CI targets through normal app transactions; no external assets."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from ucc.core.commands import CharacterSession
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.customized_humanoid import generate_customized_humanoid
from ucc.jobs.expression_keys import installed_expression_inputs
from ucc.jobs.expression_preparation import prepare_saved_expressions
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.face_revision import bundled_face_assets
from ucc.jobs.hand_library import build_hand_library
from ucc.jobs.hand_revision import apply_hand_revision
from ucc.jobs.hand_storage import installed_inputs

NAMES = ('short-light-narrow', 'middle-neutral', 'tall-muscular-wide')
CASES = ((.3, .2, .25, 0.), (.5, .5, .5, .5), (.8, .8, .75, 1.))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def expected(project) -> dict:
    return dict(expected_project_id=project.project_id, expected_revision=project.revision,
                expected_master_blend=project.master_blend)


def build_targets(blender: Path, worker: Path, out: Path) -> tuple[dict, dict]:
    discovery = ProjectStore(out/'asset-inspection')
    discovery.save(CharacterProject.new('Original regional CI asset inspection'))
    data = discover_face_data(discovery, blender_exe=blender, worker_script=worker)
    installed = {str(p): digest(p) for p, _ in bundled_face_assets(data).values()}
    installed.update({str(p): digest(p) for p in installed_expression_inputs(data).values()})
    installed.update({str(p): digest(p) for p in installed_inputs(data).values()})
    common = dict(blender_exe=blender, worker_script=worker, mpfb_data_dir=data)
    stores = {}
    for name, (height, muscle, weight, nose) in zip(NAMES, CASES):
        store = ProjectStore(out/name)
        initial = store.save(replace(CharacterProject.new('Original regional '+name), schema_version=2,
            parameters=tuple(zip(('height', 'muscle', 'weight'), (height, muscle, weight))),
            facial_parameters=(('nose_width', nose),)))
        generated = generate_customized_humanoid(store, **common, expected_project_id=initial.project_id,
                                               expected_revision=initial.revision)
        require(generated.revision.project == store.load(), 'Original customized target did not publish')
        if name == 'middle-neutral':
            library = build_hand_library(store, **common, **expected(store.load()))
            selected = apply_hand_revision(store, **common, manifest_sha256=library.library.sha256,
                                           selection='shorter', **expected(store.load()))
            require(bool(selected.project.parts), 'Original middle target has no registered selected hand')
        before = store.load()
        prepare_saved_expressions(store, **common, **expected(before))
        ready = store.load()
        if before.parts:
            require(len(ready.parts) == len(before.parts) and ready.parts[0].part_id == before.parts[0].part_id
                    and ready.parts[0].part_asset_id != before.parts[0].part_asset_id,
                    'Expression preparation did not genuinely rebuild the selected hand')
        else:
            require(not ready.parts, 'Expression preparation invented a selected hand')
        for key, _ in ready.expression.parameters:
            current = store.load(); session = CharacterSession(current)
            session.set_expression_parameter(key, .5)
            store.save(session.project, expected_revision=current.revision)
        saved = store.load()
        require(not saved.animations and all(v == .5 for _, v in saved.expression.parameters),
                'Original target did not retain neutral master intent and bounded saved strengths')
        require(saved.parameters == initial.parameters and saved.facial_parameters == initial.facial_parameters,
                'Original target preparation lost its body or face intent')
        stores[name] = store
        print('ORIGINAL_REGIONAL_TARGET_BUILT', name, flush=True)
    require(all(digest(Path(p)) == h for p, h in installed.items()), 'Installed MPFB data changed')
    return stores, installed


def protected_inputs(stores: dict) -> dict[str, str]:
    paths = []
    for store in stores.values():
        paths.append(store.file)
        for name in ('master', 'parts', 'expressions'):
            paths.extend(p for p in (store.root/name).rglob('*') if p.is_file())
    require(all(not p.is_symlink() for p in paths), 'Original regional inputs are redirected')
    return {str(p): digest(p) for p in paths}
