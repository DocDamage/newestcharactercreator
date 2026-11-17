"""Keep unsupported derivative jobs from discarding registered-source authority."""
from ucc.core.errors import ValidationError


def require_manual_native_source(*results: object) -> None:
    if any(getattr(result, 'source_authority', None) is not None for result in results):
        raise ValidationError(
            'Registered-source fitting and additional contact reviews are unavailable '
            'in this read-only preview; the admitted source is retained unchanged')
