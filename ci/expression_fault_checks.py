"""Actual scene/Action faults and coherently rehashed sub-micron cache corruption."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import zlib

from ucc.core.errors import ValidationError
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner, WorkerFailure
from ucc.preview.expression_cache import read_expression_cache


def require(condition, message):
    if not condition: raise RuntimeError(message)


def digest(path): return sha256(path.read_bytes()).hexdigest()


def verify_faults(blender: Path, worker: Path, preview, out: Path) -> dict:
    out.mkdir(exist_ok=False); stage = preview.workdir; bound = preview.bindings
    protected = {str(p): digest(p) for p in stage.iterdir() if p.is_file()}
    fixture = Path(__file__).resolve().parents[1]/'tests/fixtures/blender_expression_clip_faults.py'
    with (out/'mutation.log').open('x', encoding='utf-8') as log:
        result = subprocess.run([str(blender), '--background', '--disable-autoexec', '--python-exit-code', '13',
            '--python', str(fixture), '--', str(stage/'expression_motion.blend'), str(out/'scenes')],
            stdout=log, stderr=subprocess.STDOUT, timeout=180)
    require(result.returncode == 0, 'Real expression corruption fixture failed')
    staged = {name: stage/name for name in ('candidate.blend', 'expression_clip.json', 'expression_motion.blend',
        'expression_motion.json', 'expression_skin.bin', 'expression_skin.json')}
    staged.update({p.name: p for p in stage.glob('expr-*.target.gz')})
    runner = BlenderJobRunner(blender, out/'jobs', worker); rejected = {}
    faults = json.loads((out/'scenes/faults.json').read_text())
    expected = {'peak-ulp', 'key-time', 'interpolation', 'extra-channel', 'influence', 'key-coordinate-ulp',
                'rest-roll', 'uv', 'material', 'material-driver', 'fps', 'extra-action'}
    require(set(faults) == expected and len(faults) == 12, 'Expression scene fault coverage differs')
    for fault in faults:
        scene = out/'scenes'/(fault+'.blend')
        report = json.loads((stage/'expression_motion.json').read_text()); report['motion_sha256'] = digest(scene)
        report_path = out/(fault+'-report.json'); report_path.write_text(json.dumps(report), encoding='utf-8')
        manifest = json.loads((stage/'expression_skin.json').read_text())
        manifest['bindings'].update(motion_sha256=digest(scene), motion_report_sha256=digest(report_path))
        manifest_path = out/(fault+'-cache.json'); manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        options = dict(bound, motion_sha256=digest(scene), motion_report_sha256=digest(report_path),
                       cache_manifest_sha256=digest(manifest_path))
        try:
            runner.run(JobRequest.new('verify_mpfb_expression_clip', input_project='candidate.blend', options=options),
                staged_inputs={**staged, 'expression_motion.blend': scene, 'expression_motion.json': report_path,
                               'expression_skin.json': manifest_path}, timeout_s=300)
        except WorkerFailure as error:
            require(any(text in str(error) for text in ('Saved expression', 'Prepared expression', 'Expression Action')),
                    'Expression fault failed for an unrelated reason')
            rejected[fault] = {'semantic_rejection': True, 'scene_report_and_cache_manifest_rehashed': True}
        else: raise RuntimeError('Accepted real rehashed expression scene fault: '+fault)
        print('REAL_REHASHED_EXPRESSION_FAULT_REJECTED', fault, flush=True)
    folder = out/'cache-ulp'; folder.mkdir()
    manifest = json.loads((stage/'expression_skin.json').read_text()); binary = (stage/'expression_skin.bin').read_bytes()
    new_binary = bytearray(binary[:8]); changed = False
    for row in manifest['frames']:
        raw = bytearray(zlib.decompress(binary[row['offset']:row['offset']+row['compressed_bytes']]))
        if row['frame'] == 13:
            for offset in range(0, 12*13380, 4):
                before = struct.unpack_from('<f', raw, offset)[0]
                if abs(before) < .001: continue
                bits = struct.unpack_from('<I', raw, offset)[0]
                after = struct.unpack('<f', struct.pack('<I', bits+1))[0]
                if before != after and round(before*1000000) == round(after*1000000):
                    struct.pack_into('<f', raw, offset, after); changed = True; break
            require(changed, 'Failed to author a genuine sub-micron float32 fault')
        packed = zlib.compress(raw, 1)
        row.update(offset=len(new_binary), compressed_bytes=len(packed), raw_sha256=sha256(raw).hexdigest())
        new_binary.extend(packed)
    binary_path = folder/'expression_skin.bin'; binary_path.write_bytes(new_binary)
    manifest['geometry'].update(bytes=len(new_binary), sha256=digest(binary_path))
    manifest_path = folder/'expression_skin.json'; manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    options = dict(bound, cache_sha256=digest(binary_path), cache_manifest_sha256=digest(manifest_path))
    try:
        runner.run(JobRequest.new('verify_mpfb_expression_clip', input_project='candidate.blend', options=options),
            staged_inputs={**staged, 'expression_skin.bin': binary_path, 'expression_skin.json': manifest_path}, timeout_s=300)
    except WorkerFailure as error:
        require('Saved expression frame/cache differs' in str(error), 'Cache ULP failed for an unrelated reason')
        rejected['coherently-rehashed-cache-float32-ulp'] = {'semantic_rejection': True, 'all_binary_records_rehashed': True}
    else: raise RuntimeError('Accepted rehashed one-ULP expression cache fault')
    proof = deepcopy(preview.observed); proof['bindings'] = options
    report = json.loads((stage/'expression_motion.json').read_text())
    try: read_expression_cache(folder, options, proof, report)
    except ValidationError as error:
        require('exact independent saved surface' in str(error), 'Host exact-coordinate rejection failed for another reason')
    else: raise RuntimeError('Host accepted forged success assertion and sub-micron cache corruption')
    require(len(rejected) == 13 and protected == {p: digest(Path(p)) for p in protected},
            'Expression negative gate changed accepted input or omitted a fault')
    return {'rehashed_faults': rejected, 'host_rejected_exact_ulp_with_forged_success_assertion': True,
            'accepted_inputs_unchanged': True}
