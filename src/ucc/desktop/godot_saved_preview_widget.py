"""Display captured private debug previews without filesystem or engine access."""
from __future__ import annotations

from hashlib import sha256
import math
import struct

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ucc.core.errors import ValidationError

from ucc.export.godot_saved_preview import CapturedPreviewFrame, LoadedSavedGodotPreview


FRAMES = (1, 150, 300)


def _captured_image(frame: CapturedPreviewFrame) -> QImage:
    if type(frame) is not CapturedPreviewFrame:
        raise ValidationError("Captured preview requires an immutable frame record.")
    raw = frame.png_bytes
    if (type(raw) is not bytes or not 33 <= len(raw) <= 2 * 1024 * 1024
            or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR"
            or struct.unpack(">II", raw[16:24]) != (512, 512)):
        raise ValidationError("Captured preview must be a bounded 512 by 512 PNG.")
    image = QImage.fromData(raw, "PNG")
    if image.isNull() or (image.width(), image.height()) != (512, 512):
        raise ValidationError("Captured preview PNG could not be decoded.")
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    rgba = bytes(image.constBits())
    if (len(rgba) != 512 * 512 * 4 or type(frame.rgba_sha256) is not str
            or sha256(rgba).hexdigest() != frame.rgba_sha256):
        raise ValidationError("Captured preview decoded pixel hash differs from its verified evidence.")
    error = frame.max_normal_vector_error
    if type(error) not in (float, int) or not math.isfinite(error) or not 0 <= error <= 0.0002:
        raise ValidationError("Captured normal error is outside the private debug limit.")
    return image


class SavedGodotPreviewDialog(QDialog):
    """A view of immutable captured bytes; the controller owns live revalidation."""

    closed = Signal()

    def __init__(self, loaded: LoadedSavedGodotPreview, parent: QWidget | None = None) -> None:
        if type(loaded) is not LoadedSavedGodotPreview:
            raise ValidationError("Select a loaded saved preview record.")
        super().__init__(parent)
        self.setWindowTitle("Saved private Godot debug preview")
        self._loaded: LoadedSavedGodotPreview | None = loaded
        self._frames: dict[int, CapturedPreviewFrame] = {}
        self._images: dict[int, QImage] = {}
        self._closed_notified = False
        self.current_frame: int | None = None
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(512, 512)
        layout.addWidget(self.image_label)
        controls = QHBoxLayout()
        self.frame_buttons: dict[int, QPushButton] = {}
        for frame in FRAMES:
            button = QPushButton(f"Frame {frame}")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=frame: self.select_frame(value))
            controls.addWidget(button)
            self.frame_buttons[frame] = button
        layout.addLayout(controls)
        self.facts = QLabel()
        self.facts.setTextFormat(Qt.TextFormat.PlainText)
        self.facts.setWordWrap(True)
        layout.addWidget(self.facts)
        self.proofs = QLabel()
        self.proofs.setTextFormat(Qt.TextFormat.PlainText)
        self.proofs.setWordWrap(True)
        layout.addWidget(self.proofs)
        self.scope = QLabel(
            "Private debug readbacks only. All broader approval flags remain false. "
            "No appearance, artist, performance, VRAM, delivery, shipping or source-rights approval.")
        self.scope.setTextFormat(Qt.TextFormat.PlainText)
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button)
        try:
            if type(loaded.frames) is not tuple or len(loaded.frames) != len(FRAMES):
                raise ValidationError("Captured preview requires exactly frames 1, 150 and 300.")
            for frame in loaded.frames:
                if (type(frame) is not CapturedPreviewFrame or type(frame.frame) is not int
                        or frame.frame not in FRAMES or frame.frame in self._frames):
                    raise ValidationError("Captured preview frame identities differ.")
                self._images[frame.frame] = _captured_image(frame)
                self._frames[frame.frame] = frame
            self.proofs.setText(
                f"Saved clip: {loaded.selection.clip_id}; revision: {loaded.selection.revision}. "
                f"Draw proof: {loaded.draw_receipt.sha256}; body proof: {loaded.body_receipt.sha256}; "
                f"retained input manifest: {loaded.retained_manifest.sha256}.")
            self.select_frame(1)
        except ValidationError as error:
            self.clear_preview(str(error))

    def select_frame(self, frame: int) -> None:
        """Switch among already decoded, hash-checked captured images."""
        if type(frame) is not int or frame not in self._frames or self._loaded is None:
            return
        captured = self._frames[frame]
        self.image_label.setPixmap(QPixmap.fromImage(self._images[frame]))
        self.current_frame = frame
        for number, button in self.frame_buttons.items():
            button.setChecked(number == frame)
        self.status.setText(f"Saved private debug draw {self._loaded.draw_id} - frame {frame}")
        self.facts.setText(
            f"Captured 512 x 512 RGBA image; occupied pixels: {captured.opaque_pixels}; "
            f"occupied bounds: {captured.opaque_bounds}; maximum normal vector error: "
            f"{captured.max_normal_vector_error:.12g}. Positions, UVs and indices verified by the saved draw proof.")

    def clear_preview(self, message: str) -> None:
        """Drop captured bytes, decoded pixels and proof references immediately."""
        self.image_label.clear()
        self.facts.clear()
        self.proofs.clear()
        self._images.clear()
        self._frames.clear()
        self._loaded = None
        self.current_frame = None
        for button in self.frame_buttons.values():
            button.setEnabled(False)
            button.setChecked(False)
        self.status.setText(message)

    def _notify_closed(self) -> None:
        self.clear_preview("Preview closed.")
        if not self._closed_notified:
            self._closed_notified = True
            self.closed.emit()

    def done(self, result: int) -> None:
        self._notify_closed()
        super().done(result)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._notify_closed()
        super().closeEvent(event)
