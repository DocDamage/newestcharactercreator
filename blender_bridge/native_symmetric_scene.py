"""Reproduce a SHA-bound base before adding a private shoulder-layer Action.

The nested disposable worker directory gives the legacy verifier its fixed
filenames. No input is renamed, linked, modified or replaced. Every new process
rechecks the original source and all base poses/skin, not just report hashes.
"""
from pathlib import Path
import shutil

from blender_bridge.native_fit_policy import BASE_HASHES, load_fit
from blender_bridge.native_fit_scene import original_context, unchanged, input_hashes
from blender_bridge.native_inputs import read_json
from blender_bridge.native_review_reopen import digest


def symmetric_context(bpy, root, options, *, source_frame_observer=None):
    from blender_bridge.native_fit_measure import measure_saved_fit
    unchanged(root, options)
    nested = root/'symmetric_base_verification'
    if nested.exists() or nested.is_symlink():
        raise ValueError('Refuse to replace a symmetric base verification directory')
    legacy = {k: options[k] for k in BASE_HASHES}
    legacy.update(fit_sha256=options['base_fit_policy_sha256'], fitted_sha256=options['base_fitted_sha256'],
                  fit_report_sha256=options['base_fit_report_sha256'])
    names = {'contact_fit.json': 'base_contact_fit.json', 'fitted_motion.blend': 'base_fitted_motion.blend',
             'fitted_timeline.json': 'base_fitted_timeline.json'}
    nested.mkdir()
    for name, expected in input_hashes(legacy).items():
        source = root/names.get(name, name); output = nested/name
        if source.is_symlink() or not source.is_file() or digest(source) != expected:
            raise ValueError('Symmetric base staged input identity differs')
        with source.open('rb') as reader, output.open('xb') as writer:
            shutil.copyfileobj(reader, writer, length=1024*1024)
        if digest(output) != expected: raise ValueError('Symmetric base changed while copying')
    captured = []
    def capture(bpy, folder, identities, **kwargs):
        context = original_context(bpy, folder, identities, **kwargs)
        captured.append(context)
        return context
    actual = measure_saved_fit(bpy, nested, legacy, source_frame_observer=source_frame_observer,
                               context_factory=capture)
    expected = read_json(root/'base_fitted_timeline.json', options['base_fit_report_sha256'], 64*1024*1024)
    if actual != expected:
        raise ValueError('Symmetric base saved Action/skin differs from its complete canonical evidence')
    if len(captured) != 1: raise ValueError('Symmetric base context was not independently reproduced')
    baseline, profile, _base, state, reopened = captured[0]
    plan = load_fit(root, options, baseline, profile, {n: row['parent'] for n, row in state['rest'].items()})
    # measure_saved_fit leaves the verified base Action loaded. The stage worker
    # copies that Action, preserving all inactive frames without recomputation.
    unchanged(nested, legacy); unchanged(root, options)
    return baseline, profile, plan, state, reopened
