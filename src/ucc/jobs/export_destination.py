"""New-folder publication with canonical parent checks and no replacement."""
from dataclasses import dataclass
from pathlib import Path
import ctypes,os,tempfile
from ucc.core.errors import ProjectStorageError,ValidationError
from .godot_candidate_inputs import identity


def rename_new(source: Path,destination: Path) -> None:
    """Atomic exclusive rename; never replace even an empty raced-in folder."""
    if os.name=='nt':os.rename(source,destination);return
    library=ctypes.CDLL(None,use_errno=True)
    function=getattr(library,'renameat2',None)
    if function is None:raise ProjectStorageError('This platform has no supported atomic no-replace directory publication')
    function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];function.restype=ctypes.c_int
    if function(-100,os.fsencode(source),-100,os.fsencode(destination),1)!=0:
        code=ctypes.get_errno();raise OSError(code,os.strerror(code),str(destination))


@dataclass(frozen=True,slots=True)
class ExportDestination:
    path: Path
    parent_identity: tuple[int,int,int,int]

    def unchanged(self) -> None:
        parent=self.path.parent
        if (parent.is_symlink() or not parent.is_dir() or parent.resolve()!=parent or identity(parent)!=self.parent_identity
                or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (parent,*parent.parents))):
            raise ProjectStorageError('Chosen export parent changed or was redirected')
        if self.path.exists() or self.path.is_symlink():raise ProjectStorageError('Export destination already exists; choose a new folder')

    def stage(self,job_id: str) -> Path:
        self.unchanged()
        path=Path(tempfile.mkdtemp(prefix='.ucc-export-'+job_id+'-',dir=self.path.parent))
        if path.resolve()!=path or not path.is_relative_to(self.path.parent):raise ProjectStorageError('Export staging escaped its parent')
        return path


def plan_destination(path: Path,project_root: Path) -> ExportDestination:
    path=Path(path)
    if (not path.is_absolute() or str(path).startswith(('\\\\?\\','\\\\.\\')) or '..' in path.parts or not path.name or path.name.endswith((' ','.'))
            or any(c in path.name for c in '<>:"/\\|?*') or any(ord(c)<32 for c in path.name)
            or path.name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}):
        raise ValidationError('Choose a valid absolute path for a new export folder')
    parent=path.parent
    if not parent.is_dir() or parent.resolve()!=parent:raise ProjectStorageError('Choose an existing canonical export parent folder')
    for name in ('master','parts','expressions','materials','.ucc-jobs','.ucc-candidates'):
        if path.is_relative_to(project_root/name):raise ValidationError('Export destination cannot be inside editable source or private job folders')
    result=ExportDestination(path,identity(parent));result.unchanged();return result
