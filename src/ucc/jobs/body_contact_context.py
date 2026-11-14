"""Prepare the optional verified fitted variant for read-only body inspection."""
from dataclasses import replace
from pathlib import Path

from ucc.core.errors import ValidationError,ProjectConflict
from ucc.animations.symmetric_fit import fitted_hash_fields
from ucc.preview.fitted_cache import read_fitted_cache,FIT_HASHES
from .cached_job_evidence import cached_job_details
from .native_fit_evidence import read_json_record,validate_fitted_data
from .native_fit_renders import validate_fit_verification
from .master_preview import _digest


def fitted_body_context(store,ctx,preview,fitted,*,cancel=None,cancel_check=lambda:None):
    fp=fitted.fitted_preview;options=fp.verification.get('bindings')
    if (fitted.original_preview is not preview or
        any(getattr(fitted,k)!=getattr(ctx.playback,k) for k in ('project_id','revision','master_sha256','source_sha256')) or
        type(options) is not dict or set(options)!=fitted_hash_fields(options) or
        any(options.get(k)!=v for k,v in ctx.bindings.items()) or
        options['fit_sha256']!=fitted.fit_policy_sha256 or options['fitted_sha256']!=fitted.fitted_scene_sha256):
        raise ProjectConflict('Fitted character/source changed before body contact inspection')
    paths={'contact_fit.json':Path(fp.fit_policy_used),'fitted_motion.blend':Path(fp.private_fitted_scene),
           'fitted_timeline.json':Path(fp.private_timeline)}
    expected=dict(zip(paths,(options['fit_sha256'],options['fitted_sha256'],options['fit_report_sha256'])))
    jobs=store.root/'.ucc-jobs'
    if 'base_fit_policy_sha256' in options:
        from .symmetric_fit_evidence import cached_base_inputs
        base_paths,base_expected=cached_base_inputs(paths['contact_fit.json'].parent,options,jobs)
        paths.update(base_paths);expected.update(base_expected)
    for name in ('fitted_motion.blend','fitted_timeline.json'):
        path=paths[name]
        if jobs.is_symlink() or path.parent.is_symlink() or path.resolve().parent.parent!=jobs.resolve():
            raise ValidationError('Fitted body inspection scene/evidence is outside its private project job')
    for name,path in paths.items():
        if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=expected[name]:
            raise ValidationError('Fitted body inspection policy/scene/evidence changed')
    path=paths['fitted_timeline.json']
    data,_=read_json_record(path.parent,{'name':path.name,'bytes':path.stat().st_size,'sha256':options['fit_report_sha256']},
        path.name,64*1024*1024,cancel_check=cancel_check)
    _plan,surface,_angular=validate_fitted_data(data,{k:v for k,v in options.items() if k!='fit_report_sha256'},ctx.baseline,
        ctx.profile,paths['contact_fit.json'],fp.evidence['target_rest_frames'],cancel_check=cancel_check)
    validate_fit_verification(fp.verification,options,data)
    cache_folder=Path(fitted.private_manifest).parent
    if cache_folder.name!=fitted.job_id or Path(fitted.private_manifest)!=cache_folder/'fitted_skin.json':
        raise ValidationError('Fitted body inspection cache identity differs')
    report=cached_job_details(store.root/'.ucc-jobs',cache_folder,'cache_native_fit',cancel=cancel,cancel_check=cancel_check)
    cache=read_fitted_cache(cache_folder,report,options,data,ctx.baseline,surface,cancel_check=cancel_check)
    return dict(options),paths,expected,data,replace(fitted,cache=cache)
