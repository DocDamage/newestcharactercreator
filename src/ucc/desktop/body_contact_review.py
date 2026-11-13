"""Read-only body-review action and publication into current immutable playback."""
from pathlib import Path
from threading import Event

from ucc.core.errors import UCCError,ValidationError
from ucc.jobs.body_contact_review import review_body_contact_areas
from ucc.jobs.master_preview import _digest
from ucc.library.provenance import LicensePolicy
from .generation import bundled_worker_path
from .motion_inputs import watch_inputs


def start_body_contact_review(window):
    if window.jobs.busy:window._error('Another local task is still running');return
    preview=window._native_review;playback=window._native_playback;controller=window.controller
    if preview is None or playback is None or controller.store is None or controller.dirty:
        window._error('Load verified motion on the saved character before reviewing body contacts');return
    pane=window.animations
    if not pane.local_preview_review.isChecked():window._error('Confirm local animation preview rights first');return
    try:
        executable=window._blender_executable
        if executable is None or executable.is_symlink() or not executable.is_file():
            raise ValidationError('Select Blender and repeat the original preview')
        permission=LicensePolicy(pane.provider.text().strip(),pane.license.text().strip(),pane.uri.text().strip(),
                                 reviewed=True,local_preview_allowed=True,no_ai=True)
        store=controller.store;source=Path(pane.selected.text());fitted=window._fitted_playback;cancel=Event()
        worker=bundled_worker_path()
        window._submit('body_contacts',lambda:review_body_contact_areas(store,preview,playback,source_fbx=source,
            permission=permission,blender_exe=executable,worker_script=worker,fitted=fitted,cancel=cancel),cancel=cancel)
        window.log.setPlainText('REVIEWING HAND / CENTRAL-BODY CONTACTS\n'
            'Every saved frame is inspected and independently reproduced against the head, neck and spine chain.\n'
            'This read-only local review can take several minutes. Cancel from the Character menu.\n'
            'Playable motion remains available. Surface crossings do not approve grasp intent, visual quality or engine compatibility.')
    except (UCCError,OSError,ValueError) as error:window._error(str(error))


def publish_body_contact_review(window,result):
    controller=window.controller;preview=window._native_review;current=window._native_playback;fitted=window._fitted_playback
    if (preview is None or current is None or controller.store is None or controller.dirty or window.motion_viewer is None or
        not window.animations.local_preview_review.isChecked()):
        raise ValidationError('Motion selection or local-preview permission changed before body review publication')
    project=controller.require_project();bindings=dict(result.bindings)
    if (controller.store.load()!=project or any(getattr(result,k)!=getattr(current,k) for k in ('project_id','revision','master_sha256','source_sha256')) or
        project.project_id!=result.project_id or project.revision!=result.revision or
        current.job_id!=result.original_playback.job_id or current.cache.packed!=result.original_playback.cache.packed or
        (fitted is None)!=(result.fitted_playback is None)):
        raise ValidationError('Character or visible original/fitted buffers changed during body inspection')
    paths={Path(window.animations.selected.text()):result.source_sha256,controller.master_path():result.master_sha256,
        controller.store.root/'project.ucc.json':result.metadata_sha256,Path(preview.mapping_profile_used):bindings['mapping_sha256'],
        Path(preview.private_timeline):bindings['timeline_sha256'],Path(preview.private_visual_review_blend):bindings['review_sha256'],
        Path(preview.private_timeline).parent/'source_snapshot.json':bindings['snapshot_sha256'],Path(result.private_report):result.report_sha256}
    if fitted is not None:
        other=result.fitted_playback
        if (other.job_id!=fitted.job_id or other.fitted_scene_sha256!=fitted.fitted_scene_sha256 or
            other.fit_policy_sha256!=fitted.fit_policy_sha256 or other.cache.packed!=fitted.cache.packed):
            raise ValidationError('Visible fitted motion changed during body contact inspection')
        fp=fitted.fitted_preview
        paths.update({Path(fp.fit_policy_used):bindings['fit_sha256'],Path(fp.private_fitted_scene):bindings['fitted_sha256'],
                      Path(fp.private_timeline):bindings['fit_report_sha256']})
    if any(p.is_symlink() or not p.is_file() or _digest(p)!=digest for p,digest in paths.items()):
        raise ValidationError('Body review source/master/policy/report changed before publication')
    watch_inputs(window,paths)
    window.motion_viewer.show_body_contacts(result.contacts.original,result.contacts.fitted)
    window._body_contact_review=result
    original=result.contacts.original
    text=(f'Original: {len(original.flagged_frames)} flagged frames.' if original.status=='CHECKED' else 'Original body inspection unavailable.')
    if result.contacts.fitted is not None:
        fit=result.contacts.fitted
        text+=(f' Fitted: {len(fit.flagged_frames)} flagged frames.' if fit.status=='CHECKED' else ' Fitted body inspection unavailable.')
        if result.contacts.more_pair_frames is not None:text+=f' Higher pair counts after fitting: {len(result.contacts.more_pair_frames)} frames.'
        if result.areas is not None:
            areas=result.areas
            if areas.status=='CHECKED':
                text+=f' Newly involved contact areas: {len(areas.new_area_frames)} frames. Increased pairs for either hand: {len(areas.more_hand_pair_frames)} frames.'
            else:text+=' Stable contact-area comparison unavailable.'
    window.log.setPlainText('VERIFIED HAND / CENTRAL-BODY CONTACT REVIEW\n'+text+'\n'
        'Use the inspection selector to switch between opposite-arm and central-body annotations at the same source frame.\n'
        'Next flagged frame, Max pairs, Highlight and Focus use the selected inspection.\n'
        'Central body includes the head, neck and spine chain. Grasp intent, visual quality and engine compatibility remain unapproved.')


def show_body_contact_error(window,error):
    from PySide6.QtWidgets import QMessageBox
    message=('Body contact review was cancelled. Playable motion was retained.' if 'cancelled' in error.lower() else
             'Body contact review stopped before new annotations were shown. Reload the motion if its inputs changed.')
    window.log.setPlainText(message+'\n\nLocal diagnostic details:\n'+error[:100000]);window.statusBar().showMessage('Body contact review stopped')
    dialog=QMessageBox(window);dialog.setWindowTitle('UCC body contact review');dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText(message);dialog.setDetailedText(error[:100000]);dialog.exec()
