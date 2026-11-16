"""Read-only body-review action and publication into current immutable playback."""
from pathlib import Path
from threading import Event

from ucc.core.errors import UCCError,ValidationError
from ucc.jobs.body_contact_review import review_complete_anatomical_safety
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
        window._submit('body_contacts',lambda:review_complete_anatomical_safety(store,preview,playback,source_fbx=source,
            permission=permission,blender_exe=executable,worker_script=worker,fitted=fitted,cancel=cancel),cancel=cancel)
        window.log.setPlainText('REVIEWING HAND / CENTRAL-BODY CONTACTS\n'
            'Every saved frame is inspected and independently reproduced against the complete measured head and torso skin, including buried or uncertain hand areas.\n'
            'This read-only full-clip review can take tens of minutes. Cancel from the Character menu.\n'
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
    if result.enclosure is not None:
        paths.update({Path(result.private_enclosure_report):result.enclosure_report_sha256,
                      Path(result.private_anatomical_verification):result.anatomical_verification_sha256})
    if result.full_trunk is not None:
        if result.enclosure is None or (result.full_trunk.fitted is None)!=(fitted is None):
            raise ValidationError('Complete torso surfaces lack their verified original/fitted enclosure context')
        paths[Path(result.private_full_trunk_report)]=result.full_trunk_report_sha256
    if fitted is not None:
        other=result.fitted_playback
        if (other.job_id!=fitted.job_id or other.fitted_scene_sha256!=fitted.fitted_scene_sha256 or
            other.fit_policy_sha256!=fitted.fit_policy_sha256 or other.cache.packed!=fitted.cache.packed):
            raise ValidationError('Visible fitted motion changed during body contact inspection')
        fp=fitted.fitted_preview
        paths.update({Path(fp.fit_policy_used):bindings['fit_sha256'],Path(fp.private_fitted_scene):bindings['fitted_sha256'],
                      Path(fp.private_timeline):bindings['fit_report_sha256']})
        if 'base_fit_policy_sha256' in bindings:
            folder=Path(fp.fit_policy_used).parent
            paths.update({folder/'base_contact_fit.json':bindings['base_fit_policy_sha256'],
                          folder/'base_fitted_motion.blend':bindings['base_fitted_sha256'],
                          folder/'base_fitted_timeline.json':bindings['base_fit_report_sha256']})
    if any(p.is_symlink() or not p.is_file() or _digest(p)!=digest for p,digest in paths.items()):
        raise ValidationError('Body review source/master/policy/report changed before publication')
    watch_inputs(window,paths)
    original=result.full_trunk.original.surface if result.full_trunk is not None else result.contacts.original
    fit=(result.full_trunk.fitted.surface if result.full_trunk.fitted is not None else None) if result.full_trunk is not None else result.contacts.fitted
    window.motion_viewer.show_body_contacts(original,fit)
    window._body_contact_review=result
    text=(f'Original: {len(original.flagged_frames)} flagged frames.' if original.status=='CHECKED' else 'Original body inspection unavailable.')
    if fit is not None:
        text+=(f' Fitted: {len(fit.flagged_frames)} flagged frames.' if fit.status=='CHECKED' else ' Fitted body inspection unavailable.')
        if result.full_trunk is None and result.contacts.more_pair_frames is not None:
            text+=f' Higher pair counts after fitting: {len(result.contacts.more_pair_frames)} frames.'
        if result.areas is not None:
            areas=result.areas
            if areas.status=='CHECKED':
                scope=' Head/spine comparison: newly involved contact areas' if result.full_trunk is not None else ' Newly involved contact areas'
                text+=f'{scope}: {len(areas.new_area_frames)} frames. Increased pairs for either hand: {len(areas.more_hand_pair_frames)} frames.'
            else:text+=' Stable contact-area comparison unavailable.'
    if result.full_trunk is not None:
        full=result.full_trunk
        if full.fitted is not None:
            text+=f' Complete torso newly involved areas: {len(full.new_area_frames)} frames. Increased pairs for either hand: {len(full.more_hand_pair_frames)} frames.'
    if result.enclosure is not None:
        for name in ('original','fitted'):
            variant=getattr(result.enclosure,name)
            if variant is not None:
                text+=f' Trunk enclosure ({name}): {sum(any(row) for row in variant.inside)} frames with enclosed hand probes; {sum(any(row) for row in variant.ambiguous)} frames with uncertainty.'
        text+=' These observations do not approve remaining buried or uncertain skin.'
    window.log.setPlainText('VERIFIED HAND / CENTRAL-BODY CONTACT REVIEW\n'+text+'\n'
        'Use the inspection selector to switch between opposite-arm and central-body annotations at the same source frame.\n'
        'Next flagged frame, Max pairs, Highlight and Focus use the selected inspection.\n'+
        ('Complete body inspection covers the measured head and torso skin. ' if result.full_trunk is not None else
         'Central body includes the head, neck and spine chain. ')+
        'Grasp intent, visual quality and engine compatibility remain unapproved.')


def show_body_contact_error(window,error):
    from PySide6.QtWidgets import QMessageBox
    message=('Body contact review was cancelled. Playable motion was retained.' if 'cancelled' in error.lower() else
             'Body contact review stopped before new annotations were shown. Reload the motion if its inputs changed.')
    window.log.setPlainText(message+'\n\nLocal diagnostic details:\n'+error[:100000]);window.statusBar().showMessage('Body contact review stopped')
    dialog=QMessageBox(window);dialog.setWindowTitle('UCC body contact review');dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText(message);dialog.setDetailedText(error[:100000]);dialog.exec()
