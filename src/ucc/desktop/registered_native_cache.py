"""Bounded session reuse of already authenticated registered previews."""
from collections import OrderedDict
from dataclasses import dataclass
from threading import Event

from ucc.core.errors import UCCError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.native_body import NativeBodyPreview
from ucc.jobs.native_playback import NativePlayback
from ucc.jobs.target_action_context import operation_budget
from .registered_native_binding import guard_registered_native, selected_clip


_MAX_ENTRIES = 2
_MAX_BYTES = 192 * 1024**2


@dataclass(frozen=True, slots=True)
class _Preview:
    store: ProjectStore
    project: CharacterProject
    body: NativeBodyPreview
    playback: NativePlayback
    identities: tuple


def _automatic(window) -> bool:
    return (not window.animations.native_body_profile.text().strip()
            and not window.animations.native_include_hands.isChecked())


def clear_session_previews(window) -> None:
    entries = getattr(window, '_registered_session_previews', None)
    if entries is not None:
        entries.clear()


def remember_session_preview(window, pending, completion) -> None:
    if (pending is None or not pending.inline or not _automatic(window)
            or not isinstance(completion.value, NativePlayback)
            or not isinstance(completion.inline_preview, NativeBodyPreview)
            or window._native_playback is not completion.value
            or not guard_registered_native(window, completion.value.source_authority)):
        return
    playback = completion.value
    if len(playback.cache.packed) > _MAX_BYTES:
        return
    entries = getattr(window, '_registered_session_previews', None)
    if entries is None:
        entries = window._registered_session_previews = OrderedDict()
    entries[pending.clip_id] = _Preview(pending.store, pending.project, completion.inline_preview,
                                      playback, completion.identities)
    entries.move_to_end(pending.clip_id)
    while len(entries) > _MAX_ENTRIES or sum(len(entry.playback.cache.packed) for entry in entries.values()) > _MAX_BYTES:
        entries.popitem(last=False)


def replay_session_preview(window) -> bool:
    """Revalidate a released preview's original bytes off the UI thread."""
    entries = getattr(window, '_registered_session_previews', {})
    clip = selected_clip(window)
    cached = entries.get(clip)
    if (cached is None or window.jobs.busy or not _automatic(window)
            or window._native_playback is cached.playback):
        return False
    entries.pop(clip)
    authority = cached.playback.source_authority
    proof = cached.playback.proof_receipt
    if (window.controller.store is not cached.store or window.controller.dirty
            or not window.controller.has_project or window.controller.require_project() != cached.project
            or not authority.identities_current() or not proof.identities_current()):
        return False
    from .registered_native_workflow import RegisteredNativeCompletion, RegisteredNativePending, _begin_inline_progress
    try:
        if authority.database_path != window._catalog_path():
            return False
    except (UCCError, OSError, ValueError):
        return False
    window._clear_native_review()
    pending = RegisteredNativePending(object(), cached.store, cached.store.root.resolve(), cached.project,
                                      clip, Event(), inline=True)
    window._registered_native_pending = pending
    progress = _begin_inline_progress(window, pending.token)
    progress('REUSE_VERIFY')

    def verify():
        with operation_budget(pending.cancel, 60) as budget:
            if (authority.guard(cancel=budget.cancel, timeout_s=budget.remaining()) is not True
                    or proof.guard(cancel=budget.cancel, timeout_s=budget.remaining()) is not True
                    or authority.guard(cancel=budget.cancel, timeout_s=budget.remaining()) is not True
                    or not authority.identities_current() or not proof.identities_current()):
                raise ValidationError('Saved preview inputs changed. Preview the clip again to verify the new files.')
            return RegisteredNativeCompletion(pending.token, cached.playback, cached.identities,
                                              inline_preview=cached.body)

    window._submit('registered_native_body', verify, cancel=pending.cancel)
    return True
