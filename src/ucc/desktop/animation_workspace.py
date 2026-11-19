"""Catalog browser and embedded motion viewport for the Animation library tab."""
from weakref import WeakSet

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid


STYLE = """
#animationWorkspace { background: #101820; color: #dae7ec; }
#animationWorkspace QFrame#animationBrowser, #animationWorkspace QFrame#animationPreview {
    background: #17232e; border: 1px solid #30414e; border-radius: 9px;
}
#animationWorkspace QLabel { color: #dae7ec; background: transparent; }
#animationWorkspace QLabel[plainSecondary="true"] { color: #a4b8c6; }
#animationWorkspace QLabel[workspaceHeading="true"] { font-size: 16px; font-weight: 650; }
#animationWorkspace QLineEdit, #animationWorkspace QTableWidget {
    background: #101a23; color: #e0e9ed; border: 1px solid #3b4b59; border-radius: 5px;
    selection-background-color: #294b56; selection-color: #f3fbfb;
}
#animationWorkspace QLineEdit { padding: 6px 9px; }
#animationWorkspace QLineEdit:focus, #animationWorkspace QTableWidget:focus {
    border-color: #7bc6ba;
}
#animationWorkspace QTableWidget { gridline-color: #293946; }
#animationWorkspace QTableWidget::item { padding-left: 6px; }
#animationWorkspace QHeaderView::section {
    background: #1d2c38; color: #bfced8; border: none;
    border-bottom: 1px solid #394b5a; padding: 6px;
}
#animationWorkspace QSplitter::handle { background: transparent; }
#animationWorkspace QSplitter::handle:hover { background: #3d6570; }
#animationWorkspace QWidget#animationViewport, #animationWorkspace QLabel#animationEmptyPreview {
    background: #0a121a; border-radius: 5px; color: #9db0bc;
}
#animationWorkspace QPushButton[workspaceButton="true"] {
    background: #223441; color: #ecf3f5; border: 1px solid #435766;
    border-radius: 5px; padding: 6px 9px;
}
#animationWorkspace QPushButton[workspaceButton="true"]:hover { background: #304a59; }
#animationWorkspace QPushButton#animationPreviewClip {
    background: #87d4bd; color: #0c2923; font-weight: 700; border: 1px solid #a5e2d0;
    border-radius: 5px; padding: 7px 12px;
}
#animationWorkspace QPushButton#animationPreviewClip:hover { background: #a2e7d2; }
#animationWorkspace QPushButton#animationPreviewClip:disabled,
#animationWorkspace QPushButton[workspaceButton="true"]:disabled {
    background: #25343e; color: #98aab5; border-color: #3e505b;
}
#animationWorkspace QPushButton:focus { border: 1px solid #b9e9df; }
#animationWorkspace QWidget[workspacePlayback="true"] QPushButton {
    background: #20313e; color: #e6f1f4; border: 1px solid #455967;
    border-radius: 5px; padding: 5px 9px;
}
#animationWorkspace QWidget[workspacePlayback="true"] QPushButton:hover,
#animationWorkspace QWidget[workspacePlayback="true"] QPushButton:checked { background: #304a59; }
#animationWorkspace QWidget[workspacePlayback="true"] QPushButton[primary="true"] {
    background: #87d4bd; color: #0c2923; font-weight: 700; border-color: #a5e2d0;
}
#animationWorkspace QWidget[workspacePlayback="true"] QPushButton:disabled {
    background: #25343e; color: #98aab5;
}
#animationWorkspace QWidget[workspacePlayback="true"] QCheckBox { color: #dae7ec; spacing: 6px; }
#animationWorkspace QWidget[workspacePlayback="true"] QSlider::groove:horizontal {
    height: 4px; background: #30414e; border-radius: 2px;
}
#animationWorkspace QWidget[workspacePlayback="true"] QSlider::sub-page:horizontal {
    background: #87d4bd; border-radius: 2px;
}
#animationWorkspace QWidget[workspacePlayback="true"] QSlider::handle:horizontal {
    width: 13px; margin: -5px 0; background: #a5e2d0; border-radius: 6px;
}
"""


