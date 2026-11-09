"""Programmatic 32px icons tinted for the current theme."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QPen, QBrush, QColor,
                           QPolygonF, QPainterPath)

from .theme import icon_ink

BLUE = QColor("#3d6fb4")
AMBER = QColor("#d08a1e")
RED = QColor("#c8433a")
GREEN = QColor("#5b8a3a")


def _pen(c, w=2.2):
    p = QPen(c, w)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _poly(n, cx, cy, r, inner=None, rot=-90):
    pts = []
    cnt = n * 2 if inner else n
    for k in range(cnt):
        a = math.radians(rot + k * 360 / cnt)
        rr = r if (not inner or k % 2 == 0) else r * inner
        pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return QPolygonF(pts)


def icon(name: str, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 32, size / 32)
    ink = icon_ink()
    fill = QBrush(QColor(BLUE.red(), BLUE.green(), BLUE.blue(), 150))
    p.setPen(_pen(ink))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "select":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawPolygon(QPolygonF([QPointF(9, 4), QPointF(9, 23),
                                 QPointF(13.5, 18.5), QPointF(16.5, 26),
                                 QPointF(19.5, 24.5), QPointF(16.5, 17.5),
                                 QPointF(22.5, 17.5)]))
    elif name == "rect":
        p.setBrush(fill)
        p.drawRect(QRectF(6, 8, 20, 16))
    elif name == "ellipse":
        p.setBrush(fill)
        p.drawEllipse(QRectF(5, 8, 22, 16))
    elif name == "polygon":
        p.setBrush(fill)
        p.drawPolygon(_poly(6, 16, 16, 11))
    elif name == "star":
        p.setBrush(fill)
        p.drawPolygon(_poly(5, 16, 17, 12, 0.45))
    elif name == "line":
        p.setPen(_pen(ink, 2.6))
        p.drawLine(QPointF(7, 25), QPointF(25, 7))
    elif name == "pen":
        path = QPainterPath(QPointF(5, 24))
        path.cubicTo(10, 4, 20, 30, 27, 8)
        p.drawPath(path)
        p.setBrush(BLUE)
        p.setPen(Qt.PenStyle.NoPen)
        for x, y in ((5, 24), (27, 8)):
            p.drawRect(QRectF(x - 2.5, y - 2.5, 5, 5))
    elif name == "eyedropper":
        p.setPen(_pen(ink, 2.4))
        p.drawLine(QPointF(9, 23), QPointF(20, 12))
        p.setBrush(ink)
        p.drawEllipse(QRectF(19, 6, 7, 7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BLUE)
        p.drawEllipse(QRectF(5, 23, 5, 5))
    elif name == "pan":
        p.setPen(_pen(ink, 2.2))
        p.drawLine(QPointF(16, 5), QPointF(16, 27))
        p.drawLine(QPointF(5, 16), QPointF(27, 16))
        for a in (0, 90, 180, 270):
            r = math.radians(a)
            tip = QPointF(16 + 11 * math.cos(r), 16 + 11 * math.sin(r))
            for s in (-1, 1):
                b = r + math.pi + s * 0.6
                p.drawLine(tip, QPointF(tip.x() + 5 * math.cos(b),
                                        tip.y() + 5 * math.sin(b)))
    elif name == "vector":
        p.setBrush(fill)
        path = QPainterPath(QPointF(5, 24))
        path.cubicTo(8, 6, 24, 6, 27, 24)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "raster":
        p.setPen(_pen(ink, 1.6))
        p.drawRect(QRectF(5, 7, 22, 18))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(GREEN)
        p.drawPolygon(QPolygonF([QPointF(6, 24), QPointF(14, 14),
                                 QPointF(20, 20), QPointF(26, 24)]))
        p.setBrush(AMBER)
        p.drawEllipse(QRectF(19, 9, 5, 5))
    elif name == "generator":
        p.setPen(Qt.PenStyle.NoPen)
        for (x, y, r, c) in ((9, 10, 4, BLUE), (21, 9, 3, AMBER),
                             (15, 19, 5, GREEN), (25, 22, 3, BLUE),
                             (7, 24, 2.5, AMBER)):
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), r, r)
    elif name == "add":
        p.setPen(_pen(ink, 2.6))
        p.drawLine(QPointF(16, 7), QPointF(16, 25))
        p.drawLine(QPointF(7, 16), QPointF(25, 16))
    elif name == "delete":
        p.setPen(_pen(RED, 2.6))
        p.drawLine(QPointF(9, 9), QPointF(23, 23))
        p.drawLine(QPointF(23, 9), QPointF(9, 23))
    elif name in ("up", "down"):
        d = -1 if name == "up" else 1
        p.setPen(_pen(ink, 2.6))
        p.drawLine(QPointF(16, 16 - 9 * d), QPointF(16, 16 + 9 * d))
        p.drawLine(QPointF(16, 16 - 9 * d), QPointF(10, 16 - 3 * d))
        p.drawLine(QPointF(16, 16 - 9 * d), QPointF(22, 16 - 3 * d))
    elif name == "merge":
        p.setPen(_pen(ink, 2.2))
        p.drawLine(QPointF(9, 6), QPointF(16, 15))
        p.drawLine(QPointF(23, 6), QPointF(16, 15))
        p.drawLine(QPointF(16, 15), QPointF(16, 26))
        p.drawLine(QPointF(16, 26), QPointF(12, 22))
        p.drawLine(QPointF(16, 26), QPointF(20, 22))
    elif name == "bake":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(AMBER)
        p.drawPolygon(QPolygonF([QPointF(18, 4), QPointF(8, 18),
                                 QPointF(15, 18), QPointF(13, 28),
                                 QPointF(24, 13), QPointF(17, 13)]))
    elif name == "duplicate":
        p.setPen(_pen(ink, 1.8))
        p.drawRect(QRectF(5, 9, 15, 15))
        p.setBrush(fill)
        p.drawRect(QRectF(12, 5, 15, 15))
    elif name == "fit":
        p.setPen(_pen(ink, 2.2))
        for x, y, dx, dy in ((6, 6, 1, 1), (26, 6, -1, 1), (6, 26, 1, -1),
                             (26, 26, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 6 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 6 * dy))
        p.drawRect(QRectF(12, 12, 8, 8))
    elif name == "dice":
        p.setPen(_pen(ink, 1.8))
        p.drawRoundedRect(QRectF(6, 6, 20, 20), 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        for x, y in ((11, 11), (21, 21), (16, 16), (21, 11), (11, 21)):
            p.drawEllipse(QPointF(x, y), 1.8, 1.8)
    elif name == "lock":
        p.setPen(_pen(ink, 2))
        p.drawArc(QRectF(10, 6, 12, 14), 0, 180 * 16)
        p.setBrush(ink)
        p.drawRoundedRect(QRectF(8, 14, 16, 12), 2, 2)
    elif name == "flipx":
        p.setPen(_pen(ink, 2.2))
        p.drawLine(QPointF(7, 16), QPointF(25, 16))
        for x, d in ((7, 1), (25, -1)):
            p.drawLine(QPointF(x, 16), QPointF(x + 5 * d, 11))
            p.drawLine(QPointF(x, 16), QPointF(x + 5 * d, 21))
    elif name == "flipy":
        p.setPen(_pen(ink, 2.2))
        p.drawLine(QPointF(16, 7), QPointF(16, 25))
        for y, d in ((7, 1), (25, -1)):
            p.drawLine(QPointF(16, y), QPointF(11, y + 5 * d))
            p.drawLine(QPointF(16, y), QPointF(21, y + 5 * d))
    elif name == "import":
        p.setPen(_pen(ink, 2.2))
        p.drawLine(QPointF(16, 4), QPointF(16, 19))
        p.drawLine(QPointF(16, 19), QPointF(10, 13))
        p.drawLine(QPointF(16, 19), QPointF(22, 13))
        p.drawLine(QPointF(6, 22), QPointF(6, 27))
        p.drawLine(QPointF(6, 27), QPointF(26, 27))
        p.drawLine(QPointF(26, 27), QPointF(26, 22))
    elif name == "export":
        p.setPen(_pen(ink, 2.2))
        p.drawLine(QPointF(16, 19), QPointF(16, 4))
        p.drawLine(QPointF(16, 4), QPointF(10, 10))
        p.drawLine(QPointF(16, 4), QPointF(22, 10))
        p.drawLine(QPointF(6, 22), QPointF(6, 27))
        p.drawLine(QPointF(6, 27), QPointF(26, 27))
        p.drawLine(QPointF(26, 27), QPointF(26, 22))
    elif name == "repeat":
        p.setPen(_pen(ink, 1.4))
        for i in range(3):
            for j in range(3):
                p.setBrush(fill if (i, j) == (1, 1) else Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(5 + i * 7.5, 5 + j * 7.5, 7, 7))
    p.end()
    return QIcon(pm)


def swatch_icon(color: str | None, size: int = 22,
                stroke: bool = False) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(2, 2, size - 4, size - 4)
    if color is None:
        p.setPen(QPen(QColor("#888"), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(QPen(RED, 2))
        p.drawLine(r.bottomLeft(), r.topRight())
    elif stroke:
        p.setPen(QPen(QColor(color), 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 3, 3)
    else:
        p.setPen(QPen(QColor("#555"), 1))
        p.setBrush(QColor(color))
        p.drawRoundedRect(r, 3, 3)
    p.end()
    return QIcon(pm)
