"""NONSHIPPING synthetic PNGs only; no project, asset, raster or Godot proof."""
from hashlib import sha256
from pathlib import Path
import struct
import zlib

from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.export.godot_saved_preview import CapturedPreviewFrame, LoadedSavedGodotPreview, SelectedProofFile


def synthetic_frame(frame: int) -> CapturedPreviewFrame:
    pixel = bytes((frame % 255, 75, 120, 255))
    rgba = pixel * (512 * 512)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',512,512,8,6,0,0,0))
           + chunk(b'IDAT',zlib.compress(b''.join(b'\0'+pixel*512 for _ in range(512)))) + chunk(b'IEND',b''))
    return CapturedPreviewFrame(frame,png,sha256(rgba).hexdigest(),512*512,(0,0,511,511),0.0001)


def synthetic_loaded() -> LoadedSavedGodotPreview:
    def never_guard(**_):
        raise AssertionError('Widget must never run the background guard')
    selection=RegisteredInputSelection('NONSHIPPING_TEST_PROJECT',1,*(['a'*64]*2),'TEST_CLIP',*(['b'*64]*3))
    proof=SelectedProofFile(Path.cwd()/'nonexistent-synthetic-proof.json','c'*64)
    return LoadedSavedGodotPreview('NONSHIPPING_TEST_DRAW',selection,proof,proof,proof,
        tuple(synthetic_frame(n) for n in (1,150,300)),Path.cwd()/'nonexistent-synthetic.sqlite3',(),(),never_guard)
