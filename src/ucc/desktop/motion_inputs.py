"""Watch bound motion inputs without treating new diagnostic jobs as edits."""
import os
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.jobs.master_preview import _digest


def _identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValidationError('A bound animation input is missing or replaced')
    def stamp():
        stat=path.stat()
        return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    before=stamp();digest=_digest(path)
    if path.is_symlink() or before!=stamp():
        raise ValidationError('A bound animation input changed while checking its identity')
    return (*before,digest)


def watch_inputs(window,paths):
    """Extend the receipt only after installing both file and parent watches."""
    identities={Path(p):_identity(Path(p)) for p in paths}
    receipts=getattr(window,'_motion_input_identities',{}).copy()
    if any(p in receipts and receipts[p]!=identity for p,identity in identities.items()):
        window._clear_native_review()
        raise ValidationError('A watched animation input changed before extending its review')
    watcher=window._motion_watcher
    existing=watcher.files()+watcher.directories()
    missing=sorted({str(p) for p in identities}|{str(p.parent) for p in identities})
    missing=[p for p in missing if p not in existing]
    if missing and watcher.addPaths(missing):
        window._clear_native_review()
        raise ValidationError('Could not monitor animation inputs; playback was not published')
    if any(_identity(p)!=identity for p,identity in identities.items()):
        window._clear_native_review()
        raise ValidationError('An animation input changed while installing its watch')
    receipts.update(identities)
    window._motion_input_identities=receipts


def directory_changed(window,directory):
    """Parent events include unrelated files; validate just this parent's inputs.

    File events still invalidate immediately. Parent watches also catch deletion
    and atomic replacement when the operating system drops the file watch.
    """
    parent=os.path.normcase(os.path.abspath(directory))
    try:
        for path,identity in getattr(window,'_motion_input_identities',{}).items():
            if os.path.normcase(os.path.abspath(path.parent))==parent and _identity(path)!=identity:
                window._clear_native_review()
                return
    except (OSError,ValidationError):
        window._clear_native_review()
