"""Selected Blender 5.3 FBX helper closure; hashes only, no vendor redistribution."""
from pathlib import Path
import sys

from ucc.core.errors import ProjectStorageError
from .export_guards import bounded_paths
from .godot_candidate_inputs import identity
from .master_preview import _digest
from .target_action_context import protected


def blender_helper_resources(executable: Path, budget):
    scripts = protected(executable.parent/'5.3/scripts')
    package = protected(scripts/'addons_core/io_scene_fbx')
    if not package.is_dir():
        raise ProjectStorageError('Selected Blender 5.3 FBX helper package is missing; select its complete installed layout')
    files = {}
    for path in bounded_paths(package, budget.cancel, maximum_entries=1024):
        if path.is_file():
            files['installed_blender/io_scene_fbx/'+path.relative_to(package).as_posix()] = path
    for name in ('__init__.py', 'import_fbx.py', 'export_fbx_bin.py', 'fbx_utils.py', 'parse_fbx.py'):
        if 'installed_blender/io_scene_fbx/'+name not in files:
            raise ProjectStorageError('Selected Blender FBX helper source is incomplete: '+name)
    extras = protected(scripts/'modules/bpy_extras')
    for path in bounded_paths(extras, budget.cancel, maximum_entries=1024):
        if path.is_file():
            files['installed_blender/bpy_extras/'+path.relative_to(extras).as_posix()] = path
    for name in ('__init__.py', 'anim_utils.py', 'io_utils.py', 'node_shader_utils.py', 'image_utils.py'):
        path = protected(extras/name)
        if not path.is_file():
            raise ProjectStorageError('Selected Blender FBX auxiliary helper is missing: '+name)
    rna = protected(scripts/'modules/rna_prop_ui.py')
    if not rna.is_file():
        raise ProjectStorageError('Selected Blender animation RNA helper is missing: rna_prop_ui.py')
    files['installed_blender/rna_prop_ui.py'] = rna
    bytecode = scripts/'modules/__pycache__'
    if bytecode.exists():
        for path in bounded_paths(bytecode, budget.cancel, maximum_entries=1024):
            if path.is_file() and path.name.startswith('rna_prop_ui.'):
                files['installed_blender/__pycache__/'+path.name] = path
    return files


def blender_helper_inventory(executable: Path, budget):
    """Include empty/missing directories, not merely selected file contents."""
    files = blender_helper_resources(executable, budget)
    result = {str(path):(identity(path), _digest(path, budget.cancel)) for path in files.values()}
    scripts = executable.parent/'5.3/scripts'
    for root in (scripts/'addons_core/io_scene_fbx', scripts/'modules/bpy_extras',
                 scripts/'modules/__pycache__'):
        for path in bounded_paths(root, budget.cancel, maximum_entries=1024):
            if path.is_dir(): result[str(path)] = identity(path)
            elif not path.exists(): result[str(path)] = None
    return result


def host_code_snapshot(budget):
    """Seal the running interpreter and bounded first-party code namespace.

    Frozen application code is embedded in the executable's PYZ. Any external
    first-party source/bytecode namespace is also sealed, including its absence.
    No installed stdlib, site-packages or vendor source is copied or scanned.
    """
    root = protected(Path(__file__).absolute().parents[1])
    executable = protected(Path(sys.executable).absolute())
    result = {'host_executable':(identity(executable), _digest(executable, budget.cancel))}
    for label, selected in (('source',root),('executable',executable)):
        for index,parent in enumerate(selected.parents):
            result[f'ancestor/{label}/{index}'] = identity(protected(parent))
    for path in bounded_paths(root, budget.cancel, maximum_entries=4096):
        budget.check()
        name = 'ucc/'+path.relative_to(root).as_posix()
        if not path.exists(): result[name] = None
        elif path.is_dir(): result[name+'/'] = identity(path)
        elif path.suffix in ('.py', '.pyc', '.pyo', '.pyz'):
            result[name] = (identity(path), _digest(path, budget.cancel))
        else:
            result[name] = identity(path)
    # PyInstaller may expose an external archive; an embedded archive's filename
    # is the executable already sealed above. Bind actual loader archives only.
    archives = set()
    for module in tuple(sys.modules.values()):
        if not getattr(module, '__name__', '').startswith('ucc'): continue
        archive = getattr(getattr(module, '__loader__', None), '_pyz_archive', None)
        filename = getattr(archive, '_filename', None)
        if filename and filename not in archives:
            archives.add(filename)
            path = Path(filename).absolute()
            if path.is_file():
                protected(path)
                result['archive:'+path.name] = (identity(path), _digest(path, budget.cancel))
    return result


def worker_namespace_snapshot(worker, budget):
    """Bind complete bridge/support trees, including cache insertion and absence."""
    result = {}; counter = [0]
    for root in (worker.parent, worker.parent.parent/'worker_support'):
        protected(root)
        for index,parent in enumerate(root.parents):
            result[root.name+'/ancestor/'+str(index)] = identity(protected(parent))
        for path in bounded_paths(root, budget.cancel, counter=counter, maximum_entries=4096):
            budget.check()
            name = root.name+'/'+path.relative_to(root).as_posix()
            if not path.exists(): result[name] = None
            elif path.is_dir(): result[name+'/'] = identity(path)
            else: result[name] = (identity(path), _digest(path, budget.cancel))
    return result
