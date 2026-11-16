"""Selected installed Godot, fresh import/build and separate saved-scene reopen."""
from pathlib import Path
import shutil
from ucc.core.errors import ProjectStorageError,ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from .godot_candidate_inputs import read_json,regular_file
from .master_preview import _digest
from .runner import run_process,WorkerFailure
from .private_render_evidence import png_measurements

SCRIPTS=('configure.gd','inspect.gd','ucc_export.gd','ucc_skin_adapter.gd')
PAYLOAD=('character.glb','character.tscn','character_preview.tscn','project.godot','skin_plan.json',
    'morph_reference.json','morph_reference.bin','request.json',*SCRIPTS)
OUTPUTS=('export_verification.json','character.png','face-expression.png')


def scripts() -> dict[str,Path]:
    from .worker_resources import bundled_static_adapter_paths
    return bundled_static_adapter_paths()


def checked_observation(folder: Path,request_sha: str,*,mode: str) -> dict:
    record=read_json(folder/'export_verification.json',4*1024*1024)
    fields={'schema_version','status','mode','request_sha256','engine','adapter','rendering_method','observed','saved_scene_sha256',
        'preview_scene_sha256','saved_scene_reopened_without_repair','visual_quality_approved','distribution_license_review_complete'}
    if (set(record)!=fields or type(record.get('schema_version')) is not int or record['schema_version']!=1 or record.get('status')!='STATIC_GODOT_CHARACTER_VERIFIED_V1' or record.get('mode')!=mode
            or record.get('request_sha256')!=request_sha or record.get('saved_scene_reopened_without_repair') is not (mode=='verify')
            or record.get('visual_quality_approved') is not False or record.get('distribution_license_review_complete') is not False
            or type(record.get('engine')) is not dict or record['engine'].get('major')!=4 or record['engine'].get('minor')!=7
            or record.get('rendering_method')!='mobile' or type(record.get('adapter')) is not str or not record['adapter'].strip()):
        raise ValidationError('Godot did not return complete bound saved-scene evidence')
    data=record.get('observed',{})
    if (type(data) is not dict or any(type(data.get(k)) is not int or data[k]!=v for k,v in {'bones':163,'morphs':12,'animation_clips':0,'vertices':14517,'triangles':26756}.items())
            or data.get('exact_position_UV_correspondence') is not True or type(data.get('skin')) is not dict or data['skin'].get('unit_sum_verified') is not True
            or data['skin'].get('positive_influences_retained') is not True):raise ValidationError('Actual Godot rig/morph/skin/UV verification is incomplete')
    request_file=regular_file(folder/'request.json',folder,256*1024)
    if _digest(request_file)!=request_sha:raise ProjectStorageError('Static export request changed before readback')
    spec=SkinMaterialSpec.from_dict(read_json(request_file,256*1024)['material_spec']);material=data.get('material')
    if (type(material) is not dict or type(material.get('base_color_srgb')) is not list or len(material['base_color_srgb'])!=3
            or any(type(v) not in (int,float) or not 0<=v<=1 for v in material['base_color_srgb'])
            or max(abs(a-b) for a,b in zip(material['base_color_srgb'],spec.base_color_srgb))>1e-6
            or type(material.get('roughness')) not in (int,float) or not 0<=material['roughness']<=1 or abs(material['roughness']-spec.roughness)>1e-6
            or type(material.get('metallic')) not in (int,float) or material['metallic']!=0
            or type(material.get('textures')) is not int or material['textures']!=0 or material.get('override') is not False):
        raise ValidationError('Actual Godot material readback differs from the reviewed saved material')
    for key in ('maximum_rest_skin_error_m','maximum_morph_error_m'):
        value=data.get(key)
        if type(value) not in (int,float) or not 0<=value<=1e-5:raise ValidationError('Actual Godot deformation exceeds the bounded source comparison')
    for name,key in [('character.tscn','saved_scene_sha256'),('character_preview.tscn','preview_scene_sha256')]:
        if _digest(regular_file(folder/name,folder,64*1024*1024))!=record.get(key):raise ProjectStorageError('Saved Godot scene changed after readback')
    images=[]
    for name in ('character.png','face-expression.png'):
        image=regular_file(folder/name,folder,2*1024*1024)
        images.append(png_measurements(image.read_bytes(),include_pixel_hash=True,expected_size=(512,512)))
    if images[0]['rgba_sha256']==images[1]['rgba_sha256']:raise ValidationError('Actual facial preview render did not change')
    return record


def run_engine(folder: Path,work: Path,exe: Path,request_sha: str,*,mode: str,remaining,cancel,guard,commands: list) -> dict:
    immutable={p:_digest(p,cancel) for p in folder.iterdir() if p.is_file() and p.name not in OUTPUTS}
    def run(label: str,args: list[str]):
        guard();command=[str(exe),'--path',str(folder),*args]
        result=run_process(command,work/label,timeout_s=remaining(),cancel=cancel)
        commands.append({'phase':label,'command':command,'return_code':result.return_code,'cancelled':result.cancelled,'timed_out':result.timed_out,'elapsed_seconds':result.elapsed_seconds})
        (work/'commands.json').write_bytes(canonical_bytes({'commands':commands}))
        if result.cancelled or result.timed_out or result.return_code!=0:
            raise WorkerFailure('Godot export '+label+' failed/cancelled/timed out; logs: '+str(work/label))
        guard()
        for path,sha in immutable.items():
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=sha:raise ProjectStorageError('Godot modified an immutable export input')
    run('initial-import',['--headless','--editor','--import'])
    run('configure',['--headless','--script','res://configure.gd'])
    run('configured-import',['--headless','--editor','--import'])
    run('actual-'+mode,['--rendering-method','mobile','--rendering-driver','vulkan','--audio-driver','Dummy','--position','-32000,-32000',
        '--script','res://ucc_export.gd','--',mode,request_sha])
    return checked_observation(folder,request_sha,mode=mode)


def reopen_copy(source: Path,destination: Path) -> None:
    destination.mkdir(exist_ok=False)
    for name in PAYLOAD:shutil.copy2(regular_file(source/name,source,128*1024*1024),destination/name)