def _caption(text: str, *, heading: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setProperty("workspaceHeading" if heading else "plainSecondary", True)
    return label


class AnimationWorkspace(QWidget):
    """Arrange the catalog and share one viewport between a character and its motion."""

    def __init__(self, catalog: QTableWidget, refresh: QPushButton) -> None:
        super().__init__()
        self.setObjectName("animationWorkspace")
        self.setStyleSheet(STYLE)
        self.catalog = catalog
        self._mounted: QWidget | None = None
        self._character: QWidget | None = None
        self._observed_widgets: WeakSet[QWidget] = WeakSet()
        self._viewport_refresh = QTimer(self)
        self._viewport_refresh.setSingleShot(True)
        self._viewport_refresh.timeout.connect(self._sync_viewport)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        split.addWidget(self._browser(refresh))
        split.addWidget(self._preview())
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([410, 580])
        layout.addWidget(split)

        catalog.currentCellChanged.connect(self._show_selection)
        self.search.textChanged.connect(self.filter_catalog)
        self.filter_catalog()

    def _browser(self, refresh: QPushButton) -> QWidget:
        pane = QFrame()
        pane.setObjectName("animationBrowser")
        pane.setMinimumWidth(302)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.addWidget(_caption("Local sources", heading=True), 1)
        refresh.setProperty("workspaceButton", True)
        header.addWidget(refresh)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setAccessibleName("Search animation sources")
        self.search.setPlaceholderText("Search sources…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self.catalog.setAccessibleName("Local animation sources")
        self.catalog.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.catalog.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.catalog.setShowGrid(False)
        self.catalog.verticalHeader().hide()
        self.catalog.verticalHeader().setDefaultSectionSize(29)
        columns = self.catalog.horizontalHeader()
        columns.setStretchLastSection(False)
        columns.setMinimumSectionSize(45)
        columns.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, self.catalog.columnCount()):
            columns.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.catalog, 1)

        footer = QHBoxLayout()
        self.source_count = _caption("")
        footer.addWidget(self.source_count, 1)
        self.advanced_tools = QPushButton("Import && review…")
        self.advanced_tools.setProperty("workspaceButton", True)
        self.advanced_tools.setToolTip("Index file sources, review local licenses, and attach references")
        footer.addWidget(self.advanced_tools)
        layout.addLayout(footer)
        return pane

    def _preview(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("animationPreview")
        pane.setMinimumWidth(350)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        header.addWidget(_caption("Motion preview", heading=True), 1)
        self.show_character = QPushButton("Show character")
        self.show_character.setProperty("workspaceButton", True)
        self.show_character.setToolTip("Load the saved character for local preview.")
        self.show_character.setEnabled(False)
        header.addWidget(self.show_character)
        self.preview_clip = QPushButton("Preview on character")
        self.preview_clip.setToolTip("Preview locally on the saved character after reviewing the source.")
        self.preview_clip.setObjectName("animationPreviewClip")
        self.preview_clip.setEnabled(False)
        header.addWidget(self.preview_clip)
        layout.addLayout(header)

        self.catalog_selection_label = _caption("")
        self.catalog_selection_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.catalog_selection_label.setWordWrap(True)
        layout.addWidget(self.catalog_selection_label)

        self._viewport = QWidget()
        self._viewport.setObjectName("animationViewport")
        self._viewport.setMinimumHeight(280)
        self._stack = QStackedLayout(self._viewport)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self._backdrop = QWidget()
        self._backdrop_stack = QStackedLayout(self._backdrop)
        self._backdrop_stack.setContentsMargins(0, 0, 0, 0)
        self._backdrop_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self._empty_preview = _caption("Open a character with a saved Blender master, then select Show character.")
        self._empty_preview.setObjectName("animationEmptyPreview")
        self._empty_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_preview.setWordWrap(True)
        self._empty_preview.setContentsMargins(20, 12, 20, 12)
        self._backdrop_stack.addWidget(self._empty_preview)
        self._stack.addWidget(self._backdrop)
        layout.addWidget(self._viewport, 1)

        self.preview_status = _caption("Select a source to check preview availability.")
        self.preview_status.setWordWrap(True)
        layout.addWidget(self.preview_status)
        return pane

    def selected_asset_id(self) -> str | None:
        row = self.catalog.currentRow()
        if row < 0 or self.catalog.isRowHidden(row):
            return None
        item = self.catalog.item(row, 0)
        return item.text() if item is not None else None

    def filter_catalog(self, *_change) -> None:
        query = self.search.text().casefold().replace("_", " ").split()
        shown = 0
        total = self.catalog.rowCount()
        for row in range(total):
            values = (
                self.catalog.item(row, col).text()
                for col in range(self.catalog.columnCount())
                if self.catalog.item(row, col) is not None
            )
            text = " ".join(values).casefold().replace("_", " ")
            matches = all(word in text for word in query)
            self.catalog.setRowHidden(row, not matches)
            shown += matches
        selected = self.catalog.currentRow()
        if selected >= 0 and self.catalog.isRowHidden(selected):
            self.catalog.clearSelection()
            self.catalog.setCurrentCell(-1, -1)
        count = str(total) if shown == total else f"{shown} of {total}"
        self.source_count.setText(f"{count} {'source' if total == 1 else 'sources'}")
        self._show_selection()

    def _show_selection(self, *_change) -> None:
        asset = self.selected_asset_id()
        self.catalog_selection_label.setText(asset or "No source selected")
        self.catalog_selection_label.setToolTip(asset or "")

    def set_preview_available(self, enabled: bool, reason: str = "") -> None:
        self.preview_clip.setEnabled(enabled)
        if not reason:
            reason = ("Ready for local preview on the saved character." if enabled else
                      "Select a reviewed source to check preview availability.")
        self.preview_status.setText(reason)

    def mount_character(self, widget: QWidget | None) -> None:
        if widget is not self._character:
            old, self._character = self._character, widget
            self._remove_widget(old, self._backdrop_stack)
            if widget is not None:
                self._backdrop_stack.addWidget(widget)
                self._observe_widget(widget)
        if widget is not None:
            widget.show()
        self._sync_viewport()

    def mount_motion(self, widget: QWidget | None) -> None:
        if widget is not self._mounted:
            old, self._mounted = self._mounted, widget
            self._remove_widget(old, self._stack)
            if widget is not None:
                if isinstance(widget, QDockWidget):
                    widget.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
                    if widget.titleBarWidget() is None:
                        empty_title = QWidget(widget)
                        empty_title.setFixedHeight(0)
                        widget.setTitleBarWidget(empty_title)
                self._stack.addWidget(widget)
                self._observe_widget(widget)
        if widget is not None:
            widget.show()
        self._sync_viewport()

    def _remove_widget(self, widget: QWidget | None, layout: QStackedLayout) -> None:
        if widget is not None and isValid(widget):
            widget.hide()
            layout.removeWidget(widget)

    def _observe_widget(self, widget: QWidget) -> None:
        if widget not in self._observed_widgets:
            self._observed_widgets.add(widget)
            widget.installEventFilter(self)
            widget.destroyed.connect(self._schedule_viewport_refresh)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (watched is self._mounted or watched is self._character) and event.type() in {
            QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.ShowToParent, QEvent.Type.HideToParent,
        }:
            self._schedule_viewport_refresh()
        return super().eventFilter(watched, event)

    @Slot()
    def _schedule_viewport_refresh(self) -> None:
        self._viewport_refresh.start(0)

    def _sync_viewport(self) -> None:
        if self._mounted is not None and not isValid(self._mounted):
            self._mounted = None
        if self._character is not None and not isValid(self._character):
            self._character = None

        character = self._character
        has_character = character is not None and not character.isHidden()
        self._backdrop_stack.setCurrentWidget(character if has_character else self._empty_preview)
        self._empty_preview.setVisible(not has_character)
        motion = self._mounted
        if motion is not None and not motion.isHidden():
            self._stack.setCurrentWidget(motion)
            self._backdrop.hide()
        else:
            self._stack.setCurrentWidget(self._backdrop)
            self._backdrop.show()
