"""Read-only exact source list for an explicit per-use desktop engine review."""
from dataclasses import dataclass
from pathlib import Path
from ucc.core.errors import ValidationError,ProjectConflict
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.core.skin_material import APPEARANCE_KEY
from ucc.core.storage import ProjectStore
from .skin_material_storage import registered_material_binding
from .godot_candidate_inputs import project_sources
from .expression_storage import safe_directory
from .master_preview import _digest
from .godot_candidate_inputs import read_json


@dataclass(frozen=True,slots=True)
class ExportSource:
    asset_id: str
    sha256: str
    label: str


@dataclass(frozen=True,slots=True)
class ExportReview:
    project_id: str
    revision: int
    project_sha256: str
    sources: tuple[ExportSource,...]


def static_export_sources(store: ProjectStore,*,project_id: str,revision: int,master_blend: str,cancel=None,purpose: str='Godot export') -> tuple[ExportReview,dict[str,Path],dict]:
    project=store.load()
    if project.project_id!=project_id or project.revision!=revision or project.master_blend!=master_blend:
        raise ProjectConflict('Saved character changed before '+purpose+' review')
    if not supports_material_master_intent(project):
        raise ValidationError(purpose+' currently needs a saved prepared MPFB character with a skin material and no attached animation references')
    binding=registered_material_binding(store,project,cancel)
    recipe=read_json(safe_directory(store,'materials','proofs')/(binding['recipe_sha256']+'.json'),256*1024)['project_snapshot']
    current=project.to_dict()
    if any(current.get(k)!=recipe.get(k) for k in ('parameters','facial_parameters','scale')):
        raise ValidationError('Apply saved body and face changes before exporting this character')
    paths=project_sources(store,project,cancel)
    paths['body_material']=safe_directory(store,'materials','manifests')/(dict(project.appearance)[APPEARANCE_KEY]+'.json')
    labels={'master':'Character master','expression_library':'Prepared facial controls','body_material':'Saved skin material'}
    sources=tuple(ExportSource(name,_digest(path,cancel),labels.get(name,'Compatible left-hand part')) for name,path in sorted(paths.items()))
    return ExportReview(project.project_id,project.revision,_digest(store.file,cancel),sources),paths,binding
