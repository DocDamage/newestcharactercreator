"""Non-shipping synthetic pixels solely for bounded PNG/provenance tests."""
import struct
import zlib


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind+payload) & 0xffffffff)


def png(method=0, *, phase=0, blank=False, clipped=False, bomb=False):
    width, height = 256, 384
    rows, previous = [], bytes(width*4)
    for y in range(height):
        row = bytearray(width*4)
        for x in range(width):
            if not blank and (0 if clipped else 25) <= x < 225 and 30 <= y < 350:
                row[x*4:x*4+4] = bytes((40+(x+phase)%140, 70, 90, 255))
        filtered = bytearray(len(row))
        for i, value in enumerate(row):
            left, up, corner = row[i-4] if i >= 4 else 0, previous[i], previous[i-4] if i >= 4 else 0
            if method == 4:
                p = left+up-corner
                distances = (abs(p-left), abs(p-up), abs(p-corner))
                predictor = (left, up, corner)[distances.index(min(distances))]
            else:
                predictor = (0, left, up, (left+up)//2)[method]
            filtered[i] = (value-predictor) & 255
        rows.append(bytes((method,)) + filtered)
        previous = row
    pixels = b"".join(rows) + (b"x"*100000 if bomb else b"")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
