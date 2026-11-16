"""Build a new isolated first-party worker data payload; never install or fetch.

Python sources are chosen by bounded AST import closure, not by executing them.
All non-stdlib imports in that closure fail the build. Generated data is private
internal QA material until distribution/license review is complete.
"""
import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def build_payload(repo: Path, destination: Path) -> dict:
    repo = Path(repo); destination = Path(destination)
    if (repo.resolve() != repo or not (repo / 'src/ucc').is_dir()
            or destination.exists() or destination.is_symlink() or destination.parent.resolve() != destination.parent
            or not destination.parent.is_dir()):
        raise ValueError('Payload needs a canonical checkout and a new destination in an existing directory')
    src = repo / 'src'; bridge = repo / 'blender_bridge'
    def module_path(name: str) -> Path | None:
        if name != 'ucc' and not name.startswith('ucc.'): return None
        stem = src.joinpath(*name.split('.'))
        for path in (stem.with_suffix('.py'), stem / '__init__.py'):
            if path.is_file(): return path
        return None
    def imports(path: Path, module: str | None = None) -> set[str]:
        names = set()
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if module is None: continue
                    package = module.split('.') if path.name == '__init__.py' else module.split('.')[:-1]
                    parent = package[:len(package) - node.level + 1]
                    name = '.'.join(parent + ([node.module] if node.module else []))
                else: name = node.module or ''
                imported = [name]
                imported += [name + '.' + alias.name for alias in node.names if module_path(name + '.' + alias.name)]
            else: continue
            for name in imported:
                if module_path(name): names.add(name)
                elif module is not None and name.split('.')[0] not in sys.stdlib_module_names:
                    raise ValueError('Worker contract closure has a missing/non-stdlib dependency: ' + name)
        return names
    sources = {str(p.relative_to(repo)).replace('\\', '/'): p for p in bridge.glob('*.py')}
    queue = {'ucc.core.worker_payload'}
    for path in sources.values(): queue.update(imports(path))
    modules = set()
    while queue:
        module = queue.pop()
        if module in modules: continue
        modules.add(module); path = module_path(module)
        if path is None: raise ValueError('Missing pure worker contract module')
        sources['worker_support/' + str(path.relative_to(src)).replace('\\', '/')] = path
        queue.update(imports(path, module))
        pieces = module.split('.')
        queue.update('.'.join(pieces[:index]) for index in range(1, len(pieces)))
    for name in ('validate.gd', 'configure.gd', 'clay.gdshader', 'project.godot'):
        sources['worker_support/adapters/godot/native_runtime/' + name] = repo / 'engine_adapters/godot/native_runtime' / name
    for name in ('configure.gd', 'inspect.gd', 'export.gd'):
        sources['worker_support/adapters/godot/static_export/' + name] = repo / 'engine_adapters/godot/static_export' / name
    sources['worker_support/adapters/godot/static_export/ucc_skin_adapter.gd'] = repo / 'engine_adapters/godot/ucc_skin_adapter.gd'
    from ucc.core.worker_payload import UNITY_ADAPTER,UNITY_ADAPTER_FILES
    for name in UNITY_ADAPTER_FILES:
        sources[UNITY_ADAPTER+'/'+name] = repo/'engine_adapters/unity'/name
    from ucc.core.worker_payload import UNREAL_ADAPTER,UNREAL_ADAPTER_FILES
    for name in UNREAL_ADAPTER_FILES:
        sources[UNREAL_ADAPTER+'/'+name] = repo/'engine_adapters/unreal'/name
    sources['blender_bridge/payload_contract.py'] = src / 'ucc/core/worker_payload.py'
    snapshots = {}
    for relative, path in sources.items():
        if path.is_symlink() or path.resolve() != path or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Worker payload source missing, redirected or oversized')
        snapshots[relative] = {'sha256': sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
    temporary = Path(tempfile.mkdtemp(prefix='ucc-payload-', dir=destination.parent))
    try:
        for relative, path in sources.items():
            target = temporary / relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if sha256(target.read_bytes()).hexdigest() != snapshots[relative]['sha256']:
                raise ValueError('Worker source changed during payload staging')
        manifest = {'schema_version': 1, 'policy': 'UCC_WORKER_PAYLOAD_V1', 'files': snapshots,
            'modules': sorted(modules), 'engine_import_verified': False, 'distribution_license_review_complete': False}
        (temporary / 'worker_support/payload.v1.json').write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
        for relative, path in sources.items():
            if path.is_symlink() or path.resolve() != path or sha256(path.read_bytes()).hexdigest() != snapshots[relative]['sha256']:
                raise ValueError('Worker source changed before payload promotion')
        if destination.exists() or destination.is_symlink(): raise ValueError('Payload destination appeared during build')
        os.rename(temporary, destination)
        return manifest
    finally:
        if temporary.exists():
            if temporary.resolve().parent != destination.parent or not temporary.name.startswith('ucc-payload-'):
                raise ValueError('Unsafe payload staging cleanup path')
            shutil.rmtree(temporary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    result = build_payload(args.repo, args.destination)
    print('WORKER_PAYLOAD_BUILT', len(result['modules']), 'modules', len(result['files']), 'files')
