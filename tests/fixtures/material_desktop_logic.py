"""Isolated non-shipping byte fixture; NEVER Blender/model integration evidence."""
from hashlib import sha256


def install_synthetic_desktop_master(store) -> str:
    """Satisfy real storage existence checks in metadata-only unit tests."""
    data=b'BLENDER_UNIT_NOT_REAL_MATERIAL_MODEL'*100
    identity=sha256(data).hexdigest()
    relative='master/versions/'+identity+'.blend'
    (store.root/relative).write_bytes(data)
    return relative
