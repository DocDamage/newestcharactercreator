"""Bounded immutable body readback mapping; no renderer or appearance acceptance."""
from math import isfinite
from pathlib import Path
import struct
from typing import Callable

from ucc.core.errors import ValidationError
from .target_action_context import Budget

SOURCE_VERTICES = 13380
IMPORTED_VERTICES = 14517
TRIANGLES = 26756


def map_frame(position_bytes: bytes, normal_bytes: bytes, ids_bytes: bytes,
              uv_bytes: bytes, triangles_bytes: bytes, *,
              source_vertices: int = SOURCE_VERTICES,
              imported_vertices: int = IMPORTED_VERTICES,
              check: Callable[[], None] | None = None) -> dict[str, bytes]:
    """Map sealed C vec4 readbacks to unskinned Godot vec3 surface buffers.

    C stores world (x, -z, y); its inverse is (x, z, -y). UV-seam vertices
    retain distinct UVs/indices while sharing source positions and normals.
    Smaller explicit dimensions are permitted solely for isolated logic tests.
    All inputs must be captured immutable bytes; no path is reopened here.
    """
    if (type(source_vertices) is not int or type(imported_vertices) is not int
            or not 1 <= source_vertices <= SOURCE_VERTICES
            or not source_vertices <= imported_vertices <= IMPORTED_VERTICES
            or (source_vertices == SOURCE_VERTICES or imported_vertices == IMPORTED_VERTICES)
            and (source_vertices, imported_vertices) != (SOURCE_VERTICES, IMPORTED_VERTICES)):
        raise ValidationError("Unsupported draw source/imported vertex profile")
    buffers = (position_bytes, normal_bytes, ids_bytes, uv_bytes, triangles_bytes)
    if any(type(value) is not bytes for value in buffers):
        raise ValidationError("Draw mapping requires immutable captured bytes")
    if (len(position_bytes) != source_vertices * 16
            or len(normal_bytes) != source_vertices * 16
            or len(ids_bytes) != imported_vertices * 4
            or len(uv_bytes) != imported_vertices * 8
            or not 0 < len(triangles_bytes) <= TRIANGLES * 12
            or len(triangles_bytes) % 12
            or source_vertices == SOURCE_VERTICES and len(triangles_bytes) != TRIANGLES * 12):
        raise ValidationError("Draw source array byte lengths differ")
    def checkpoint(index: int) -> None:
        if check is not None and index % 256 == 0:
            check()
    positions = []
    normals = []
    for index, (point, normal) in enumerate(zip(struct.iter_unpack('<4f', position_bytes),
                                               struct.iter_unpack('<4f', normal_bytes))):
        checkpoint(index)
        if (not all(isfinite(value) for value in point + normal)
                or point[3] != 1.0 or normal[3] != 0.0
                or abs(sum(value * value for value in normal[:3]) - 1.0) > 2e-5):
            raise ValidationError("Draw source position/normal is malformed")
        positions.append((point[0], point[2], -point[1]))
        normals.append((normal[0], normal[2], -normal[1]))
    ids = [row[0] for row in struct.iter_unpack('<I', ids_bytes)]
    if any(value >= source_vertices for value in ids) or set(ids) != set(range(source_vertices)):
        raise ValidationError("Draw source identity coverage differs")
    for index, row in enumerate(struct.iter_unpack('<2f', uv_bytes)):
        checkpoint(index)
        if not all(isfinite(value) for value in row):
            raise ValidationError("Draw UV contains a nonfinite value")
    indices = [row[0] for row in struct.iter_unpack('<I', triangles_bytes)]
    if any(value >= imported_vertices for value in indices) or set(indices) != set(range(imported_vertices)):
        raise ValidationError("Draw index topology is incomplete or out of bounds")
    mapped_positions = bytearray(imported_vertices * 12)
    mapped_normals = bytearray(imported_vertices * 12)
    for index, source in enumerate(ids):
        checkpoint(index)
        struct.pack_into('<3f', mapped_positions, index * 12, *positions[source])
        struct.pack_into('<3f', mapped_normals, index * 12, *normals[source])
    if check is not None:
        check()
    return dict(positions=bytes(mapped_positions), normals=bytes(mapped_normals),
                uv=uv_bytes, triangles=triangles_bytes)


DRAW_FRAMES = (1, 150, 300)
STATUS = "REGISTERED_BODY300_DEBUG_DRAW_VERIFIED"
NORMAL_READBACK_POLICY = "GODOT_4_7_1_OCTAHEDRAL_NORMAL_VECTOR_0_0002_V1"
MAX_NORMAL_VECTOR_ERROR = 0.0002


