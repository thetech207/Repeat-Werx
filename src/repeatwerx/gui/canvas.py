"""Tile canvas: shows the working tile inside an N x N repeat and hosts
the drawing / selection tools. Everything is edited in tile units; the
pointer is wrapped into the center tile so you can work across seams."""

from __future__ import annotations

import json
import math
from enum import Enum

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QTimer
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QImage,
                           QTransform, QPainterPath, QCursor)
from PySide6.QtWidgets import QWidget

from ..core.model import (Item, RECT, ELLIPSE, POLYGON, STAR, PATH, IMAGE,
                          SVG, VECTOR, RASTER, GENERATOR)
from ..core import render
from ..core.generators import _cache_key


class Tool(Enum):
    SELECT = "select"
    RECT = "rect"
    ELLIPSE = "ellipse"
    POLYGON = "polygon"
    STAR = "star"
    LINE = "line"
    PEN = "pen"
    EYEDROPPER = "eyedropper"
    PAN = "pan"


SHAPE_TOOLS = {Tool.RECT: RECT, Tool.ELLIPSE: ELLIPSE,
               Tool.POLYGON: POLYGON, Tool.STAR: STAR}
HANDLE_PX = 7


def make_path_item(segments_tile: list, style: dict) -> Item:
    """Build a PATH item from segments given in tile coordinates."""
    xs, ys = [], []
    for s in segments_tile:
        xs += s[1::2]
        ys += s[2::2]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    unit = []
    for s in segments_tile:
        out = [s[0]]
        for k in range(1, len(s), 2):
            out += [(s[k] - cx) / w, (s[k + 1] - cy) / h]
        unit.append(out)
    closed = bool(unit) and unit[-1][0] == "Z"
    return Item(PATH, cx=cx, cy=cy, w=w, h=h, segments=unit,
                fill=style["fill"] if closed else None,
                stroke=style["stroke"] or ("#1c1c1c" if not closed
                                           else None),
                stroke_width=style["stroke_width"])


