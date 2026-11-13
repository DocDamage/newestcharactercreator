"""One local measured-fitting action; no policy editing or asset upload."""
from pathlib import Path
from threading import Event

from ucc.core.errors import UCCError,ValidationError
from ucc.library.provenance import LicensePolicy
from ucc.jobs.contact_fit import fit_measured_contacts
from .generation import bundled_worker_path


def fit_error_message(error: str) -> str:
    reasons={
        'COMPLETE_TRUNK_FIT_INTRODUCES_CONTACT_AREAS':'The correction would move hand/body crossings onto new torso surface areas. Original motion is retained.',
        'COMPLETE_TRUNK_FIT_INCREASES_HAND_PAIRS':'The correction would increase torso crossings for at least one hand. Original motion is retained.',
        'COMPLETE_TRUNK_FIT_UNAVAILABLE':'A complete torso-surface comparison was unavailable. Original motion is retained.',
        'COMPLETE_TRUNK_FIT_COVERAGE_CHANGED':'The complete torso comparison no longer covers the visible motion. Original motion is retained.',
        'COMPLETE_TRUNK_FIT_EVIDENCE_CHANGED':'Torso-surface evidence changed before publication. Original motion is retained.',
        'COMPLETE_TRUNK_FIT_COMPARISON_CHANGED':'The torso-surface comparison changed before publication. Original motion is retained.',
        'ENCLOSURE_FIT_INTRODUCES_BURIED_SKIN':'The correction would bury new hand areas inside the torso. Original motion is retained.',
        'ENCLOSURE_FIT_INTRODUCES_UNCERTAINTY':'The correction creates new hand areas whose torso clearance cannot be determined. Original motion is retained.',
        'ENCLOSURE_FIT_UNAVAILABLE':'A complete torso-enclosure comparison was unavailable. Original motion is retained.',
        'ENCLOSURE_FIT_EVIDENCE_CHANGED':'Torso-enclosure evidence changed before publication. Original motion is retained.',
        'NO_BOUNDED_HAND_CONTACT_CANDIDATE_FOUND':'No arm and wrist correction cleared these crossings without creating new body-contact areas within the current limits. Original motion is retained.',
        'SEED_COMPLETE_BODY_CONSTRAINTS_UNAVAILABLE':'The starting correction did not have complete body-contact measurements. Original motion is retained.',
        'FRESH_SEED_BODY_REPRODUCTION_FAILED':'The final body-contact check did not reproduce. Original motion is retained.',
        'NO_BOUNDED_AREA_CONTACT_CANDIDATE_FOUND':'No candidate cleared the hand/arm crossings without creating new body-contact areas within the current limits. The original motion was retained.',
        'COMPLETE_STABLE_BODY_AREAS_REQUIRED':'A complete original head/body area review was unavailable. The original motion was retained.',
        'BODY_FIT_INTRODUCES_CONTACT_AREAS':'The candidate would move hand/body crossings onto new surface areas. The original motion was retained.',
        'BODY_FIT_INCREASES_HAND_PAIRS':'The candidate would increase hand/body crossings on at least one frame. The original motion was retained.',
        'BODY_FIT_AREAS_UNAVAILABLE':'A complete head/body contact comparison was unavailable. The original motion was retained.',
        'NO_CHECKED_CROSSINGS':'The original has no checked hand/arm crossings. No fitting was applied.',
        'MULTIPLE_CONTACTING_HANDS_UNSUPPORTED':'Both hands need correction. This fitter currently supports one hand at a time.',
        'CONTACT_AT_FIXED_ENDPOINT':'This clip needs a correction at its first or last pose. This fitter keeps those endpoint poses unchanged.',
        'CONTACT_INTERVAL_EXCEEDS_CANDIDATE_BUDGET':'The affected interval is too long for this bounded search. Original motion is retained.',
        'CANDIDATE_POSE_BUDGET_EXCEEDED':'The bounded search reached its evaluation limit. Original motion is retained.',
        'CANDIDATE_TRIAL_BUDGET_EXCEEDED':'The bounded search reached its trial limit. Original motion is retained.',
        'NO_BOUNDED_CONTACT_CANDIDATE_FOUND':'No candidate cleared these crossings within the current joint, skin and displacement limits. Original motion is retained.',
        'COMPLETE_SURFACE_REVIEW_REQUIRED':'Complete hand/arm measurements are unavailable. Load verified original motion before fitting.',
    }
    for code,message in reasons.items():
        if code in error:return message
    if 'cancelled' in error.lower():return 'Fitting was cancelled. The original motion was not replaced.'
    return 'Fitting stopped before a comparison was published. Reload the original motion to try again.'


