"""Typed errors for domain logic; never hide a failed validation."""


class UCCError(Exception):
    """Base UCC error."""


class ValidationError(UCCError):
    """Untrusted or incompatible data."""


class CompatibilityError(ValidationError):
    """Part/slot/family/rig compatibility mismatch."""


class ProjectConflict(UCCError):
    """Stored revision differs from the caller's expected revision."""


class ProjectStorageError(UCCError):
    """A project could not safely be read/written."""
