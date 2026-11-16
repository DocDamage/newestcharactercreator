"""Independently validate the canonical base before its shoulder layer."""
from ucc.animations.contact_fit import HASHES
from ucc.animations.symmetric_fit import BINDINGS, read_symmetric_fit
from ucc.core.errors import ValidationError


def read_layer_plan(policy_path, options, baseline, profile, stage_rest, *, cancel_check=lambda: None):
    from .native_fit_evidence import read_json_record, rest_parents, validate_fitted_data
    folder = policy_path.parent
    paths = {}
    for name, key, maximum in (
        ('base_contact_fit.json', 'base_fit_policy_sha256', 512*1024),
        ('base_fitted_timeline.json', 'base_fit_report_sha256', 64*1024*1024),
    ):
        path = folder/name
        if path.is_symlink() or not path.is_file(): raise ValidationError('Missing regular symmetric base evidence')
        paths[name] = read_json_record(folder, {'name': name, 'bytes': path.stat().st_size, 'sha256': options[key]},
                                      name, maximum, cancel_check=cancel_check)
    base_options = {k: options[k] for k in HASHES}
    base_options.update(fit_sha256=options['base_fit_policy_sha256'], fitted_sha256=options['base_fitted_sha256'])
    base_data, _ = paths['base_fitted_timeline.json']
    base, _surface, _angular = validate_fitted_data(base_data, base_options, baseline, profile,
        paths['base_contact_fit.json'][1], stage_rest, cancel_check=cancel_check)
    plan = read_symmetric_fit(policy_path, options['fit_sha256'], {k: options[k] for k in BINDINGS},
                              baseline, profile, rest_parents(stage_rest, baseline), base, cancel_check=cancel_check)
    return plan, [row['target_global_poses'] for row in base_data['frames']]


def layer_base_inputs(base, original, jobs, options, baseline, profile, *, cancel_check=lambda: None):
    from pathlib import Path
    from .native_fit_evidence import read_json_record, validate_fitted_data
    from .native_fit_renders import validate_fit_verification
    from .native_evidence import bound_file
    from ucc.preview.fitted_cache import FIT_HASHES
    identities = base.verification.get('bindings')
    if (base.project_id != original.project_id or base.revision != original.revision or
            base.master_sha256 != original.master_sha256 or base.source_sha256 != original.source_sha256 or
            type(identities) is not dict or set(identities) != FIT_HASHES or
            {k: identities[k] for k in HASHES} != options or
            identities['fitted_sha256'] != base.fitted_scene_sha256 or identities['fit_sha256'] != base.fit_policy_sha256):
        raise ValidationError('Shoulder layer base differs from this original character/source verification')
    paths = {'base_contact_fit.json': Path(base.fit_policy_used), 'base_fitted_motion.blend': Path(base.private_fitted_scene),
             'base_fitted_timeline.json': Path(base.private_timeline)}
    keys = {'base_contact_fit.json': 'fit_sha256', 'base_fitted_motion.blend': 'fitted_sha256',
            'base_fitted_timeline.json': 'fit_report_sha256'}
    for name in ('base_fitted_motion.blend', 'base_fitted_timeline.json'):
        path = paths[name]
        if path.parent.is_symlink() or path.resolve().parent.parent != jobs.resolve():
            raise ValidationError('Shoulder layer base is outside its private project job')
    for name, path in paths.items():
        maximum = 512*1024*1024 if name.endswith('.blend') else (512*1024 if name.endswith('fit.json') else 64*1024*1024)
        if path.is_symlink() or not path.is_file(): raise ValidationError('Missing regular shoulder layer base input')
        bound_file(path.parent, {'name': path.name, 'bytes': path.stat().st_size, 'sha256': identities[keys[name]]},
                   path.name, maximum, cancel_check=cancel_check)
    timeline = paths['base_fitted_timeline.json']
    data, _ = read_json_record(timeline.parent, {'name': timeline.name, 'bytes': timeline.stat().st_size,
                               'sha256': identities['fit_report_sha256']}, timeline.name, 64*1024*1024, cancel_check=cancel_check)
    validate_fitted_data(data, {k: v for k, v in identities.items() if k != 'fit_report_sha256'}, baseline, profile,
                         paths['base_contact_fit.json'], base.evidence['target_rest_frames'], cancel_check=cancel_check)
    validate_fit_verification(base.verification, identities, data)
    return paths, {n: identities[k] for n, k in keys.items()}


def cached_base_inputs(folder, options, jobs):
    if jobs.is_symlink() or folder.is_symlink() or folder.resolve().parent != jobs.resolve():
        raise ValidationError('Symmetric base is outside its private project worker folder')
    keys = {'base_contact_fit.json': 'base_fit_policy_sha256', 'base_fitted_motion.blend': 'base_fitted_sha256',
            'base_fitted_timeline.json': 'base_fit_report_sha256'}
    return {n: folder/n for n in keys}, {n: options[k] for n, k in keys.items()}
