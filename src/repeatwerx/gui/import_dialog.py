"""Raster import: pick or auto-detect the background color to key out."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QImage
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QWidget, QRadioButton, QButtonGroup,
                               QCheckBox, QSpinBox, QDialogButtonBox,
                               QComboBox)

from ..core import imageproc
from .widgets import ColorButton, SliderSpin

PREVIEW_PX = 420


class _Preview(QWidget):
    picked = Signal(int, int)       # source-image pixel coords

    def __init__(self):
        super().__init__()
        self.setMinimumSize(PREVIEW_PX, PREVIEW_PX)
        self.img: QImage | None = None
        self.src_size = (1, 1)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Click to pick the background color")

    def _target(self) -> QRectF:
        if self.img is None:
            return QRectF()
        iw, ih = self.img.width(), self.img.height()
        s = min(self.width() / iw, self.height() / ih)
        w, h = iw * s, ih * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, _e):
        p = QPainter(self)
        sz = 12
        for y in range(0, self.height(), sz):
            for x in range(0, self.width(), sz):
                p.fillRect(x, y, sz, sz, QColor("#ffffff")
                           if (x // sz + y // sz) % 2 else QColor("#d6d6d6"))
        if self.img is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(self._target(), self.img)
        p.end()

    def mousePressEvent(self, ev):
        r = self._target()
        if r.isNull() or not r.contains(ev.position()):
            return
        fx = (ev.position().x() - r.left()) / r.width()
        fy = (ev.position().y() - r.top()) / r.height()
        self.picked.emit(int(fx * self.src_size[0]),
                         int(fy * self.src_size[1]))


class ImageImportDialog(QDialog):
    def __init__(self, path: str, can_use_active: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import image")
        self.source = imageproc.load_image(path)
        self.small = self.source.scaled(
            PREVIEW_PX, PREVIEW_PX, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation) \
            if max(self.source.width(), self.source.height()) > PREVIEW_PX \
            else self.source
        self.detected = imageproc.detect_background(self.source)
        self.picked = self.detected
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)

        lay = QHBoxLayout(self)
        self.preview = _Preview()
        self.preview.src_size = (self.source.width(), self.source.height())
        self.preview.picked.connect(self._on_pick)
        lay.addWidget(self.preview, 1)

        side = QVBoxLayout()
        form = QFormLayout()
        self.mode_none = QRadioButton("Keep as is")
        self.mode_auto = QRadioButton("Auto-detect")
        self.mode_pick = QRadioButton("Picked color")
        grp = QButtonGroup(self)
        for b in (self.mode_none, self.mode_auto, self.mode_pick):
            grp.addButton(b)
            b.toggled.connect(self._schedule)
        has_alpha = imageproc.has_transparency(self.source)
        (self.mode_none if (has_alpha or not self.detected)
         else self.mode_auto).setChecked(True)
        self.mode_auto.setEnabled(self.detected is not None)
        self.mode_auto.setText(
            f"Auto-detect ({self.detected})" if self.detected
            else "Auto-detect (none found)")
        modes = QVBoxLayout()
        for b in (self.mode_none, self.mode_auto, self.mode_pick):
            modes.addWidget(b)
        mw = QWidget()
        mw.setLayout(modes)
        form.addRow("Transparent:", mw)
        self.swatch = ColorButton(self.picked or "#ffffff")
        self.swatch.color_changed.connect(self._on_swatch)
        form.addRow("Color:", self.swatch)
        self.tol = SliderSpin(0, 200, 1, 0)
        self.tol.setValue(40)
        self.tol.value_changed.connect(self._schedule)
        form.addRow("Tolerance:", self.tol)
        self.feather = SliderSpin(0, 120, 1, 0)
        self.feather.setValue(20)
        self.feather.value_changed.connect(self._schedule)
        form.addRow("Soft edge:", self.feather)
        self.contig = QCheckBox("Only areas touching the edge")
        self.contig.setChecked(True)
        self.contig.toggled.connect(self._schedule)
        form.addRow("", self.contig)
        self.size = QSpinBox()
        self.size.setRange(2, 400)
        self.size.setValue(50)
        self.size.setSuffix(" % of tile")
        form.addRow("Size:", self.size)
        self.target = QComboBox()
        self.target.addItem("New raster layer", "new")
        if can_use_active:
            self.target.addItem("Active raster layer", "active")
        form.addRow("Place on:", self.target)
        side.addLayout(form)
        info = QLabel(f"{self.source.width()} × {self.source.height()} px. "
                      "Click the preview to pick a color.")
        info.setWordWrap(True)
        side.addWidget(info)
        side.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)
        lay.addLayout(side)
        self._timer.timeout.connect(self._update_preview)
        self._update_preview()

    def _key_color(self):
        if self.mode_auto.isChecked():
            return self.detected
        if self.mode_pick.isChecked():
            return self.picked
        return None

    def _on_pick(self, x, y):
        self.picked = imageproc.pixel_color(self.source, x, y)
        self.swatch.set_color(self.picked)
        self.mode_pick.setChecked(True)
        self._schedule()

    def _on_swatch(self, c):
        self.picked = c
        self.mode_pick.setChecked(True)
        self._schedule()

    def _schedule(self, *_):
        self._timer.start()

    def _process(self, img):
        return imageproc.key_out(img, self._key_color(), self.tol.value(),
                                 self.feather.value(),
                                 self.contig.isChecked())

    def _update_preview(self):
        self.preview.img = self._process(self.small)
        self.preview.update()

    def result_image(self) -> QImage:
        return self._process(self.source)

    def size_fraction(self) -> float:
        return self.size.value() / 100.0

    def target_mode(self) -> str:
        return self.target.currentData()
