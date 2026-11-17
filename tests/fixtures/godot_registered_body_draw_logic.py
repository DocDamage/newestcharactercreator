"""NONSHIPPING synthetic buffers/PNG only; no model, Godot or raster proof."""
from hashlib import sha256
import json
import struct
import zlib
from ucc.export.godot_registered_body_runtime import FALSE_FLAGS


def png(*, blank=False, clipped=False):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = []
    for y in range(512):
        row = bytearray(512 * 4)
        for x in range(0 if clipped else 200, 16 if clipped else 216):
            if not blank and 200 <= y < 216:
                row[x*4:x*4+4] = bytes([50 + (y-200)*5, 60, 70, 255])
        rows.append(b'\0' + row)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',512,512,8,6,0,0,0))
            + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND',b''))


def write_measurement(folder, report):
    (folder/'measurement.json').write_text(json.dumps(report), encoding='utf-8')


def synthetic_draw_outputs(folder):
    # Full declared lengths exercise bounds, but values are invented test-only data.
    positions = struct.pack('<3f', 0.1, 0.2, 0.3) * 14517
    normals = struct.pack('<3f', 0., 1., 0.) * 14517
    uv = struct.pack('<2f', 0.2, 0.8) * 14517
    triangles = struct.pack('<' + 'I' * (26756*3), *[i % 14517 for i in range(26756*3)])
    staged = {'imported_uv.f32':uv, 'imported_uv_triangles.u32':triangles}
    frames=[]
    for frame in (1,150,300):
        staged[f'frame{frame:03d}_positions.f32']=positions
        staged[f'frame{frame:03d}_normals.f32']=normals
        outputs={f'frame{frame:03d}_draw_positions.f32':positions,
                 f'frame{frame:03d}_draw_normals.f32':normals,
                 f'frame{frame:03d}_draw_uv.f32':uv,
                 f'frame{frame:03d}_draw_triangles.u32':triangles,
                 f'frame{frame:03d}.png':png()}
        for name, raw in outputs.items():(folder/name).write_bytes(raw)
        frames.append({'frame':frame,'mesh_visible':True,'camera_current':True,
                       'files':{name:{'sha256':sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in outputs.items()}})
    for name,raw in staged.items():(folder/name).write_bytes(raw)
    spec=b'{"synthetic_nonshipping":true}';(folder/'spec.json').write_bytes(spec)
    spec_sha=sha256(spec).hexdigest()
    report=dict(schema_version=1,status='REGISTERED_BODY300_DEBUG_DRAW_VERIFIED',spec_sha256=spec_sha,
                godot_version={'major':4,'minor':7,'patch':1},rendering_device='SYNTHETIC_NOT_AN_ENGINE',frames=frames,
                **{name:False for name in FALSE_FLAGS})
    write_measurement(folder,report)
    return spec_sha,{name:sha256(raw).hexdigest() for name,raw in staged.items()},report
