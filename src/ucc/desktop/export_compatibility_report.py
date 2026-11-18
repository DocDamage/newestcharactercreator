"""Display the scope of an export already authenticated by its desktop workflow."""

from enum import Enum
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)


class ExportProfile(Enum):
    GODOT = 'Godot'
    UNITY = 'Unity'
    UNREAL = 'Unreal'


_SCOPES = {
    ExportProfile.GODOT: (
        'Godot reopened the saved static scene. The checks covered the rig, facial shapes, UVs '
        'and saved skin material.'
    ),
    ExportProfile.UNITY: (
        'Unity reopened the saved scene and verified GPU deformation diagnostics for the tested '
        'rig and facial shapes.'
    ),
    ExportProfile.UNREAL: (
        'Unreal reopened the saved static scene. The checks covered the rig, morphs, materials '
        'and source parity. Shader compilation, GPU rendering and Play In Editor were not tested.'
    ),
}

_CHECKS = (
    ('Export files', 'Generated'),
    ('Offline checks', 'Verified'),
    ('Engine import and reopen', 'Verified'),
    ('Animation playback', 'Not tested'),
    ('Player build', 'Not tested'),
    ('Visual quality', 'Not reviewed'),
    ('Distribution rights', 'Not reviewed'),
)


class ExportCompatibilityReport(QDialog):
    def __init__(self, profile: ExportProfile, destination: Path, parent: QWidget):
        super().__init__(parent)
        self.setObjectName('exportCompatibilityReport')
        self.setWindowTitle('Export quality and compatibility')
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'{profile.value} private character export'))

        path_label = QLabel('Export folder')
        path = QLineEdit(str(destination))
        path.setObjectName('exportCompatibilityDestination')
        path.setReadOnly(True)
        path_label.setBuddy(path)
        layout.addWidget(path_label)
        layout.addWidget(path)

        details = QTreeWidget()
        details.setObjectName('exportCompatibilityDetails')
        details.setAccessibleName('Export compatibility checks')
        details.setHeaderLabels(['Check', 'Status'])
        details.setRootIsDecorated(False)
        details.setUniformRowHeights(True)
        details.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        details.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for check, status in _CHECKS:
            details.addTopLevelItem(QTreeWidgetItem([check, status]))
        layout.addWidget(details)

        scope = QLabel(_SCOPES[profile])
        scope.setObjectName('exportCompatibilityScope')
        scope.setWordWrap(True)
        layout.addWidget(scope)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.setObjectName('exportCompatibilityButtons')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def show_export_compatibility(window: QWidget, profile: ExportProfile, destination: Path) -> None:
    """Show the latest confirmed result without blocking the desktop."""
    report = ExportCompatibilityReport(profile, destination, window)
    previous = getattr(window, '_export_compatibility_report', None)
    if previous is not None:
        previous.close()
        previous.deleteLater()
    window._export_compatibility_report = report
    report.show()
