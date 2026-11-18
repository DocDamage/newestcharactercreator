"""Closed original-idle worker envelope; no file access or runtime imports."""
from ucc.core.errors import ValidationError


OPERATIONS = frozenset({
    'inspect_authored_idle_target',
    'author_original_idle_source',
    'verify_authored_idle_source',
})


def validate_job(operation: str, input_project: str | None, options: object) -> None:
    """Reject arbitrary inputs, path options and incomplete phase bindings."""
    fields = {'request_sha256'}
    if operation == 'verify_authored_idle_source':
        fields |= {'review_sha256', 'source_sha256', 'recipe_sha256'}
    if (type(operation) is not str or operation not in OPERATIONS
            or type(input_project) is not str or input_project != 'candidate.blend'
            or type(options) is not dict or set(options) != fields):
        raise ValidationError('Original idle requires a closed phase and candidate input')
    for value in options.values():
        if (type(value) is not str or len(value) != 64
                or any(c not in '0123456789abcdef' for c in value)):
            raise ValidationError('Original idle requires exact lowercase SHA256 bindings')
