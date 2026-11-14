"""Dependency-free desktop session controller: real project persistence, no fake 3D changes.

Qt is intentionally absent. UI tests and pure-Python tests share this object so
save/conflict/undo semantics cannot silently diverge from the CLI core.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ucc.core.commands import CharacterSession
from ucc.core.errors import ValidationError
from ucc.core.models import CharacterProject, MORPH_LIMITS
from ucc.core.storage import PROJECT_FILE, ProjectStore


@dataclass(frozen=True, slots=True)
class ProjectView:
    name: str
    folder: str
    revision: int
    dirty: bool
    geometry_state: str
    rig_profile: str | None
    master_blend: str | None
    morphs: tuple[tuple[str, float], ...]
    part_count: int
    animation_count: int
    blockers: tuple[str, ...]
    can_undo: bool
    can_redo: bool
    facial_parameters: tuple[tuple[str, float], ...] = ()


class DesktopController:
    """One open editable project; explicit saves and optimistic conflict detection."""

    def __init__(self) -> None:
        self.store: ProjectStore | None = None
        self.session: CharacterSession | None = None
        self._saved_revision: int | None = None
        self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def has_project(self) -> bool:
        return self.store is not None and self.session is not None

    def create(self, directory: Path | str, name: str) -> ProjectView:
        root = Path(directory).expanduser()
        if root.is_symlink() or (root.exists() and not root.is_dir()):
            raise ValidationError("Project destination is not a regular directory")
        # Never populate a preexisting nonempty directory without an explicit open.
        if root.exists() and any(root.iterdir()):
            raise ValidationError("Project folder is not empty; select a new/empty folder")
        store = ProjectStore(root)
        saved = store.save(CharacterProject.new(name))
        self._attach(store, saved)
        return self.view()

    def open(self, directory: Path | str) -> ProjectView:
        store = ProjectStore(directory)
        loaded = store.load()  # No mutation of unknown/newer schemas or broken files.
        self._attach(store, loaded)
        return self.view()

    def _attach(self, store: ProjectStore, project: CharacterProject) -> None:
        self.store = store
        self.session = CharacterSession(project)
        self._saved_revision = project.revision
        self._dirty = False

    def require_project(self) -> CharacterProject:
        if self.session is None:
            raise ValidationError("Create or open a character project first")
        return self.session.project

    def rename(self, name: str) -> ProjectView:
        session = self._get_session()
        previous = session.project
        session.rename(name)
        self._dirty |= session.project != previous
        return self.view()

    def set_morph(self, name: str, value: float) -> ProjectView:
        if name not in MORPH_LIMITS:
            raise ValidationError("Unknown morph parameter; MPFB mapping is unverified")
        session = self._get_session()
        previous = session.project
        session.set_morph(name, value)
        self._dirty |= session.project != previous
        return self.view()

    def undo(self) -> ProjectView:
        self._get_session().undo()
        self._dirty = True
        return self.view()

    def set_face_parameter(self, name: str, value: float) -> ProjectView:
        session = self._get_session()
        previous = session.project
        session.set_face_parameter(name, value)
        self._dirty |= previous != session.project
        return self.view()

    def accept_saved_master(self, saved: CharacterProject) -> ProjectView:
        if self.store is None or self._dirty or self.store.load() != saved:
            raise ValidationError('Saved master cannot replace a changed or unsaved desktop session')
        self._get_session().accept_saved_master(saved)
        self._saved_revision = saved.revision
        return self.view()

    def redo(self) -> ProjectView:
        self._get_session().redo()
        self._dirty = True
        return self.view()

    def save(self) -> ProjectView:
        if self.store is None or self._saved_revision is None:
            raise ValidationError("No project is open")
        session = self._get_session()
        if not self._dirty:
            return self.view()
        saved = self.store.save(session.project, expected_revision=self._saved_revision)
        self._saved_revision = saved.revision
        self._dirty = False
        return self.view()

    def master_path(self) -> Path:
        project = self.require_project()
        if self.store is None or project.master_blend is None:
            raise ValidationError("Project has no staged .blend master to open")
        path = self.store.root / project.master_blend
        resolved = path.resolve(strict=True)
        if path.is_symlink() or not resolved.is_relative_to(self.store.root):
            raise ValidationError("Master file path has been redirected")
        if not resolved.is_file() or resolved.suffix.lower() != ".blend":
            raise ValidationError("Project master file is missing or invalid")
        return resolved

    def view(self) -> ProjectView:
        project = self.require_project()
        assert self.store is not None and self.session is not None
        return ProjectView(
            project.name, str(self.store.root), project.revision, self._dirty,
            project.geometry_state, project.rig_profile, project.master_blend,
            tuple(sorted(project.parameters)), len(project.parts), len(project.animations),
            project.export_readiness(), self.session.can_undo, self.session.can_redo,
            tuple(project.facial_parameters),
        )

    def _get_session(self) -> CharacterSession:
        if self.session is None:
            raise ValidationError("No character project selected")
        return self.session
