"""Geometry + painting for items and whole tiles (with wrap-around)."""

from __future__ import annotations

import base64
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QByteArray
from PySide6.QtGui import (QPainter, QPainterPath, QTransform, QPen,
                           QBrush, QColor, QImage, QPolygonF)
from PySide6.QtSvg import QSvgRenderer

from .model import (Item, Layer, Document, RECT, ELLIPSE, POLYGON, STAR,
                    PATH, IMAGE, SVG, GENERATOR)

UNIT = QRectF(-0.5, -0.5, 1.0, 1.0)

_image_cache: dict = {}
_svg_cache: dict = {}


# ------------------------------------------------------------- geometry
def regular_polygon(sides: int, inner: float | None = None) -> QPolygonF:
    """Unit-box polygon (or star when `inner` is given), point up."""
    sides = max(3, int(sides))
    pts = []
    count = sides * 2 if inner is not None else sides
    for k in range(count):
        a = -math.pi / 2 + k * math.pi * 2 / count
        r = 0.5 if (inner is None or k % 2 == 0) else 0.5 * inner
        pts.append(QPointF(r * math.cos(a), r * math.sin(a)))
    return QPolygonF(pts)


def segments_path(segments: list) -> QPainterPath:
    p = QPainterPath()
    for seg in segments:
        op = seg[0]
        if op == "M":
            p.moveTo(seg[1], seg[2])
        elif op == "L":
            p.lineTo(seg[1], seg[2])
        elif op == "C":
            p.cubicTo(seg[1], seg[2], seg[3], seg[4], seg[5], seg[6])
        elif op == "Z":
            p.closeSubpath()
    return p


def unit_path(item: Item) -> QPainterPath:
    p = QPainterPath()
    k = item.kind
    if k == RECT:
        if item.corner_radius > 0:
            r = min(item.corner_radius, min(item.w, item.h) / 2)
            p.addRoundedRect(UNIT, r / max(item.w, 1e-6),
                             r / max(item.h, 1e-6))
        else:
            p.addRect(UNIT)
    elif k == ELLIPSE:
        p.addEllipse(UNIT)
    elif k == POLYGON:
        p.addPolygon(regular_polygon(item.sides))
        p.closeSubpath()
    elif k == STAR:
        p.addPolygon(regular_polygon(item.sides, item.inner_ratio))
        p.closeSubpath()
    elif k == PATH:
        p = segments_path(item.segments)
    else:
        p.addRect(UNIT)
    return p


def item_transform(item: Item) -> QTransform:
    """Local unit box -> tile coords."""
    t = QTransform()
    t.translate(item.cx, item.cy)
    t.rotate(item.rotation)
    t.scale(item.w * (-1 if item.flip_x else 1),
            item.h * (-1 if item.flip_y else 1))
    return t


def item_path(item: Item) -> QPainterPath:
    """Outline in tile coords (stroke width is not scaled with the item)."""
    return item_transform(item).map(unit_path(item))


def item_bounds(item: Item) -> QRectF:
    if item.kind in (IMAGE, SVG):
        r = item_transform(item).mapRect(UNIT)
    else:
        r = item_path(item).boundingRect()
    m = (item.stroke_width / 2 + 1) if item.stroke else 1
    return r.adjusted(-m, -m, m, m)


def is_closed(item: Item) -> bool:
    if item.kind != PATH:
        return True
    return bool(item.segments) and item.segments[-1][0] == "Z"


def hit_test(item: Item, x: float, y: float, tol: float = 4.0) -> bool:
    if item.kind in (IMAGE, SVG):
        inv, ok = item_transform(item).inverted()
        if not ok:
            return False
        lp = inv.map(QPointF(x, y))
        return UNIT.contains(lp)
    path = item_path(item)
    if is_closed(item) and (item.fill or not item.stroke) \
            and path.contains(QPointF(x, y)):
        return True
    from PySide6.QtGui import QPainterPathStroker
    st = QPainterPathStroker()
    st.setWidth(max(item.stroke_width if item.stroke else 0, 0) + tol * 2)
    return st.createStroke(path).contains(QPointF(x, y))