class TileCanvas(QWidget):
    tool_changed = Signal(object)
    color_picked = Signal(str, bool)       # color, is_stroke
    zoom_changed = Signal(float)

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(300, 300)
        self.tool = Tool.SELECT
        self.zoom = 0.25
        self.pan = QPointF(0, 0)
        self.repeat_n = 3
        self.dim_neighbors = True
        self.show_border = True
        self._layer_cache: dict = {}       # lid -> (key, px, QImage)
        self._tile_img: QImage | None = None
        self._dirty = True
        self._drag = None                  # active drag state dict
        self._pen_nodes: list = []         # [(x, y, hx, hy)]
        self._hover = None
        self._space = False
        self._fitted = False

    # -------------------------------------------------------- view math
    @property
    def doc(self):
        return self.win.doc

    def T(self) -> float:
        return float(self.doc.tile_size)

    def to_tile(self, pos) -> QPointF:
        return QPointF((pos.x() - self.pan.x()) / self.zoom,
                       (pos.y() - self.pan.y()) / self.zoom)

    def to_screen(self, pt) -> QPointF:
        return QPointF(pt.x() * self.zoom + self.pan.x(),
                       pt.y() * self.zoom + self.pan.y())

    def wrap(self, pt: QPointF) -> QPointF:
        T = self.T()
        return QPointF(pt.x() % T, pt.y() % T)

    def fit(self):
        T = self.T()
        n = self.repeat_n
        avail = min(self.width(), self.height()) - 40
        self.zoom = max(0.02, avail / (T * n))
        self.pan = QPointF(self.width() / 2 - T * self.zoom / 2,
                           self.height() / 2 - T * self.zoom / 2)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def fit_tile(self):
        T = self.T()
        avail = min(self.width(), self.height()) - 60
        self.zoom = max(0.02, avail / T)
        self.pan = QPointF(self.width() / 2 - T * self.zoom / 2,
                           self.height() / 2 - T * self.zoom / 2)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def zoom_by(self, factor, anchor=None):
        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        before = self.to_tile(anchor)
        self.zoom = max(0.02, min(16.0, self.zoom * factor))
        self.pan = QPointF(anchor.x() - before.x() * self.zoom,
                           anchor.y() - before.y() * self.zoom)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def set_tool(self, tool: Tool):
        if self._pen_nodes and tool is not Tool.PEN:
            self._finish_pen(False)
        self.tool = tool
        self._drag = None
        cur = {Tool.PAN: Qt.CursorShape.OpenHandCursor,
               Tool.SELECT: Qt.CursorShape.ArrowCursor,
               Tool.EYEDROPPER: Qt.CursorShape.PointingHandCursor}
        self.setCursor(cur.get(tool, Qt.CursorShape.CrossCursor))
        self.tool_changed.emit(tool)
        self.update()

    # ------------------------------------------------------ tile cache
    def invalidate(self):
        self._dirty = True
        self.update()

    def _render_px(self) -> int:
        want = self.T() * self.zoom * self.devicePixelRatioF()
        px = 2 ** math.ceil(math.log2(max(want, 64)))
        return int(max(128, min(4096, px)))

    def _layer_key(self, lay) -> str:
        if lay.kind == GENERATOR:
            base = _cache_key(lay, self.doc)
        else:
            base = json.dumps([i.to_dict() for i in lay.items],
                              sort_keys=True)
        return f"{lay.opacity}|{self.doc.tile_size}|{base}"

    def tile_image(self) -> QImage:
        px = self._render_px()
        if not self._dirty and self._tile_img is not None \
                and self._tile_img.width() == px:
            return self._tile_img
        doc = self.doc
        img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(doc.background) if doc.background
                 else QColor(0, 0, 0, 0))
        p = QPainter(img)
        live = set()
        for lay in doc.layers:
            if not lay.visible:
                continue
            live.add(lay.id)
            key = self._layer_key(lay)
            hit = self._layer_cache.get(lay.id)
            if hit and hit[0] == key and hit[1] == px:
                limg = hit[2]
            else:
                limg = render.render_layer_image(doc, lay, px)
                self._layer_cache[lay.id] = (key, px, limg)
            p.drawImage(0, 0, limg)
        p.end()
        for lid in list(self._layer_cache):
            if lid not in live:
                del self._layer_cache[lid]
        self._tile_img = img
        self._dirty = False
        return img

    # -------------------------------------------------------- painting
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().color(
            self.backgroundRole()).darker(115))
        T = self.T()
        tw = T * self.zoom
        img = self.tile_image()
        k = (self.repeat_n - 1) // 2
        if not self.doc.background:
            self._checker(p, QRectF(self.pan.x() - k * tw,
                                    self.pan.y() - k * tw,
                                    tw * self.repeat_n,
                                    tw * self.repeat_n))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for i in range(-k, k + 1):
            for j in range(-k, k + 1):
                r = QRectF(self.pan.x() + i * tw, self.pan.y() + j * tw,
                           tw, tw)
                p.drawImage(r, img)
                if self.dim_neighbors and (i or j):
                    p.fillRect(r, QColor(255, 255, 255, 70))
        if self.show_border:
            pen = QPen(QColor(0, 0, 0, 160), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self.pan.x(), self.pan.y(), tw, tw))
            p.setPen(QPen(QColor(255, 255, 255, 140), 1,
                          Qt.PenStyle.DotLine))
            p.drawRect(QRectF(self.pan.x() + 1, self.pan.y() + 1,
                              tw - 2, tw - 2))
        self._paint_overlay(p)
        p.end()

    def _checker(self, p, rect):
        p.save()
        p.setClipRect(rect)
        s = 10
        p.fillRect(rect, QColor("#ffffff"))
        c = QColor("#d8d8d8")
        y = int(rect.top())
        row = 0
        while y < rect.bottom():
            x = int(rect.left()) + (s if row % 2 else 0)
            while x < rect.right():
                p.fillRect(x, y, s, s, c)
                x += 2 * s
            y += s
            row += 1
        p.restore()

    def _view_transform(self) -> QTransform:
        t = QTransform()
        t.translate(self.pan.x(), self.pan.y())
        t.scale(self.zoom, self.zoom)
        return t

    def _paint_overlay(self, p: QPainter):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        vt = self._view_transform()
        sel = self.win.selected_items()
        hi = self.palette().color(self.palette().ColorRole.Highlight)
        # selection outlines (including wrapped copies near seams)
        for it in sel:
            outline = self._outline(it)
            for ox, oy in render.wrap_offsets(render.item_bounds(it),
                                              self.T()):
                path = vt.map(outline.translated(ox, oy))
                p.setPen(QPen(QColor(255, 255, 255, 200), 3))
                p.drawPath(path)
                p.setPen(QPen(hi, 1.5))
                p.drawPath(path)
        if sel and self.tool is Tool.SELECT:
            self._paint_handles(p, sel, hi)
        d = self._drag
        if d and d.get("mode") == "rubber":
            r = QRectF(self.to_screen(d["start"]),
                       self.to_screen(d["cur"])).normalized()
            p.setPen(QPen(hi, 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(hi.red(), hi.green(), hi.blue(), 40))
            p.drawRect(r)
        if d and d.get("mode") == "create" and d.get("preview"):
            p.setPen(QPen(hi, 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(vt.map(render.item_path(d["preview"])))
        if self._pen_nodes:
            path = QPainterPath()
            segs = self._pen_segments(closed=False, preview=self._hover)
            path = vt.map(render.segments_path(segs))
            p.setPen(QPen(hi, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setBrush(QColor("#ffffff"))
            for n in self._pen_nodes:
                sp = self.to_screen(QPointF(n[0], n[1]))
                p.drawRect(QRectF(sp.x() - 3, sp.y() - 3, 6, 6))
                if n[2] or n[3]:
                    for s in (1, -1):
                        hp = self.to_screen(QPointF(n[0] + s * n[2],
                                                    n[1] + s * n[3]))
                        p.drawLine(sp, hp)
                        p.drawEllipse(hp, 2.5, 2.5)

    def _outline(self, it: Item) -> QPainterPath:
        if it.kind in (IMAGE, SVG, PATH):
            path = QPainterPath()
            path.addPolygon(render.item_transform(it).map(_unit_poly()))
            path.closeSubpath()
            if it.kind == PATH:
                path.addPath(render.item_path(it))
            return path
        return render.item_path(it)

    # handles: list of (kind, screen_point, data)
    def _handles(self, sel):
        if not sel:
            return []
        if len(sel) == 1:
            it = sel[0]
            t = render.item_transform(it)
            out = []
            for hx in (-1, 0, 1):
                for hy in (-1, 0, 1):
                    if hx == 0 and hy == 0:
                        continue
                    pt = t.map(QPointF(0.5 * hx, 0.5 * hy))
                    out.append(("scale", self.to_screen(pt), (hx, hy)))
            top = t.map(QPointF(0, -0.5))
            ctr = QPointF(it.cx, it.cy)
            v = top - ctr
            ln = math.hypot(v.x(), v.y()) or 1
            rot_pt = top + v * (24 / self.zoom / ln)
            out.append(("rotate", self.to_screen(rot_pt), None))
            return out
        r = self._sel_bounds(sel)
        out = []
        for hx in (-1, 0, 1):
            for hy in (-1, 0, 1):
                if hx == 0 and hy == 0:
                    continue
                pt = QPointF(r.center().x() + hx * r.width() / 2,
                             r.center().y() + hy * r.height() / 2)
                out.append(("scale", self.to_screen(pt), (hx, hy)))
        out.append(("rotate", self.to_screen(
            QPointF(r.center().x(), r.top() - 24 / self.zoom)), None))
        return out

    def _sel_bounds(self, sel) -> QRectF:
        r = QRectF()
        for it in sel:
            b = render.item_transform(it).mapRect(render.UNIT) \
                if it.kind in (IMAGE, SVG) else \
                render.item_path(it).boundingRect()
            r = b if r.isNull() else r.united(b)
        return r

    def _paint_handles(self, p, sel, hi):
        p.setPen(QPen(hi, 1.2))
        hs = self._handles(sel)
        for kind, sp, _d in hs:
            if kind == "rotate":
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(sp, HANDLE_PX / 2 + 1, HANDLE_PX / 2 + 1)
            else:
                p.setBrush(QColor("#ffffff"))
                p.drawRect(QRectF(sp.x() - HANDLE_PX / 2,
                                  sp.y() - HANDLE_PX / 2,
                                  HANDLE_PX, HANDLE_PX))

    # ------------------------------------------------------ hit testing
    def item_at(self, pt: QPointF, layers=None):
        """Topmost (layer, item) under tile point `pt` (wrap-aware)."""
        T = self.T()
        w = self.wrap(pt)
        tol = 4 / self.zoom
        order = layers if layers is not None else self._pick_order()
        for lay in order:
            for it in reversed(lay.items):
                for ox in (0, -T, T):
                    for oy in (0, -T, T):
                        if render.hit_test(it, w.x() + ox, w.y() + oy,
                                           tol):
                            return lay, it
        return None, None

    def _pick_order(self):
        doc = self.doc
        act = doc.layer(self.win.active_layer_id)
        rest = [l for l in reversed(doc.layers) if l is not act]
        cands = ([act] if act else []) + rest
        return [l for l in cands if l.visible and not l.locked
                and l.kind != GENERATOR]

    def _handle_at(self, pos):
        sel = self.win.selected_items()
        for kind, sp, data in self._handles(sel):
            if abs(sp.x() - pos.x()) <= HANDLE_PX and \
                    abs(sp.y() - pos.y()) <= HANDLE_PX:
                return kind, data
        return None

    # ----------------------------------------------------------- mouse
    def mousePressEvent(self, ev):
        self.setFocus()
        pos = ev.position()
        pt = self.to_tile(pos)
        if ev.button() == Qt.MouseButton.MiddleButton or self._space or (
                self.tool is Tool.PAN
                and ev.button() == Qt.MouseButton.LeftButton):
            self._drag = {"mode": "pan", "last": pos}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self.tool is Tool.SELECT:
            self._press_select(pos, pt, shift)
        elif self.tool in SHAPE_TOOLS or self.tool is Tool.LINE:
            w = self.wrap(pt)
            off = QPointF(w.x() - pt.x(), w.y() - pt.y())
            self._drag = {"mode": "create", "start": w, "cur": w,
                          "off": off, "preview": None}
        elif self.tool is Tool.PEN:
            if not self._pen_nodes:
                w = self.wrap(pt)
                self._pen_off = QPointF(w.x() - pt.x(), w.y() - pt.y())
            else:
                w = self._pen_local(pt)
            if len(self._pen_nodes) > 2:
                first = self._pen_nodes[0]
                fs = self.to_screen(QPointF(first[0], first[1]))
                if math.hypot(fs.x() - pos.x(), fs.y() - pos.y()) < 8:
                    self._finish_pen(True)
                    return
            self._pen_nodes.append([w.x(), w.y(), 0.0, 0.0])
            self._drag = {"mode": "pen", "start": w}
            self.update()
        elif self.tool is Tool.EYEDROPPER:
            self._pick_color(pt, shift)

    def _pen_local(self, pt):
        """Pen points share the first point's wrap offset, so a path can
        run across a seam without being torn apart."""
        off = getattr(self, "_pen_off", QPointF(0, 0))
        return QPointF(pt.x() + off.x(), pt.y() + off.y())

    def _press_select(self, pos, pt, shift):
        h = self._handle_at(pos)
        sel = self.win.selected_items()
        if h and sel:
            kind, data = h
            self.win.begin_edit()
            self._drag = {"mode": kind, "start": pt, "handle": data,
                          "orig": [i.to_dict() for i in sel],
                          "bounds": self._sel_bounds(sel),
                          "ids": [i.id for i in sel]}
            return
        lay, it = self.item_at(pt)
        if it is not None:
            if lay.id != self.win.active_layer_id:
                self.win.set_active_layer(lay.id, keep_selection=False)
            ids = list(self.win.selection)
            if shift:
                if it.id in ids:
                    ids.remove(it.id)
                else:
                    ids.append(it.id)
                self.win.set_selection(ids)
                return
            if it.id not in ids:
                self.win.set_selection([it.id])
            sel = self.win.selected_items()
            self.win.begin_edit()
            # anchor the drag to the copy of the item that was clicked
            self._drag = {"mode": "move", "start": pt,
                          "orig": [i.to_dict() for i in sel],
                          "ids": [i.id for i in sel], "moved": False}
            return
        if not shift:
            self.win.set_selection([])
        self._drag = {"mode": "rubber", "start": pt, "cur": pt,
                      "add": shift}

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        pt = self.to_tile(pos)
        self.win.show_coords(self.wrap(pt))
        d = self._drag
        if self._pen_nodes:
            self._hover = self._pen_local(pt)
        if not d:
            if self.tool is Tool.SELECT:
                h = self._handle_at(pos)
                if h:
                    self.setCursor(Qt.CursorShape.CrossCursor
                                   if h[0] == "rotate"
                                   else Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._pen_nodes:
                self.update()
            return
        mode = d["mode"]
        shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(ev.modifiers() & Qt.KeyboardModifier.AltModifier)
        if mode == "pan":
            delta = pos - d["last"]
            d["last"] = pos
            self.pan += delta
            self.update()
        elif mode == "move":
            dx, dy = pt.x() - d["start"].x(), pt.y() - d["start"].y()
            if shift:
                if abs(dx) > abs(dy):
                    dy = 0
                else:
                    dx = 0
            for it, o in zip(self.win.selected_items(), d["orig"]):
                it.cx, it.cy = o["cx"] + dx, o["cy"] + dy
            d["moved"] = True
            self.invalidate()
        elif mode == "scale":
            self._drag_scale(pt, shift)
            self.invalidate()
        elif mode == "rotate":
            self._drag_rotate(pt, shift)
            self.invalidate()
        elif mode == "rubber":
            d["cur"] = pt
            self.update()
        elif mode == "create":
            cur = QPointF(pt.x() + d["off"].x(), pt.y() + d["off"].y())
            d["cur"] = cur
            d["preview"] = self._shape_from_drag(d["start"], cur, shift,
                                                 alt)
            self.update()
        elif mode == "pen":
            n = self._pen_nodes[-1]
            lp = self._pen_local(pt)
            n[2], n[3] = lp.x() - n[0], lp.y() - n[1]
            self.update()

    def mouseReleaseEvent(self, ev):
        d = self._drag
        self._drag = None
        if not d:
            return
        mode = d["mode"]
        if mode == "pan":
            self.set_tool(self.tool) if not self._space else \
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if mode == "move":
            if d.get("moved"):
                self._normalize_selection()
                self.win.end_edit("Move")
            else:
                self.win.cancel_edit()
        elif mode in ("scale", "rotate"):
            self._normalize_selection()
            self.win.end_edit("Scale" if mode == "scale" else "Rotate")
        elif mode == "rubber":
            r = QRectF(d["start"], d["cur"]).normalized()
            lay = self.doc.layer(self.win.active_layer_id)
            if lay and lay.kind != GENERATOR and r.width() > 1 / self.zoom:
                hits = [it.id for it in lay.items
                        if r.intersects(render.item_bounds(it))
                        or any(r.translated(-ox, -oy).intersects(
                            render.item_bounds(it))
                            for ox in (-self.T(), 0, self.T())
                            for oy in (-self.T(), 0, self.T()))]
                ids = list(self.win.selection) if d["add"] else []
                self.win.set_selection(ids + [h for h in hits
                                              if h not in ids])
            self.update()
        elif mode == "create":
            shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            alt = bool(ev.modifiers() & Qt.KeyboardModifier.AltModifier)
            it = self._shape_from_drag(d["start"], d["cur"], shift, alt)
            if max(it.w, it.h) * self.zoom < 4:
                it = self._shape_from_drag(d["start"], d["start"], shift,
                                           alt, default=True)
            self.win.add_item(it)
        elif mode == "pen":
            self.update()

    def mouseDoubleClickEvent(self, ev):
        if self.tool is Tool.PEN and self._pen_nodes:
            # the double-click's first press already added a node
            if len(self._pen_nodes) > 1:
                self._pen_nodes.pop()
            self._finish_pen(False)
            return
        if self.tool is Tool.SELECT:
            lay, it = self.item_at(self.to_tile(ev.position()))
            if it is not None:
                self.win.focus_item_settings()

    def wheelEvent(self, ev):
        delta = ev.angleDelta().y()
        if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.pan += QPointF(delta / 2, 0)
            self.update()
            return
        if not delta:
            return
        self.zoom_by(1.15 if delta > 0 else 1 / 1.15, ev.position())

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self._pen_nodes and k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish_pen(False)
            return
        if k == Qt.Key.Key_Escape:
            if self._pen_nodes:
                self._pen_nodes = []
                self.update()
            else:
                self.win.set_selection([])
            return
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.win.delete_selection()
            return
        arrows = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                  Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if k in arrows and self.win.selection:
            step = 10 if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier \
                else 1
            dx, dy = arrows[k]
            self.win.nudge(dx * step, dy * step)
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space = False
            self.set_tool(self.tool)
            return
        super().keyReleaseEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if not self._fitted and self.width() > 100:
            self._fitted = True
            QTimer.singleShot(0, self.fit)

    # ------------------------------------------------------ tool logic
    def _shape_from_drag(self, a: QPointF, b: QPointF, square: bool,
                         from_center: bool, default: bool = False) -> Item:
        style = self.win.current_style()
        if default:
            s = 120.0
            b = QPointF(a.x() + s / 2, a.y() + s / 2)
            from_center = True
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if self.tool is Tool.LINE:
            if square:   # snap to 45 degrees
                ang = round(math.atan2(dy, dx) / (math.pi / 4)) * math.pi / 4
                ln = math.hypot(dx, dy)
                dx, dy = ln * math.cos(ang), ln * math.sin(ang)
            if default:
                dx, dy = 120.0, 0.0
            return make_path_item([["M", a.x(), a.y()],
                                   ["L", a.x() + dx, a.y() + dy]],
                                  style)
        if square:
            s = max(abs(dx), abs(dy))
            dx = math.copysign(s, dx or 1)
            dy = math.copysign(s, dy or 1)
        if from_center:
            cx, cy, w, h = a.x(), a.y(), abs(dx) * 2, abs(dy) * 2
        else:
            cx, cy = a.x() + dx / 2, a.y() + dy / 2
            w, h = abs(dx), abs(dy)
        kind = SHAPE_TOOLS.get(self.tool, RECT)
        opts = self.win.shape_options()
        return Item(kind, cx=cx, cy=cy, w=max(w, 1), h=max(h, 1),
                    fill=style["fill"], stroke=style["stroke"],
                    stroke_width=style["stroke_width"],
                    sides=opts["sides"] if kind == POLYGON
                    else opts["points"],
                    inner_ratio=opts["inner_ratio"],
                    corner_radius=opts["corner_radius"]
                    if kind == RECT else 0.0)

    def _pen_segments(self, closed: bool, preview=None) -> list:
        nodes = [list(n) for n in self._pen_nodes]
        if preview is not None and self._drag is None:
            nodes.append([preview.x(), preview.y(), 0.0, 0.0])
        if not nodes:
            return []
        segs = [["M", nodes[0][0], nodes[0][1]]]
        pairs = list(zip(nodes, nodes[1:]))
        if closed and len(nodes) > 2:
            pairs.append((nodes[-1], nodes[0]))
        for a, b in pairs:
            if a[2] or a[3] or b[2] or b[3]:
                segs.append(["C", a[0] + a[2], a[1] + a[3],
                             b[0] - b[2], b[1] - b[3], b[0], b[1]])
            else:
                segs.append(["L", b[0], b[1]])
        if closed:
            segs.append(["Z"])
        return segs

    def _finish_pen(self, closed: bool):
        if len(self._pen_nodes) >= 2:
            segs = self._pen_segments(closed)
            it = make_path_item(segs, self.win.current_style())
            self._pen_nodes = []
            self.win.add_item(it)
        else:
            self._pen_nodes = []
        self._hover = None
        self.update()

    def _pick_color(self, pt, stroke: bool):
        img = self.tile_image()
        w = self.wrap(pt)
        s = img.width() / self.T()
        c = img.pixelColor(int(min(img.width() - 1, w.x() * s)),
                           int(min(img.height() - 1, w.y() * s)))
        self.color_picked.emit(c.name(), stroke)

    def _normalize_selection(self):
        T = self.T()
        for it in self.win.selected_items():
            it.cx %= T
            it.cy %= T

    def _drag_scale(self, pt, keep_aspect):
        d = self._drag
        sel = self.win.selected_items()
        hx, hy = d["handle"]
        if len(sel) == 1:
            o = d["orig"][0]
            it = sel[0]
            a = math.radians(o["rotation"])
            ca, sa = math.cos(a), math.sin(a)
            mx, my = pt.x() - o["cx"], pt.y() - o["cy"]
            lx, ly = mx * ca + my * sa, -mx * sa + my * ca
            w0, h0 = o["w"], o["h"]
            ax, ay = -hx * w0 / 2, -hy * h0 / 2
            nw = abs(lx - ax) if hx else w0
            nh = abs(ly - ay) if hy else h0
            if keep_aspect and hx and hy:
                s = max(nw / max(w0, 1e-6), nh / max(h0, 1e-6))
                nw, nh = w0 * s, h0 * s
            nw, nh = max(nw, 1.0), max(nh, 1.0)
            ncx = ax + hx * nw / 2 if hx else 0.0
            ncy = ay + hy * nh / 2 if hy else 0.0
            it.w, it.h = nw, nh
            it.cx = o["cx"] + ncx * ca - ncy * sa
            it.cy = o["cy"] + ncx * sa + ncy * ca
            return
        r = d["bounds"]
        ax = r.center().x() - hx * r.width() / 2
        ay = r.center().y() - hy * r.height() / 2
        sx0 = d["start"].x() - ax
        sy0 = d["start"].y() - ay
        sx = (pt.x() - ax) / sx0 if hx and abs(sx0) > 1e-6 else 1.0
        sy = (pt.y() - ay) / sy0 if hy and abs(sy0) > 1e-6 else 1.0
        if keep_aspect:
            s = max(abs(sx), abs(sy)) if hx and hy else (
                abs(sx) if hx else abs(sy))
            sx = sy = s
        sx, sy = max(abs(sx), 0.01), max(abs(sy), 0.01)
        for it, o in zip(sel, d["orig"]):
            it.cx = ax + (o["cx"] - ax) * sx
            it.cy = ay + (o["cy"] - ay) * sy
            rot = math.radians(o["rotation"])
            c2, s2 = math.cos(rot) ** 2, math.sin(rot) ** 2
            it.w = o["w"] * (sx * c2 + sy * s2)
            it.h = o["h"] * (sy * c2 + sx * s2)

    def _drag_rotate(self, pt, snap):
        d = self._drag
        sel = self.win.selected_items()
        if len(sel) == 1:
            c = QPointF(d["orig"][0]["cx"], d["orig"][0]["cy"])
        else:
            c = d["bounds"].center()
        a0 = math.atan2(d["start"].y() - c.y(), d["start"].x() - c.x())
        a1 = math.atan2(pt.y() - c.y(), pt.x() - c.x())
        da = math.degrees(a1 - a0)
        if snap:
            if len(sel) == 1:
                tgt = round((d["orig"][0]["rotation"] + da) / 15) * 15
                da = tgt - d["orig"][0]["rotation"]
            else:
                da = round(da / 15) * 15
        r = math.radians(da)
        cr, sr = math.cos(r), math.sin(r)
        for it, o in zip(sel, d["orig"]):
            dx, dy = o["cx"] - c.x(), o["cy"] - c.y()
            it.cx = c.x() + dx * cr - dy * sr
            it.cy = c.y() + dx * sr + dy * cr
            it.rotation = (o["rotation"] + da) % 360


def _unit_poly():
    from PySide6.QtGui import QPolygonF
    return QPolygonF([QPointF(-0.5, -0.5), QPointF(0.5, -0.5),
                      QPointF(0.5, 0.5), QPointF(-0.5, 0.5)])
