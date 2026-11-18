"""Private registered Unreal Blender source preparation."""
from pathlib import Path
from threading import Event
from typing import Callable

from ucc.core.errors import ValidationError
from ucc.core.storage import ProjectStore
from .registered_animation_source import PreparedRegisteredAnimationSource as PreparedUnrealAnimationSource
from .registered_animation_source import prepare_registered_animation_source
from .unreal_animation_authorization import UnrealAnimationAuthorization


def prepare_unreal_animation_source(store: ProjectStore, *, authorization: UnrealAnimationAuthorization,
        database_path: Path, blender_exe: Path, worker_script: Path, cancel: Event | None = None,
        timeout_s: float = 1800, progress: Callable[[str], None] | None = None) -> PreparedUnrealAnimationSource:
    from ucc.export import unreal_animation_recipe

    if type(authorization) is not UnrealAnimationAuthorization:
        raise ValidationError('Explicit Unreal authority for this saved target is required')
    return prepare_registered_animation_source(store, engine='unreal', recipe=unreal_animation_recipe,
        selection=authorization.selection, permissions=authorization.permissions, database_path=database_path,
        blender_exe=blender_exe, worker_script=worker_script, cancel=cancel, timeout_s=timeout_s, progress=progress)
