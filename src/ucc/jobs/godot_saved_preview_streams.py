"""Captured C stream/source hashing and numerical comparison without producers."""
from contextlib import ExitStack
from hashlib import sha256
import math
import os
from pathlib import Path
import stat
import struct
from ucc.core.errors import ProjectStorageError, ValidationError
from .target_action_context import Budget, protected


NAMES=('actual_corrected_world.f32','expected_vec4.f32',
       'actual_normals_vec4.f32','expected_normals_vec4.f32')


def capture_body_streams(folder:Path, hashes:dict[str,str], references:dict[str,dict], budget:Budget,
                         *,frames:int=300,vertices:int=13380,selected:tuple[int,...]=(1,150,300)) -> tuple[dict,dict]:
    """Hash every captured byte; dehomogenized reference hashes bind producer data.

    Synthetic tests may use smaller explicit dimensions. No original producer
    path or executable is inferred, opened or launched.
    """
    if (type(frames) is not int or not 1<=frames<=300 or type(vertices) is not int
            or not 1<=vertices<=13380 or type(selected) is not tuple or len(selected)>3
            or any(type(n) is not int or not 1<=n<=frames for n in selected)
            or len(set(selected))!=len(selected)):
        raise ValidationError('Unsupported saved body reference dimensions')
    paths=[protected(folder/name) for name in NAMES]
    def stamp(value):return value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_nlink
    before=[path.stat() for path in paths]
    for info in before:
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size!=frames*vertices*16:
            raise ProjectStorageError('Saved body stream length/ownership differs')
    full=[sha256() for _ in paths];original=[sha256(),sha256()]
    captured={NAMES[0]:{},NAMES[2]:{}}
    max_position=0.;max_vector=0.;minimum_cosine=1.
    with ExitStack() as stack:
        streams=[stack.enter_context(path.open('rb')) for path in paths]
        opened=[os.fstat(stream.fileno()) for stream in streams]
        if list(map(stamp,before))!=list(map(stamp,opened)):
            raise ProjectStorageError('Saved body stream changed before capture')
        for frame in range(1,frames+1):
            budget.check();blocks=[stream.read(vertices*16) for stream in streams]
            if any(len(raw)!=vertices*16 for raw in blocks):raise ProjectStorageError('Truncated saved body stream')
            for digest,raw in zip(full,blocks):digest.update(raw)
            if frame in selected:
                for name,index in ((NAMES[0],0),(NAMES[2],2)):captured[name][frame]=blocks[index]
            for index in range(vertices):
                if index%256==0:budget.check()
                rows=[struct.unpack_from('<4f',raw,index*16) for raw in blocks]
                actual,expected,normal,reference=rows
                if (not all(math.isfinite(value) for row in rows for value in row)
                        or actual[3]!=1 or expected[3]!=1 or normal[3]!=0 or reference[3]!=0):
                    raise ValidationError('Malformed saved homogeneous position/normal')
                # Keep original IEEE754 bytes (including signed zero), not repacked values.
                original[0].update(blocks[1][index*16:index*16+12]);original[1].update(blocks[3][index*16:index*16+12])
                distance=sum((actual[i]-expected[i])**2 for i in range(3))
                vector=sum((normal[i]-reference[i])**2 for i in range(3))
                a=sum(v*v for v in normal[:3]);b=sum(v*v for v in reference[:3])
                if abs(a-1)>2e-5 or abs(b-1)>2e-5:raise ValidationError('Nonunit saved reference normal')
                cosine=sum(normal[i]*reference[i] for i in range(3))/math.sqrt(a*b)
                if distance>1e-10 or vector>4e-6 or cosine<math.cos(math.radians(.1)):
                    raise ValidationError('Saved body numerical readback exceeds C limits')
                max_position=max(max_position,distance);max_vector=max(max_vector,vector);minimum_cosine=min(minimum_cosine,cosine)
        if any(stream.read(1) for stream in streams):raise ProjectStorageError('Trailing saved reference bytes')
        finished=[os.fstat(stream.fileno()) for stream in streams]
    after=[protected(path).stat() for path in paths];budget.check()
    if any(stamp(a)!=stamp(b) or stamp(b)!=stamp(c) or stamp(c)!=stamp(d)
           or a.st_ctime_ns!=d.st_ctime_ns or b.st_ctime_ns!=c.st_ctime_ns
           for a,b,c,d in zip(before,opened,finished,after)):
        raise ProjectStorageError('Saved body streams changed during captured comparison')
    if any(digest.hexdigest()!=hashes[name] for name,digest in zip(NAMES,full)):
        raise ProjectStorageError('Captured saved body bytes differ from selected SHA')
    for name,digest in zip(('native_positions.bin','native_normals.bin'),original):
        record=references.get(name)
        if (type(record) is not dict or type(record.get('bytes')) is not int
                or record['bytes']!=frames*vertices*12 or record.get('sha256')!=digest.hexdigest()):
            raise ValidationError('C reference does not match retained original producer hash')
    return captured,dict(samples=frames,vertices=vertices,maximum_position_error_m=math.sqrt(max_position),
        maximum_normal_vector_error=math.sqrt(max_vector),
        maximum_normal_angle_degrees=math.degrees(math.acos(max(-1.,min(1.,minimum_cosine)))))
