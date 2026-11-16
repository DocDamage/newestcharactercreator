"""Fresh process: load existing saved packages and capture; no setters or saves."""
import sys
sys.dont_write_bytecode = True
import unreal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_common import identity, capture
control, root, profile = identity('FRESH')
if not unreal.EditorLevelLibrary.load_level('/Game/UCC/CharacterScene'):
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
mesh = unreal.load_asset('/Game/UCC/Character')
if not isinstance(mesh, unreal.SkeletalMesh):
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
capture('FRESH', control, root, profile, mesh)
