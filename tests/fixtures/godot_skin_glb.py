"""Tiny synthetic accessor-only unit data; NOT model or engine evidence."""
import json
from pathlib import Path
import struct


def skin_document() -> tuple[dict, bytearray, list]:
    binary = bytearray(); views = []; accessors = []

    def add(rows, fmt, component, kind):
        offset = len(binary)
        for row in rows:
            binary.extend(struct.pack(fmt, *row))
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(binary)-offset})
        accessors.append({'bufferView': len(views)-1, 'componentType': component,
                          'count': len(rows), 'type': kind})
        return len(accessors)-1

    attributes = {
        'TEXCOORD_1': add([(0., 1.), (1/255, 1.), (0., 1.)], '<2f', 5126, 'VEC2'),
        'JOINTS_0': add([(0, 1, 2, 3)]*3, '<4B', 5121, 'VEC4'),
        'JOINTS_1': add([(4, 5, 6, 7)]*3, '<4B', 5121, 'VEC4'),
        'WEIGHTS_0': add([(.125,)*4]*3, '<4f', 5126, 'VEC4'),
        'WEIGHTS_1': add([(.125,)*4]*3, '<4f', 5126, 'VEC4')}
    attributes['POSITION'] = add([(0., 0., 0.), (1., 0., 0.), (0., 0., 0.)], '<3f', 5126, 'VEC3')
    document = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(binary)}],
        'bufferViews': views, 'accessors': accessors,
        'nodes': [{'name': f'bone{i}'} for i in range(8)],
        'skins': [{'joints': list(range(8))}],
        'meshes': [{'primitives': [{'attributes': attributes}]}]}
    original = [[[f'bone{i}', .125] for i in range(8)] for _ in range(2)]
    return document, binary, original


def write_skin(path: Path, document: dict, binary: bytearray, *, json_text: str | None = None) -> None:
    raw = (json.dumps(document) if json_text is None else json_text).encode('utf-8')
    raw += b' '*(-len(raw) % 4)
    payload = bytes(binary)+b'\0'*(-len(binary) % 4)
    body = struct.pack('<I4s', len(raw), b'JSON')+raw+struct.pack('<I4s', len(payload), b'BIN\0')+payload
    path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12+len(body))+body)
