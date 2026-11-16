"""Inspect fixed assets in the single already-enabled MPFB package only."""
import importlib
from pathlib import Path
import tomllib

from blender_bridge.mpfb_service import locate_human_service
from blender_bridge.face_policy import BASE_SHA, RIG_SHA, TARGETS, VERSION, digest


def installed_face_assets() -> dict:
    _, module = locate_human_service()
    package = importlib.import_module(module.removesuffix('.services.humanservice'))
    root = Path(package.__file__).resolve().parent
    if tomllib.loads((root/'blender_manifest.toml').read_text(encoding='utf-8')).get('version') != VERSION:
        raise ValueError('Facial customization requires the existing MPFB 2.0.18 extension')
    data = root/'data'
    assets = {'base': ('3dobjs/base.obj', BASE_SHA), 'rig': ('rigs/standard/rig.default.json', RIG_SHA),
              **{role: ('targets/nose/'+name+'.target.gz', sha) for role, name, sha in TARGETS}}
    for _, (relative, expected) in assets.items():
        path = data/relative
        if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(data.resolve())
                or digest(path) != expected):
            raise ValueError('Installed facial asset is missing, redirected or changed: '+relative)
    return {'schema_version': 1, 'mpfb_version': VERSION, 'data_directory': str(data),
            'asset_sha256': {name: sha for name, (_, sha) in assets.items()},
            'installed_or_downloaded': False}
