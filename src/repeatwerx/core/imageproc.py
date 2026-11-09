"""Raster/SVG import helpers: background detection and color keying."""

from __future__ import annotations

import base64
import hashlib
from collections import Counter

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtSvg import QSvgRenderer

from .model import Document

MAX_IMPORT_PX = 2048


def raster_filter() -> str:
    fmts = sorted({bytes(f).decode().lower()
                   for f in QImageReader.supportedImageFormats()}
                  - {"svg", "svgz", "pdf"})
    pats = " ".join(f"*.{f}" for f in fmts)
    return f"Images ({pats})"


def load_image(path: str, max_px: int = MAX_IMPORT_PX) -> QImage:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        raise ValueError(f"could not read image: {reader.errorString()}")
    if max(img.width(), img.height()) > max_px:
        img = img.scaled(max_px, max_px, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return img.convertToFormat(QImage.Format.Format_ARGB32)


def _array(img: QImage) -> np.ndarray:
    """H x W x 4 (B, G, R, A) uint8 copy of an ARGB32 image."""
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    h, w, bpl = img.height(), img.width(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), np.uint8, count=h * bpl)
    return buf.reshape(h, bpl)[:, :w * 4].reshape(h, w, 4).copy()


def _image(arr: np.ndarray) -> QImage:
    h, w = arr.shape[:2]
    arr = np.ascontiguousarray(arr)
    img = QImage(arr.data, w, h, w * 4, QImage.Format.Format_ARGB32)
    return img.copy()


def has_transparency(img: QImage) -> bool:
    return bool((_array(img)[..., 3] < 250).any())


def detect_background(img: QImage) -> str | None:
    """Most common border color, or None if the border is transparent."""
    a = _array(img)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    if (border[:, 3] < 128).mean() > 0.5:
        return None
    q = (border[:, :3] // 16).astype(np.int32)
    keys = q[:, 0] | (q[:, 1] << 4) | (q[:, 2] << 8)
    top = Counter(keys.tolist()).most_common(1)[0][0]
    sel = border[keys == top][:, :3].mean(axis=0)
    b, g, r = (int(round(v)) for v in sel)
    return f"#{r:02x}{g:02x}{b:02x}"


def pixel_color(img: QImage, x: int, y: int) -> str:
    c = img.pixelColor(max(0, min(img.width() - 1, x)),
                       max(0, min(img.height() - 1, y)))
    return c.name()


def key_out(img: QImage, hexcol: str | None, tolerance: float = 32,
            feather: float = 16, contiguous: bool = True) -> QImage:
    """Make pixels near `hexcol` transparent.

    tolerance/feather are RGB distances (0..441). With `contiguous`, only
    regions connected to the image border are removed, so interior
    details of the same color survive.
    """
    if not hexcol:
        return img.convertToFormat(QImage.Format.Format_ARGB32)
    a = _array(img)
    hexcol = hexcol.lstrip("#")
    key = np.array([int(hexcol[4:6], 16), int(hexcol[2:4], 16),
                    int(hexcol[0:2], 16)], np.float32)     # B, G, R
    dist = np.sqrt(((a[..., :3].astype(np.float32) - key) ** 2).sum(-1))
    keep = np.clip((dist - tolerance) / max(feather, 1.0), 0.0, 1.0)
    if contiguous:
        cand = keep < 1.0
        reach = np.zeros_like(cand)
        reach[0, :] = cand[0, :]
        reach[-1, :] = cand[-1, :]
        reach[:, 0] |= cand[:, 0]
        reach[:, -1] |= cand[:, -1]
        for _ in range(max(a.shape[:2]) * 2):
            grown = reach.copy()
            grown[1:] |= reach[:-1]
            grown[:-1] |= reach[1:]
            grown[:, 1:] |= reach[:, :-1]
            grown[:, :-1] |= reach[:, 1:]
            grown &= cand
            if np.array_equal(grown, reach):
                break
            reach = grown
        keep = np.where(reach, keep, 1.0)
    a[..., 3] = (a[..., 3].astype(np.float32) * keep).astype(np.uint8)
    return _image(a)


def png_b64(img: QImage) -> str:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return base64.b64encode(bytes(ba)).decode("ascii")


def add_image_asset(doc: Document, img: QImage, name: str = "") -> str:
    data = png_b64(img)
    key = "img-" + hashlib.sha1(data.encode()).hexdigest()[:12]
    doc.assets.setdefault(key, {"type": "png", "data": data,
                                "w": img.width(), "h": img.height(),
                                "name": name})
    return key


def add_svg_asset(doc: Document, text: str, name: str = ""):
    r = QSvgRenderer(QByteArray(text.encode("utf-8")))
    if not r.isValid():
        raise ValueError("invalid SVG file")
    size = r.defaultSize()
    w, h = (size.width(), size.height()) if size.isValid() else (100, 100)
    key = "svg-" + hashlib.sha1(text.encode()).hexdigest()[:12]
    doc.assets.setdefault(key, {"type": "svg", "data": text, "w": w,
                                "h": h, "name": name})
    return key, w, h
