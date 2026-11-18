"""Closed authoring and independent reopen contracts for the private MPFB walk."""
from hashlib import sha256

from ucc.core.authored_idle import PROFILE, AuthoredIdleInspectionRequest
from ucc.core.errors import ValidationError
from ucc.core.target_action_format import canonical_bytes, checked_sha, read_document, require


AUTHOR = 'author_original_walk_source'
VERIFY = 'verify_authored_walk_source'
OPERATIONS = frozenset({AUTHOR, VERIFY})
INTENT = 'walk_authoring_request.json'
POLICY = 'UCC_PRIVATE_ORIGINAL_WALK_INTENT_V1'
INPUT_BINDINGS = {
    'candidate.blend': 'master_sha256',
    'project.ucc.json': 'project_sha256',
    'idle_anatomical_frame.json': 'anatomy_sha256',
    'idle_inspection_request.json': 'request_sha256',
    INTENT: 'walk_request_sha256',
}
REOPEN_BINDINGS = {'original_walk.blend': 'review_sha256', 'original_walk.fbx': 'source_sha256'}


def validate_job(operation: str, input_project: str | None, options: object) -> None:
    fields = set(INPUT_BINDINGS.values())
    if operation == VERIFY:
        fields.update(REOPEN_BINDINGS.values())
    if (type(operation) is not str or operation not in OPERATIONS
            or type(input_project) is not str or input_project != 'candidate.blend'
            or type(options) is not dict or set(options) != fields):
        raise ValidationError('Original walk requires a closed phase and candidate input')
    for value in options.values():
        checked_sha(value)


def walk_intent(inspection: AuthoredIdleInspectionRequest, anatomy_sha256: str) -> dict:
    """Bind the explicitly selected original walk to the measured part-free rig."""
    require(type(inspection) is AuthoredIdleInspectionRequest and inspection.profile == PROFILE
            and not inspection.project.parts,
            'Original walk requires the saved part-free MPFB character')
    return {
        'schema_version': 1,
        'policy': POLICY,
        'inspection_request_sha256': inspection.sha256,
        'project_sha256': sha256(inspection.project_snapshot_json).hexdigest(),
        'master_sha256': inspection.to_dict()['consumed_sources']['master_and_derived_rig'],
        'anatomy_sha256': checked_sha(anatomy_sha256),
        'private_original_walk_confirmed': True,
    }


def read_walk_intent(payload: bytes, options: dict, inspection: AuthoredIdleInspectionRequest) -> dict:
    value = read_document(payload)
    expected = walk_intent(inspection, options['anatomy_sha256'])
    require(payload == canonical_bytes(expected)
            and sha256(payload).hexdigest() == options['walk_request_sha256']
            and expected['inspection_request_sha256'] == options['request_sha256']
            and expected['project_sha256'] == options['project_sha256']
            and expected['master_sha256'] == options['master_sha256'],
            'Original walk intent differs from the exact inspection, source or measured rig')
    return value