def show_contact_error(window,error: str):
    from PySide6.QtWidgets import QMessageBox
    message=fit_error_message(error)
    window.log.setPlainText(message+'\n\nLocal diagnostic details:\n'+error[:100000])
    window.statusBar().showMessage('Fitting stopped')
    dialog=QMessageBox(window);dialog.setWindowTitle('UCC fitting stopped');dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText(message);dialog.setDetailedText(error[:100000]);dialog.exec()


def start_contact_fit(window):
    if window.jobs.busy:window._error('Another local task is still running');return
    preview=window._native_review;playback=window._native_playback;controller=window.controller
    if preview is None or playback is None or controller.store is None or controller.dirty:
        window._error('Load verified original motion on the saved character before fitting');return
    pane=window.animations
    if not pane.local_preview_review.isChecked():window._error('Confirm local animation preview rights first');return
    try:
        executable=window._blender_executable
        if executable is None or executable.is_symlink() or not executable.is_file():
            raise ValidationError('Select Blender and repeat the original body preview')
        permission=LicensePolicy(pane.provider.text().strip(),pane.license.text().strip(),pane.uri.text().strip(),
                                 reviewed=True,local_preview_allowed=True,no_ai=True)
        store=controller.store;source=Path(pane.selected.text());cancel=Event();worker=bundled_worker_path()
        window._submit('fitted_comparison',lambda:fit_measured_contacts(store,preview,playback,source_fbx=source,
            permission=permission,blender_exe=executable,worker_script=worker,cancel=cancel),cancel=cancel)
        window.log.setPlainText('TRYING A BOUNDED LOCAL HAND/ARM FIT\n'
            'The original animation stays available. Original head/body review, bounded arm and wrist search, saved-scene verification, targeted renders and final body comparison can take tens of minutes.\n'
            'Cancel from the Character menu. Unsupported contacts or failed joint/skin checks keep the original motion.\n'
            'A generated candidate changes target motion; it does not approve grasp intent, visual quality or engine compatibility.')
    except (UCCError,OSError,ValueError) as error:window._error(str(error))


def publish_fitted_result(window,result):
    from .native_playback import publish_comparison
    from .body_contact_review import publish_body_contact_review
    from ucc.jobs.body_fit_guard import require_body_fit_guard
    from ucc.jobs.enclosure_fit_guard import require_enclosure_fit_guard
    from ucc.jobs.complete_trunk_fit_guard import require_complete_trunk_fit_guard
    if result.candidate_job_id:
        if result.body_review is None or result.body_fit_guard!=require_body_fit_guard(result.body_review):
            raise ValidationError('Automatic fit lacks its verified central-body guard')
        if result.enclosure_fit_guard!=require_enclosure_fit_guard(result.body_review):
            raise ValidationError('Automatic fit lacks its verified trunk-enclosure guard')
        if result.complete_trunk_fit_guard!=require_complete_trunk_fit_guard(result.body_review):
            raise ValidationError('Automatic fit lacks its verified complete torso-surface guard')
    publish_comparison(window,result.original,result.fitted)
    if result.body_review is not None:
        try:publish_body_contact_review(window,result.body_review)
        except Exception:
            window._clear_native_review();raise
