"""Read-only original-source closure for normal native runtime production."""
from pathlib import Path
from threading import Event
from typing import Callable

from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.export.godot_native_recipe import build_native_recipe
from ucc.export.godot_runtime_contract import CODE_FILES
from .godot_candidate_inputs import project_sources,regular_file,identity,read_json,check_cancel
from .master_preview import _digest
from .native_body import NativeBodyPreview
from .worker_resources import worker_dependency_files


def admit_native_production(store,runner,preview: NativeBodyPreview,*,source_fbx: Path,
        authorized_source_root: Path,authorized_native_root: Path,runtime_directory: Path,
        motion_asset_id: str,permissions: tuple,capability: str,cancel: Event | None,
        check: Callable[[],None]) -> dict:
    check();store._check_safety();project=store.load();project_sha=_digest(store.file,cancel)
    sources=dict(project_sources(store,project,cancel))
    if (not isinstance(preview,NativeBodyPreview) or preview.project_id!=project.project_id
            or preview.revision!=project.revision or preview.master_sha256!=Path(project.master_blend).stem
            or type(preview.worker_report) is not dict or type(preview.reopen_evidence) is not dict
            or len(preview.worker_job_ids)!=2 or not preview.private_reopen_job_id):
        raise ProjectConflict('Native preview does not belong to this exact saved prepared character')
    source=regular_file(source_fbx,authorized_source_root,256*1024*1024)
    if source.suffix.lower()!='.fbx' or _digest(source,cancel)!=preview.source_sha256:
        raise ValidationError('Native original FBX differs from the preview source')
    if type(motion_asset_id) is not str or not motion_asset_id.startswith('motion:') or motion_asset_id in sources:
        raise ValidationError('Native producer needs an explicit original motion identity')
    sources[motion_asset_id]=source
    timeline=regular_file(Path(preview.private_timeline),authorized_native_root,64*1024*1024)
    folder=timeline.parent
    if folder.name!=preview.worker_job_ids[0] or timeline.name!='target_timeline.json':
        raise ValidationError('Native preview timeline is outside its bound first worker')
    evidence={'native_review':regular_file(Path(preview.private_visual_review_blend),authorized_native_root,512*1024*1024),
        'native_timeline':timeline,'source_snapshot':regular_file(folder/'source_snapshot.json',authorized_native_root,64*1024*1024),
        'native_mapping':regular_file(Path(preview.mapping_profile_used),authorized_native_root,64*1024)}
    if evidence['native_review'].parent!=folder or evidence['native_review'].name!='review_motion.blend':
        raise ValidationError('Native review is outside its bound first worker')
    implementation={name:regular_file(runtime_directory/name,runtime_directory,256*1024) for name in CODE_FILES}
    bindings={name:_digest(path,cancel) for name,path in sources.items()}
    evidence_bindings={name:_digest(path,cancel) for name,path in evidence.items()}
    code_hashes={name:_digest(path,cancel) for name,path in implementation.items()}
    recipe=build_native_recipe(project,project_sha,bindings,evidence_bindings,code_hashes,permissions,motion_asset_id,capability)
    roots=(store.root,authorized_source_root,authorized_native_root,runtime_directory)
    watched={store.file,*roots,*sources.values(),*evidence.values(),*implementation.values()}
    worker=regular_file(Path(runner.worker_script),Path(runner.worker_script).parent,256*1024)
    blender=regular_file(Path(runner.blender_exe),Path(runner.blender_exe).parent,512*1024*1024)
    dependencies={worker,blender,*worker_dependency_files(worker)}
    # This package is an explicit application source root, not disk/model discovery.
    package=Path(__file__).resolve().parents[1];dependencies.update(package.rglob('*.py'))
    for path in tuple(watched):
        root=next((r for r in roots if path.is_relative_to(r)),None)
        if root is None:raise ProjectStorageError('Native original input escaped its selected directory')
        for parent in path.parents:
            if not parent.is_relative_to(root):break
            watched.add(parent)
            if parent==root:break
    watched.update(dependencies);identities={path:identity(path) for path in watched}
    hashes={path:_digest(path,cancel) for path in watched if path.is_file()}
    def unchanged() -> None:
        check();current=store.load()
        if current.project_id!=project.project_id or current.revision!=project.revision or _digest(store.file,cancel)!=project_sha:
            raise ProjectConflict('Saved character changed during native runtime production')
        for path,before in identities.items():
            if path.is_symlink() or not path.exists() or identity(path)!=before:
                raise ProjectStorageError('Native producer input/dependency identity changed')
        for path,sha in hashes.items():
            check()
            if _digest(path,cancel)!=sha:raise ProjectStorageError('Native producer input/dependency content changed')
        for name,path in sources.items():
            if name not in {'master',motion_asset_id}:
                rights=read_json(path,4*1024*1024).get('rights',{})
                permission=next(p for p in permissions if p.asset_id==name)
                if rights.get('no_ai') and (not permission.policy.no_ai or permission.policy.ai_input_allowed):
                    raise ValidationError('Native production cannot remove registered NoAI restrictions')
        build_native_recipe(current,project_sha,bindings,evidence_bindings,code_hashes,permissions,motion_asset_id,capability)
    unchanged()
    return {'project':project,'project_sha':project_sha,'sources':sources,'evidence':evidence,
        'bindings':bindings,'evidence_bindings':evidence_bindings,'implementation':implementation,
        'recipe':recipe,'unchanged':unchanged,'source':source}
