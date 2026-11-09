"""Raster and vector export of tiles, tile grids and fixed-size images."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QSize, QSizeF, QMarginsF
from PySide6.QtGui import (QImage, QPainter, QBrush, QTransform, QColor,
                           QImageWriter, QPageSize, QPageLayout)

from .model import Document
from .render import render_tile, paint_tile

RASTER_FORMATS = {"png": "PNG", "jpg": "JPEG", "tiff": "TIFF",
                  "webp": "WebP", "bmp": "BMP"}
VECTOR_FORMATS = {"svg": "SVG", "pdf": "PDF"}
ALPHA_FORMATS = {"png", "tiff", "webp", "svg", "pdf"}


@dataclass
class ExportSpec:
    mode: str = "tile"          # tile | grid | size
    tile_px: float = 1024       # pixels per tile
    cols: int = 4
    rows: int = 4
    width: int = 3000           # size mode
    height: int = 2000
    size_fit: str = "scale"     # scale (use tile_px) | across (tiles_across)
    tiles_across: float = 4.0
    center: bool = False        # size mode: center a tile in the image
    background: bool = True     # False = transparent where supported
    quality: int = 92

    def resolved(self):
        """(width, height, tile_px, (ox, oy)) in output pixels."""
        if self.mode == "grid":
            t = float(self.tile_px)
            return (int(round(self.cols * t)), int(round(self.rows * t)),
                    t, (0.0, 0.0))
        if self.mode == "size":
            w, h = max(1, int(self.width)), max(1, int(self.height))
            t = (w / max(self.tiles_across, 0.01)
                 if self.size_fit == "across" else float(self.tile_px))
            off = ((w / 2 - t / 2) % t, (h / 2 - t / 2) % t) \
                if self.center else (0.0, 0.0)
            return w, h, t, off
        t = float(self.tile_px)
        return int(round(t)), int(round(t)), t, (0.0, 0.0)


def compose(doc: Document, spec: ExportSpec) -> QImage:
    w, h, t, (ox, oy) = spec.resolved()
    tpx = max(1, int(math.ceil(t)))
    tile = render_tile(doc, tpx, spec.background)
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    brush = QBrush(tile)
    tr = QTransform()
    tr.translate(ox - t, oy - t)
    tr.scale(t / tpx, t / tpx)
    brush.setTransform(tr)
    p.fillRect(QRectF(0, 0, w, h), brush)
    p.end()
    return out


def export_raster(doc: Document, spec: ExportSpec, path) -> Path:
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    ext = {"jpeg": "jpg", "tif": "tiff"}.get(ext, ext)
    if ext not in RASTER_FORMATS:
        raise ValueError(f"unsupported image format: .{ext}")
    if ext not in ALPHA_FORMATS:
        spec.background = True
    img = compose(doc, spec)
    if ext in ("jpg", "bmp"):
        flat = QImage(img.size(), QImage.Format.Format_RGB32)
        flat.fill(QColor(doc.background or "#ffffff"))
        p = QPainter(flat)
        p.drawImage(0, 0, img)
        p.end()
        img = flat
    w = QImageWriter(str(path), {"jpg": b"jpeg"}.get(ext, ext.encode()))
    if ext in ("jpg", "webp"):
        w.setQuality(int(spec.quality))
    if not w.write(img):
        raise IOError(w.errorString())
    return path


def _paint_tiles(p: QPainter, doc: Document, spec: ExportSpec):
    w, h, t, (ox, oy) = spec.resolved()
    T = doc.tile_size
    p.setClipRect(QRectF(0, 0, w, h))
    i0 = -1 if ox > 0 else 0
    j0 = -1 if oy > 0 else 0
    for j in range(j0, int(math.ceil(h / t)) + 1):
        for i in range(i0, int(math.ceil(w / t)) + 1):
            x, y = ox + i * t, oy + j * t
            if x >= w or y >= h or x + t <= 0 or y + t <= 0:
                continue
            p.save()
            p.translate(x, y)
            p.scale(t / T, t / T)
            paint_tile(p, doc, spec.background)
            p.restore()


def export_vector(doc: Document, spec: ExportSpec, path) -> Path:
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    w, h, _t, _o = spec.resolved()
    if ext == "svg":
        from PySide6.QtSvg import QSvgGenerator
        gen = QSvgGenerator()
        gen.setFileName(str(path))
        gen.setSize(QSize(w, h))
        gen.setViewBox(QRectF(0, 0, w, h))
        gen.setTitle(doc.name)
        gen.setDescription("Created with Repeat-Werx")
        p = QPainter(gen)
        _paint_tiles(p, doc, spec)
        p.end()
    elif ext == "pdf":
        from PySide6.QtGui import QPdfWriter
        pdf = QPdfWriter(str(path))
        pdf.setResolution(96)
        pdf.setPageSize(QPageSize(QSizeF(w * 72 / 96, h * 72 / 96),
                                  QPageSize.Unit.Point, "Pattern"))
        pdf.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
        pdf.setTitle(doc.name)
        p = QPainter(pdf)
        _paint_tiles(p, doc, spec)
        p.end()
    else:
        raise ValueError(f"unsupported vector format: .{ext}")
    return path


def export(doc: Document, spec: ExportSpec, path) -> Path:
    ext = Path(path).suffix.lower().lstrip(".")
    if ext in VECTOR_FORMATS:
        return export_vector(doc, spec, path)
    return export_raster(doc, spec, path)
