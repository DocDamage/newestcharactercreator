"""Bound and independently decode private fitted-scene views before publication."""
from hashlib import sha256
import math
from ucc.core.errors import ValidationError
from .native_evidence import bound_file
from .native_fit_evidence import FLAGS,read_json_record
from .private_render_evidence import png_measurements,WIDTH,HEIGHT,VIEWS


def validate_fit_verification(report,options,data):
    fields={'status','bindings','frames_verified','private_review_renders','originals_unchanged'}|FLAGS
    if (type(report) is not dict or set(report)!=fields or report['status']!='REAL_NATIVE_FIT_VERIFIED' or
        report['bindings']!=options or type(report['frames_verified']) is not int or report['frames_verified']!=data['frame_count'] or
        report['originals_unchanged'] is not True or any(report[k] is not False for k in FLAGS)):
        raise ValidationError('Fitted scene was not independently reopened with complete bound evidence')


def fit_render_frames(plan):
    if plan.render_frames:return list(plan.render_frames)
    if hasattr(plan,'active_frames'):
        active=[i for i,v in enumerate(plan.active_frames,1) if v]
        def magnitude(frame):
            return sum(math.hypot(*s.arm.offsets[frame-1])+math.hypot(*s.rotations[frame-1])+
                       (math.hypot(*s.arm.hand_rotations[frame-1]) if s.arm.hand_rotations else 0.)
                       for s in (plan.left,plan.right))
        peak=max(active,key=magnitude);count=len(plan.active_frames)
        chosen={1,count,active[0],active[-1],peak}
        for frame in range(1,count+1):
            if len(chosen)==5:break
            chosen.add(frame)
        return sorted(chosen)
    if len(plan.offsets)<5:raise ValidationError('Fitted private review requires five source frames')
    active=[i for i,v in enumerate(plan.offsets,1) if math.hypot(*v)>1e-7]
    peak=max(active,key=lambda i:math.hypot(*plan.offsets[i-1]))
    chosen={1,len(plan.offsets),active[0],active[-1],peak}
    for frame in range(1,len(plan.offsets)+1):
        if len(chosen)==5:break
        chosen.add(frame)
    return sorted(chosen)


def verify_fit_renders(folder,report,options,data,baseline,plan,*,cancel_check=lambda:None):
    validate_fit_verification(report,options,data)
    raw=report['private_review_renders']
    if (type(raw) is not dict or set(raw)!={'manifest','index','image_count','animation_visual_quality_verified'} or
        type(raw['image_count']) is not int or raw['image_count']!=15 or raw['animation_visual_quality_verified'] is not False):
        raise ValidationError('Fitted review requires all fifteen unapproved actual-skin views')
    root=folder/'review_frames'
    if root.is_symlink() or not root.is_dir() or root.resolve().parent!=folder.resolve():
        raise ValidationError('Fitted render directory is redirected')
    manifest,_=read_json_record(root,raw['manifest'],'manifest.json',64*1024,cancel_check=cancel_check)
    index=bound_file(root,raw['index'],'index.html',64*1024,cancel_check=cancel_check)
    fields={'schema_version','method','fit_bindings','scope','source_frame_count','rendered_frames','animation_visual_quality_verified','images'}
    samples=fit_render_frames(plan)
    if (type(manifest) is not dict or set(manifest)!=fields or type(manifest['schema_version']) is not int or manifest['schema_version']!=1 or
        manifest['method']!='CYCLES_CPU_EVALUATED_SKIN_CLAY_V1' or manifest['fit_bindings']!=options or
        manifest['scope']!='BOUNDED_TARGET_FIT_NOT_SOURCE_FK_OR_CONTACT_APPROVAL' or
        type(manifest['source_frame_count']) is not int or manifest['source_frame_count']!=data['frame_count'] or
        type(manifest['rendered_frames']) is not list or any(type(v) is not int for v in manifest['rendered_frames']) or
        manifest['rendered_frames']!=samples or manifest['animation_visual_quality_verified'] is not False or
        type(manifest['images']) is not list or len(manifest['images'])!=15):
        raise ValidationError('Fitted render provenance or requested sample coverage differs')
    image_fields={'name','bytes','sha256','frame','view','width','height','opaque_pixels','opaque_bounds','evaluated_sha256','camera_root_offset_world'}
    for row,(frame,view) in zip(manifest['images'],((f,v) for f in samples for v in VIEWS)):
        cancel_check()
        if (type(row) is not dict or set(row)!=image_fields or type(row['frame']) is not int or row['frame']!=frame or row['view']!=view or
            type(row['width']) is not int or row['width']!=WIDTH or type(row['height']) is not int or row['height']!=HEIGHT or
            row['evaluated_sha256']!=data['frames'][frame-1]['skin_sha256']):
            raise ValidationError('Fitted render does not represent the verified frame/view/skin')
        record={k:row[k] for k in ('name','bytes','sha256')}
        path=bound_file(root,record,f'frame_{frame:04}_{view}.png',2*1024*1024,cancel_check=cancel_check)
        with path.open('rb') as stream:payload=stream.read(2*1024*1024+1)
        if len(payload)!=row['bytes'] or sha256(payload).hexdigest()!=row['sha256']:
            raise ValidationError('Fitted render changed while reading')
        measured=png_measurements(payload)
        if any(row[k]!=v for k,v in measured.items()):raise ValidationError('Fitted PNG pixel measurements disagree')
        expected=[baseline['full_timeline_frames'][frame-1]['root_world_head'][i]-baseline['full_timeline_frames'][samples[0]-1]['root_world_head'][i] for i in range(3)]
        offset=row['camera_root_offset_world']
        if (type(offset) is not list or len(offset)!=3 or any(type(v) not in (int,float) or not -1e6<=v<=1e6 for v in offset) or
            any(abs(a-b)>1e-5 for a,b in zip(offset,expected))):
            raise ValidationError('Fitted render camera does not follow the preserved original root trajectory')
    if any(len({r['sha256'] for r in manifest['images'] if r['view']==v})<2 for v in VIEWS):
        raise ValidationError('Fitted render samples do not show changing actual skin')
    return str(index)
