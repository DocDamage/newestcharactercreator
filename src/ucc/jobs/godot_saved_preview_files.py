"""Same-buffer saved-proof reads and immutable cross-file ownership fences."""
from pathlib import Path
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from .godot_registered_runtime_files import read_bytes, read_metadata, hash_file
from .godot_candidate_inputs import identity
from .target_action_context import Budget, protected
from .target_action_storage import ancestry


class ProofReads:
    def __init__(self, budget: Budget):
        self.budget = budget
        self.records: dict[Path, tuple[tuple[int,int,int,int], str, int]] = {}
        self.authority: dict[Path, tuple[int,int,int,int]] = {}

    def capture(self, path: Path, maximum: int, expected: str | None = None) -> bytes:
        path=protected(Path(path)); stamp=identity(path)
        if path.stat().st_nlink!=1:
            raise ProjectStorageError('Saved proof file is not single-link')
        raw,digest=read_bytes(path,maximum,self.budget,expected_sha256=expected)
        if identity(protected(path))!=stamp or path.stat().st_nlink!=1:
            raise ProjectStorageError('Saved proof changed while capturing bytes')
        value=(stamp,digest,len(raw))
        if path in self.records and self.records[path]!=value:
            raise ProjectStorageError('Saved proof changed between reads')
        self.records[path]=value
        for parent,value in ancestry((path,)).items():
            if parent in self.authority and self.authority[parent]!=value:
                raise ProjectStorageError('Saved proof ancestry changed between reads')
            self.authority[parent]=value
        return raw

    def metadata(self, path: Path, maximum: int, expected: str | None = None) -> dict:
        import json
        from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
        raw=self.capture(path,maximum,expected)
        try:
            value=json.loads(raw.decode('utf-8'),object_pairs_hook=_unique_project_fields,
                             parse_constant=_nonfinite_project_number)
        except (ValueError,UnicodeError,RecursionError) as error:
            raise ValidationError('Malformed selected saved-preview metadata') from error
        if type(value) is not dict:
            raise ValidationError('Saved-preview metadata must be an object')
        canonical_bytes(value)
        return value

    def record(self, path: Path, maximum: int, expected: str | None = None) -> None:
        path=protected(Path(path));stamp=identity(path)
        if path.stat().st_nlink!=1:
            raise ProjectStorageError('Saved proof file is not single-link')
        digest,size=hash_file(path,maximum,self.budget)
        if identity(protected(path))!=stamp or expected is not None and digest!=expected:
            raise ProjectStorageError('Saved proof bytes or identity changed')
        value=(stamp,digest,size)
        if path in self.records and self.records[path]!=value:
            raise ProjectStorageError('Saved proof changed between reads')
        self.records[path]=value
        for parent,value in ancestry((path,)).items():
            if parent in self.authority and self.authority[parent]!=value:
                raise ProjectStorageError('Saved proof ancestry changed between reads')
            self.authority[parent]=value

    def check(self, budget: Budget | None = None) -> None:
        budget=budget or self.budget
        for path,stamp in self.authority.items():
            budget.check()
            if identity(protected(path))!=stamp:
                raise ProjectStorageError('Saved proof ancestry or file identity changed')
        for path,(stamp,digest,size) in self.records.items():
            budget.check()
            if (identity(protected(path))!=stamp or path.stat().st_nlink!=1
                    or hash_file(path,size,budget)!=(digest,size)):
                raise ProjectStorageError('Saved preview proof changed after validation')
        for path,stamp in self.authority.items():
            if identity(protected(path))!=stamp:
                raise ProjectStorageError('Saved proof identity changed during final guard')
