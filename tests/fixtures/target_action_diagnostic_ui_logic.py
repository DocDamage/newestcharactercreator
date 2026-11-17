"""NONSHIPPING synthetic scalar report; never Blender or animation evidence."""
from pathlib import Path
import struct

from ucc.animations.target_action_diagnostic import (
    DiagnosticSamples, TargetActionDiagnosticSelection, measure_target_action_diagnostic,
)


def synthetic_report():
    selection = TargetActionDiagnosticSelection(
        'unit-project', 1, 'a'*64, 'b'*64, 'unit:nonshipping#clip-0000',
        'c'*64, 'd'*64, 'e'*64)
    samples = DiagnosticSamples(
        struct.pack('<fff', 0, 0, 0), struct.pack('<fff', 0, 0, 0),
        (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        ((0., 0., 0.),)*300, ((0., 0., 0.),)*300,
        cache_sha256='f'*64, timeline_sha256='1'*64)
    return measure_target_action_diagnostic(selection, samples)


def synthetic_loaded(path: Path):
    from ucc.jobs.target_action_diagnostic import LoadedTargetActionDiagnostics
    from ucc.desktop.target_action_preview import _stamp
    path = path.resolve()
    def never_guard(**_):
        raise AssertionError('Background proof guard must never run on the GUI thread')
    return LoadedTargetActionDiagnostics(synthetic_report(), (path, path.parent),
        ((path, _stamp(path)), (path.parent, _stamp(path.parent))), never_guard, path)
