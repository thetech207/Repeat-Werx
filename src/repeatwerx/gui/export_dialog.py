"""Export dialog with live preview: one tile, a tile grid, or a fixed
image size with tile-scale options."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QRadioButton, QButtonGroup, QSpinBox,
                               QDoubleSpinBox, QCheckBox, QComboBox,
                               QDialogButtonBox, QFileDialog, QMessageBox,
                               QGroupBox, QWidget)

from ..core import export as exp

FORMATS = [("png", "PNG image"), ("jpg", "JPEG image"),
           ("tiff", "TIFF image"), ("webp", "WebP image"),
           ("bmp", "BMP image"), ("svg", "SVG vector"),
           ("pdf", "PDF document")]
PREVIEW = 360


class ExportDialog(QDialog):
    def __init__(self, doc, settings: QSettings, last_dir: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export pattern")
        self.doc = doc
        self.settings = settings
        self.last_dir = last_dir
        self.exported_path = None
        lay = QHBoxLayout(self)

        left = QVBoxLayout()
        mg = QGroupBox("What to export")
        mf = QVBoxLayout(mg)
        self.m_tile = QRadioButton("Single tile")
        self.m_grid = QRadioButton("Tile grid (e.g. 4 × 4)")
        self.m_size = QRadioButton("Fixed image size")
        grp = QButtonGroup(self)
        for b in (self.m_tile, self.m_grid, self.m_size):
            grp.addButton(b)
            mf.addWidget(b)
            b.toggled.connect(self._changed)
        left.addWidget(mg)

        og = QGroupBox("Options")
        f = QFormLayout(og)
        self.tile_px = QSpinBox()
        self.tile_px.setRange(16, 16384)
        self.tile_px.setSuffix(" px")
        f.addRow("Tile size:", self.tile_px)
        self.cols = QSpinBox()
        self.cols.setRange(1, 64)
        self.rows = QSpinBox()
        self.rows.setRange(1, 64)
        cr = QWidget()
        crl = QHBoxLayout(cr)
        crl.setContentsMargins(0, 0, 0, 0)
        crl.addWidget(self.cols)
        crl.addWidget(QLabel("×"))
        crl.addWidget(self.rows)
        f.addRow("Tiles:", cr)
        self.width_ = QSpinBox()
        self.width_.setRange(16, 30000)
        self.height_ = QSpinBox()
        self.height_.setRange(16, 30000)
        wh = QWidget()
        whl = QHBoxLayout(wh)
        whl.setContentsMargins(0, 0, 0, 0)
        whl.addWidget(self.width_)
        whl.addWidget(QLabel("×"))
        whl.addWidget(self.height_)
        f.addRow("Image size:", wh)
        self.fit = QComboBox()
        self.fit.addItem("Use tile size (scale)", "scale")
        self.fit.addItem("Fit a number of tiles across", "across")
        f.addRow("Tile scale:", self.fit)
        self.across = QDoubleSpinBox()
        self.across.setRange(0.25, 200)
        self.across.setDecimals(2)
        f.addRow("Tiles across:", self.across)
        self.center = QCheckBox("Center a tile in the image")
        f.addRow("", self.center)
        self.fmt = QComboBox()
        for k, lab in FORMATS:
            self.fmt.addItem(lab, k)
        f.addRow("Format:", self.fmt)
        self.transparent = QCheckBox("Transparent background")
        f.addRow("", self.transparent)
        self.quality = QSpinBox()
        self.quality.setRange(10, 100)
        f.addRow("Quality:", self.quality)
        left.addWidget(og)
        self._form = f
        for w in (self.tile_px, self.cols, self.rows, self.width_,
                  self.height_, self.across, self.quality):
            w.valueChanged.connect(self._changed)
        for w in (self.fit, self.fmt):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.center, self.transparent):
            w.toggled.connect(self._changed)
        left.addStretch(1)
        lay.addLayout(left)

        right = QVBoxLayout()
        self.preview = QLabel()
        self.preview.setFixedSize(PREVIEW, PREVIEW)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#808080; border-radius:6px;")
        right.addWidget(self.preview)
        self.info = QLabel()
        right.addWidget(self.info)
        right.addStretch(1)
        bb = QDialogButtonBox()
        self.export_btn = bb.addButton(
            "Export…", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._export)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._update_preview)
        self._load()
        self._changed()

    # -------------------------------------------------------------
    def _load(self):
        s = self.settings
        mode = s.value("export/mode", "tile")
        {"tile": self.m_tile, "grid": self.m_grid,
         "size": self.m_size}.get(mode, self.m_tile).setChecked(True)
        self.tile_px.setValue(int(s.value("export/tile_px",
                                          self.doc.tile_size)))
        self.cols.setValue(int(s.value("export/cols", 4)))
        self.rows.setValue(int(s.value("export/rows", 4)))
        self.width_.setValue(int(s.value("export/width", 3000)))
        self.height_.setValue(int(s.value("export/height", 2000)))
        i = self.fit.findData(s.value("export/fit", "scale"))
        self.fit.setCurrentIndex(max(0, i))
        self.across.setValue(float(s.value("export/across", 4)))
        self.center.setChecked(s.value("export/center", "false") == "true")
        i = self.fmt.findData(s.value("export/format", "png"))
        self.fmt.setCurrentIndex(max(0, i))
        self.transparent.setChecked(
            s.value("export/transparent", "false") == "true")
        self.quality.setValue(int(s.value("export/quality", 92)))

    def _save(self):
        s = self.settings
        sp = self.spec()
        s.setValue("export/mode", sp.mode)
        s.setValue("export/tile_px", int(sp.tile_px))
        s.setValue("export/cols", sp.cols)
        s.setValue("export/rows", sp.rows)
        s.setValue("export/width", sp.width)
        s.setValue("export/height", sp.height)
        s.setValue("export/fit", sp.size_fit)
        s.setValue("export/across", sp.tiles_across)
        s.setValue("export/center", "true" if sp.center else "false")
        s.setValue("export/format", self.fmt.currentData())
        s.setValue("export/transparent",
                   "true" if self.transparent.isChecked() else "false")
        s.setValue("export/quality", sp.quality)

    def spec(self) -> exp.ExportSpec:
        mode = ("grid" if self.m_grid.isChecked() else
                "size" if self.m_size.isChecked() else "tile")
        fmt = self.fmt.currentData()
        return exp.ExportSpec(
            mode=mode, tile_px=self.tile_px.value(), cols=self.cols.value(),
            rows=self.rows.value(), width=self.width_.value(),
            height=self.height_.value(), size_fit=self.fit.currentData(),
            tiles_across=self.across.value(), center=self.center.isChecked(),
            background=not (self.transparent.isChecked()
                            and fmt in exp.ALPHA_FORMATS),
            quality=self.quality.value())

    def _changed(self, *_):
        sp = self.spec()
        f = self._form
        size_mode = sp.mode == "size"
        f.setRowVisible(self.cols.parentWidget(), sp.mode == "grid")
        f.setRowVisible(self.width_.parentWidget(), size_mode)
        f.setRowVisible(self.fit, size_mode)
        f.setRowVisible(self.across, size_mode and sp.size_fit == "across")
        f.setRowVisible(self.center, size_mode)
        f.setRowVisible(self.tile_px, not (size_mode
                                           and sp.size_fit == "across"))
        fmt = self.fmt.currentData()
        f.setRowVisible(self.transparent, fmt in exp.ALPHA_FORMATS)
        f.setRowVisible(self.quality, fmt in ("jpg", "webp"))
        w, h, t, _o = sp.resolved()
        tiles = f"{w / t:.2f} × {h / t:.2f} tiles"
        self.info.setText(f"Output: <b>{w} × {h}</b> px<br>"
                          f"Tile: {t:.1f} px · {tiles}")
        self._timer.start()

    def _update_preview(self):
        sp = self.spec()
        w, h, t, _o = sp.resolved()
        k = min(1.0, PREVIEW / max(w, h))
        small = replace(sp, tile_px=max(2.0, sp.tile_px * k),
                        width=max(1, int(w * k)), height=max(1, int(h * k)),
                        mode=sp.mode)
        if sp.mode == "size" and sp.size_fit == "across":
            small.tile_px = small.width / max(sp.tiles_across, 0.01)
        img = exp.compose(self.doc, small)
        self.preview.setPixmap(QPixmap.fromImage(img))

    def _export(self):
        fmt = self.fmt.currentData()
        label = dict(FORMATS)[fmt]
        start = str(Path(self.last_dir or Path.home())
                    / f"{self.doc.name}.{fmt}")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export pattern", start, f"{label} (*.{fmt})")
        if not path:
            return
        if not path.lower().endswith(f".{fmt}") and not (
                fmt in ("jpg", "tiff")
                and path.lower().endswith((".jpeg", ".tif"))):
            path += f".{fmt}"
        try:
            exp.export(self.doc, self.spec(), path)
        except Exception as e:      # noqa: BLE001 - surface any failure
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self._save()
        self.exported_path = path
        self.accept()