def verify_draw_outputs(folder: Path, spec_sha256: str, expected_input_hashes: dict[str, str],
                        budget: Budget) -> dict:
    """Verify captured assigned arrays and bounded private raster proof, not beauty.

    Input and output comparisons use the very bytes whose SHA was admitted.
    Final path/identity checks fence later substitutions across the read set.
    The caller retains its owned namespace/source guard through receipt commit.
    """
    from ucc.core.errors import ProjectStorageError
    from ucc.core.target_action_format import checked_sha
    from ucc.export.godot_registered_body_runtime import FALSE_FLAGS
    from ucc.export.godot_candidate_contract import canonical_bytes
    from .godot_candidate_inputs import identity
    from .godot_registered_runtime_files import read_bytes, hash_file
    from .private_render_evidence import png_measurements
    from .target_action_context import protected

    folder = protected(Path(folder))
    root_identity = identity(folder)
    checked_sha(spec_sha256)
    lengths = {"positions": IMPORTED_VERTICES * 12, "normals": IMPORTED_VERTICES * 12,
               "uv": IMPORTED_VERTICES * 8, "triangles": TRIANGLES * 12}
    inputs = {f"frame{frame:03d}_{kind}.f32": lengths[kind]
              for frame in DRAW_FRAMES for kind in ("positions", "normals")}
    inputs.update({"imported_uv.f32": lengths['uv'], "imported_uv_triangles.u32": lengths['triangles']})
    if type(expected_input_hashes) is not dict or set(expected_input_hashes) != set(inputs):
        raise ValidationError("Draw staged input closure differs")
    for value in expected_input_hashes.values():
        checked_sha(value)
    captured = {}
    seals = {}
    def capture(name, maximum, expected=None):
        path = folder / name
        stamp = identity(protected(path))
        if path.stat().st_nlink != 1:
            raise ProjectStorageError("Draw evidence must be an owned single-link file")
        raw, digest = read_bytes(path, maximum, budget, expected_sha256=expected)
        if identity(protected(path)) != stamp:
            raise ProjectStorageError("Draw evidence identity changed while captured")
        seals[name] = (stamp, digest, len(raw))
        return raw
    capture('spec.json', 256 * 1024, spec_sha256)
    for name, size in inputs.items():
        raw = capture(name, size, expected_input_hashes[name])
        if len(raw) != size:
            raise ValidationError("Draw staged buffer length differs")
        captured[name] = raw
    for frame in DRAW_FRAMES:
        for kind in ('positions', 'normals'):
            for index, row in enumerate(struct.iter_unpack('<3f', captured[f'frame{frame:03d}_{kind}.f32'])):
                if index % 256 == 0:
                    budget.check()
                if (not all(isfinite(value) for value in row)
                        or kind == 'normals' and abs(sum(value * value for value in row) - 1) > 2e-5):
                    raise ValidationError("Invalid staged draw vector")
    if any(not all(isfinite(value) for value in row)
           for row in struct.iter_unpack('<2f', captured['imported_uv.f32'])):
        raise ValidationError("Invalid staged draw UV")
    indices = [row[0] for row in struct.iter_unpack('<I', captured['imported_uv_triangles.u32'])]
    if any(value >= IMPORTED_VERTICES for value in indices) or set(indices) != set(range(IMPORTED_VERTICES)):
        raise ValidationError("Invalid staged draw triangle coverage")
    report_raw = capture('measurement.json', 256 * 1024)
    # Parse exactly the captured bytes through the shared strict JSON decoder.
    # read_metadata would reopen; decode the retained buffer directly instead.
    import json
    from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
    try:
        report = json.loads(report_raw.decode('utf-8'), object_pairs_hook=_unique_project_fields,
                            parse_constant=_nonfinite_project_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("Malformed draw measurement JSON") from error
    canonical_bytes(report)
    keys = {'schema_version', 'status', 'spec_sha256', 'godot_version', 'rendering_device', 'frames'} | FALSE_FLAGS
    if (type(report) is not dict or set(report) != keys or type(report['schema_version']) is not int
            or report['schema_version'] != 1 or report['status'] != STATUS
            or report['spec_sha256'] != spec_sha256 or any(report[name] is not False for name in FALSE_FLAGS)
            or type(report['frames']) is not list or len(report['frames']) != len(DRAW_FRAMES)
            or type(report['rendering_device']) is not str or not report['rendering_device'].strip()
            or len(report['rendering_device']) > 256):
        raise ValidationError("Incomplete closed draw measurement")
    version = report['godot_version']
    if type(version) is not dict or any(type(version.get(key)) is not int or version[key] != value
                                       for key, value in [('major', 4), ('minor', 7), ('patch', 1)]):
        raise ValidationError("Unsupported actual draw Godot version")
    files = {}
    observations = []
    for frame, row in zip(DRAW_FRAMES, report['frames']):
        budget.check()
        if (type(row) is not dict or set(row) != {'frame', 'files', 'mesh_visible', 'camera_current'}
                or type(row['frame']) is not int or row['frame'] != frame
                or row['mesh_visible'] is not True or row['camera_current'] is not True
                or type(row['files']) is not dict):
            raise ValidationError("Incomplete visible draw frame evidence")
        names = {f'frame{frame:03d}_draw_{kind}.{suffix}': kind
                 for kind, suffix in [('positions', 'f32'), ('normals', 'f32'), ('uv', 'f32'), ('triangles', 'u32')]}
        png = f'frame{frame:03d}.png'
        if set(row['files']) != set(names) | {png}:
            raise ValidationError("Draw output file closure differs")
        image_observed = None
        max_normal_vector_error = 0.0
        for name in [*names, png]:
            record = row['files'][name]
            maximum = 2 * 1024 * 1024 if name == png else lengths[names[name]]
            if (type(record) is not dict or set(record) != {'sha256', 'bytes'}
                    or type(record['bytes']) is not int or not 0 < record['bytes'] <= maximum):
                raise ValidationError("Invalid draw output record")
            checked_sha(record['sha256'])
            raw = capture(name, maximum, record['sha256'])
            if len(raw) != record['bytes']:
                raise ValidationError("Draw output record byte count differs")
            if name == png:
                image_observed = png_measurements(raw, include_pixel_hash=True, expected_size=(512, 512))
            else:
                kind = names[name]
                staged = (f'frame{frame:03d}_{kind}.f32' if kind in {'positions', 'normals'}
                          else 'imported_uv.f32' if kind == 'uv' else 'imported_uv_triangles.u32')
                if kind == 'normals':
                    if len(raw) != lengths['normals']:
                        raise ValidationError("Actual assigned draw normal length differs")
                    for index, (actual, expected) in enumerate(zip(struct.iter_unpack('<3f',raw),
                                                                   struct.iter_unpack('<3f',captured[staged]))):
                        if index % 256 == 0:
                            budget.check()
                        error = sum((a-b)**2 for a,b in zip(actual,expected))**0.5
                        if (not all(isfinite(value) for value in actual)
                                or abs(sum(value*value for value in actual)-1)>2e-5
                                or not isfinite(error) or error>MAX_NORMAL_VECTOR_ERROR):
                            raise ValidationError("Actual assigned draw normals exceed engine format bound")
                        max_normal_vector_error = max(max_normal_vector_error,error)
                elif raw != captured[staged]:
                    raise ValidationError("Actual assigned draw arrays differ from staged mapped input")
            files[name] = dict(sha256=record['sha256'], bytes=len(raw))
        observations.append(dict(frame=frame, normal_readback_policy=NORMAL_READBACK_POLICY,
                                 max_normal_vector_error=max_normal_vector_error, **image_observed))
    for name, (stamp, digest, size) in seals.items():
        budget.check()
        if ((folder / name).stat().st_nlink != 1 or identity(protected(folder / name)) != stamp
                or hash_file(folder / name, size, budget) != (digest, size)):
            raise ProjectStorageError("Draw evidence changed after capture")
    if identity(protected(folder)) != root_identity:
        raise ProjectStorageError("Draw evidence directory changed")
    return dict(status=STATUS, measurement_sha256=seals['measurement.json'][1], files=files,
                observations=observations, **{name: False for name in FALSE_FLAGS})



def read_frame_stream(path: Path, expected_sha256: str, budget: Budget, *,
                      selected: tuple[int, ...] = DRAW_FRAMES,
                      frames: int = 300, vertices: int = SOURCE_VERTICES) -> dict[int, bytes]:
    """Hash one complete captured stream while retaining only selected frames.

    Smaller explicit dimensions are isolated synthetic-test support. Hashing
    must cover the SAME bytes used for mapping, not a separate path sample.
    """
    from hashlib import sha256
    import os
    import stat
    from ucc.core.errors import ProjectStorageError
    from ucc.core.target_action_format import checked_sha
    from .target_action_context import protected
    checked_sha(expected_sha256)
    if (type(frames) is not int or not 1 <= frames <= 300
            or type(vertices) is not int or not 1 <= vertices <= SOURCE_VERTICES
            or type(selected) is not tuple or not 1 <= len(selected) <= 3
            or any(type(frame) is not int or not 1 <= frame <= frames for frame in selected)
            or len(set(selected)) != len(selected)):
        raise ValidationError("Unsupported bounded draw frame stream profile")
    budget.check()
    path = protected(Path(path))
    def stamp(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
                value.st_nlink)
    before = path.stat()
    frame_bytes = vertices * 16
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_size != frames * frame_bytes):
        raise ProjectStorageError("Diagnostic frame stream length or ownership differs")
    digest = sha256()
    captured = {}
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if stamp(opened) != stamp(before):
            raise ProjectStorageError("Diagnostic frame stream replaced before read")
        for frame in range(1, frames + 1):
            budget.check()
            raw = stream.read(frame_bytes)
            if len(raw) != frame_bytes:
                raise ProjectStorageError("Diagnostic frame stream is truncated")
            digest.update(raw)
            if frame in selected:
                captured[frame] = raw
        if stream.read(1):
            raise ProjectStorageError("Diagnostic frame stream has trailing bytes")
        finished = os.fstat(stream.fileno())
    after = protected(path).stat()
    budget.check()
    if (stamp(before) != stamp(opened) or stamp(opened) != stamp(finished)
            or stamp(finished) != stamp(after) or before.st_ctime_ns != after.st_ctime_ns
            or opened.st_ctime_ns != finished.st_ctime_ns or digest.hexdigest() != expected_sha256):
        raise ProjectStorageError("Captured diagnostic frame stream differs from selected SHA/identity")
    return captured
