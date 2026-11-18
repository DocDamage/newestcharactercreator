"""Private registered Unity Blender source preparation."""
from pathlib import Path
from threading import Event
from typing import Callable

from ucc.core.errors import ValidationError
from ucc.core.storage import ProjectStore
from ucc.export import unity_animation_recipe
from .registered_animation_source import PreparedRegisteredAnimationSource as PreparedUnityAnimationSource
from .registered_animation_source import prepare_registered_animation_source
from .unity_animation_authorization import UnityAnimationAuthorization


def prepare_unity_animation_source(store: ProjectStore, *, authorization: UnityAnimationAuthorization,
        database_path: Path, blender_exe: Path, worker_script: Path, cancel: Event | None = None,
        timeout_s: float = 1800, progress: Callable[[str], None] | None = None) -> PreparedUnityAnimationSource:
    if type(authorization) is not UnityAnimationAuthorization:
        raise ValidationError('Explicit Unity-only authority for the saved target is required')
    return prepare_registered_animation_source(store, engine='unity', recipe=unity_animation_recipe,
        selection=authorization.selection, permissions=authorization.permissions, database_path=database_path,
        blender_exe=blender_exe, worker_script=worker_script, cancel=cancel, timeout_s=timeout_s, progress=progress)