def wrap_offsets(rect: QRectF, T: float):
    """Tile-sized offsets at which `rect` overlaps the tile [0,T]^2."""
    tile = QRectF(0, 0, T, T)
    out = []
    for ox in (-T, 0.0, T):
        for oy in (-T, 0.0, T):
            if rect.translated(ox, oy).intersects(tile):
                out.append((ox, oy))
    return out


# --------------------------------------------------------------- assets
def asset_image(doc: Document, key: str) -> QImage | None:
    img = _image_cache.get(key)
    if img is None:
        a = doc.assets.get(key)
        if not a or a.get("type") != "png":
            return None
        img = QImage.fromData(base64.b64decode(a["data"]), "PNG")
        _image_cache[key] = img
    return img


def asset_svg(doc: Document, key: str) -> QSvgRenderer | None:
    r = _svg_cache.get(key)
    if r is None:
        a = doc.assets.get(key)
        if not a or a.get("type") != "svg":
            return None
        r = QSvgRenderer(QByteArray(a["data"].encode("utf-8")))
        _svg_cache[key] = r
    return r


# -------------------------------------------------------------- painting
def make_pen(item: Item) -> QPen:
    if not item.stroke or item.stroke_width <= 0:
        return QPen(Qt.PenStyle.NoPen)
    pen = QPen(QColor(item.stroke), item.stroke_width)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def draw_item(p: QPainter, item: Item, doc: Document):
    p.save()
    if item.opacity < 1:
        p.setOpacity(p.opacity() * item.opacity)
    if item.kind == IMAGE:
        img = asset_image(doc, item.asset) if item.asset else None
        if img is not None:
            p.setTransform(item_transform(item), True)
            p.drawImage(UNIT, img)
    elif item.kind == SVG:
        r = asset_svg(doc, item.asset) if item.asset else None
        if r is not None:
            p.setTransform(item_transform(item), True)
            r.render(p, UNIT)
    else:
        path = item_path(item)
        p.setPen(make_pen(item))
        if item.fill and is_closed(item):
            p.setBrush(QBrush(QColor(item.fill)))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    p.restore()


def draw_wrapped(p: QPainter, item: Item, doc: Document, T: float):
    for ox, oy in wrap_offsets(item_bounds(item), T):
        if ox or oy:
            p.save()
            p.translate(ox, oy)
            draw_item(p, item, doc)
            p.restore()
        else:
            draw_item(p, item, doc)


def layer_items(layer: Layer, doc: Document) -> list:
    if layer.kind == GENERATOR:
        from .generators import generate_cached
        return generate_cached(layer, doc)[0]
    return layer.items


def paint_layer(p: QPainter, layer: Layer, doc: Document):
    T = doc.tile_size
    p.save()
    p.setOpacity(layer.opacity)
    for it in layer_items(layer, doc):
        draw_wrapped(p, it, doc, T)
    p.restore()


def paint_tile(p: QPainter, doc: Document, background: bool = True,
               layers=None):
    """Paint one tile in tile units (caller sets the scale)."""
    T = doc.tile_size
    p.save()
    p.setClipRect(QRectF(0, 0, T, T))
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if background and doc.background:
        p.fillRect(QRectF(0, 0, T, T), QColor(doc.background))
    for lay in (layers if layers is not None else doc.layers):
        if lay.visible:
            paint_layer(p, lay, doc)
    p.restore()


def render_tile(doc: Document, px: int, background: bool = True,
                layers=None) -> QImage:
    px = max(1, int(px))
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.scale(px / doc.tile_size, px / doc.tile_size)
    paint_tile(p, doc, background, layers)
    p.end()
    return img


def render_layer_image(doc: Document, layer: Layer, px: int) -> QImage:
    """One layer, wrapped, transparent elsewhere (opacity applied)."""
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(px / doc.tile_size, px / doc.tile_size)
    p.setClipRect(QRectF(0, 0, doc.tile_size, doc.tile_size))
    paint_layer(p, layer, doc)
    p.end()
    return img
