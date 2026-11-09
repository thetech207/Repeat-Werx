"""Repeat-Werx main window."""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QSettings, QPoint, QEvent, QTimer, QRect
from PySide6.QtGui import (QAction, QActionGroup, QKeySequence, QIcon,
                           QPixmap, QPainter, QColor, QUndoStack)
from PySide6.QtWidgets import (QApplication, QMainWindow, QToolBar,
                               QDockWidget, QWidget, QVBoxLayout, QSplitter,
                               QLabel, QFileDialog, QMessageBox, QToolButton,
                               QDoubleSpinBox, QSpinBox, QUndoView, QDialog,
                               QTextBrowser, QSplashScreen,
                               QDialogButtonBox)

from . import __version__, __author__
from .core.model import (Document, Layer, Item, VECTOR, RASTER, GENERATOR,
                         IMAGE, SVG, SHAPE_KINDS, default_generator, new_id)
from .core import project as project_io
from .core import render, imageproc
from .core import color as colors
from .core.generators import generate, area_factor
from .gui import theme
from .gui.canvas import TileCanvas, Tool
from .gui.commands import SnapshotCommand
from .gui.icons import icon
from .gui.layers_panel import LayersPanel
from .gui.settings_panel import SettingsPanel
from .gui.widgets import ColorButton

TOOL_TIPS = [
    (Tool.SELECT, "select", "Select / move / scale / rotate  (V)", "V"),
    (Tool.RECT, "rect", "Rectangle — Shift: square, Alt: from center  (R)",
     "R"),
    (Tool.ELLIPSE, "ellipse", "Ellipse — Shift: circle, Alt: from center  "
     "(E)", "E"),
    (Tool.POLYGON, "polygon", "Regular polygon  (G)", "G"),
    (Tool.STAR, "star", "Star  (S)", "S"),
    (Tool.LINE, "line", "Line — Shift snaps to 45°  (L)", "L"),
    (Tool.PEN, "pen", "Pen — click for corners, drag for curves, click the "
     "first point to close, double-click/Enter to finish  (P)", "P"),
    (Tool.EYEDROPPER, "eyedropper", "Eyedropper — click: fill, "
     "Shift-click: outline  (I)", "I"),
    (Tool.PAN, "pan", "Pan — or hold Space / middle mouse  (H)", "H"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1360, 860)
        self._settings = QSettings("RepeatWerx", "RepeatWerx")
        theme.apply_theme(self._settings.value("ui/theme", "system"))
        self.doc = Document()
        self.active_layer_id = self.doc.layers[-1].id
        self.selection: list[str] = []
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self._edit_before = None
        self._clip: list = []
        self._clip_assets: dict = {}
        self._file_path: str | None = None
        self._style = {
            "fill": self._settings.value("style/fill", "#4a7ab5"),
            "stroke": self._settings.value("style/stroke", "#1c1c1c"),
            "stroke_width": float(self._settings.value("style/width", 2.0)),
        }
        if self._style["fill"] == "none":
            self._style["fill"] = None
        if self._style["stroke"] == "none":
            self._style["stroke"] = None
        self.setAcceptDrops(True)
        self._build_ui()
        self._build_menus()
        self.changed()

    # ============================================================ UI
    def _build_ui(self):
        self.canvas = TileCanvas(self)
        self.setCentralWidget(self.canvas)
        self.canvas.color_picked.connect(self.set_current_color)
        self.canvas.tool_changed.connect(self._on_tool_changed)
        self.canvas.zoom_changed.connect(
            lambda z: self.zoom_label.setText(f"{z * 100:.0f}%"))
        self.canvas.repeat_n = int(self._settings.value("view/repeat", 3))
        self.canvas.dim_neighbors = \
            self._settings.value("view/dim", "true") == "true"
        self.canvas.show_border = \
            self._settings.value("view/border", "true") == "true"

        # left tools
        tb = QToolBar("Tools")
        tb.setObjectName("Tools")
        tb.setIconSize(QSize(26, 26))
        tb.setMovable(False)
        self._tools_bar = tb
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tb)
        self.tool_actions = {}
        grp = QActionGroup(self)
        for tool, ic, tip, key in TOOL_TIPS:
            a = QAction(icon(ic), tip, self)
            a.setCheckable(True)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, t=tool: self.canvas.set_tool(t))
            grp.addAction(a)
            tb.addAction(a)
            self.tool_actions[tool] = a
        self.tool_actions[Tool.SELECT].setChecked(True)
        tb.addSeparator()
        self.fill_btn = ColorButton(self._style["fill"], allow_none=True)
        self.fill_btn.setToolTip("Fill color (right-click for none)")
        self.fill_btn.color_changed.connect(
            lambda c: self._set_style("fill", c))
        self.stroke_btn = ColorButton(self._style["stroke"], allow_none=True,
                                      stroke=True)
        self.stroke_btn.color_changed.connect(
            lambda c: self._set_style("stroke", c))
        for b in (self.fill_btn, self.stroke_btn):
            b.setIconSize(QSize(24, 24))
            tb.addWidget(b)

        # top options bar
        ob = QToolBar("Options")
        ob.setObjectName("Options")
        ob.setMovable(False)
        ob.setIconSize(QSize(20, 20))
        self._opts_bar = ob
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, ob)
        ob.addWidget(QLabel("Outline"))
        self.sw_spin = QDoubleSpinBox()
        self.sw_spin.setRange(0, 200)
        self.sw_spin.setDecimals(1)
        self.sw_spin.setValue(self._style["stroke_width"])
        self.sw_spin.valueChanged.connect(
            lambda v: self._set_style("stroke_width", v))
        ob.addWidget(self.sw_spin)
        ob.addSeparator()
        ob.addWidget(QLabel("Sides"))
        self.sides_spin = QSpinBox()
        self.sides_spin.setRange(3, 64)
        self.sides_spin.setValue(int(self._settings.value("shape/sides", 6)))
        ob.addWidget(self.sides_spin)
        ob.addWidget(QLabel("Points"))
        self.points_spin = QSpinBox()
        self.points_spin.setRange(3, 64)
        self.points_spin.setValue(int(self._settings.value("shape/points",
                                                           5)))
        ob.addWidget(self.points_spin)
        ob.addWidget(QLabel("Inner"))
        self.inner_spin = QDoubleSpinBox()
        self.inner_spin.setRange(0.05, 0.95)
        self.inner_spin.setSingleStep(0.05)
        self.inner_spin.setValue(float(self._settings.value("shape/inner",
                                                            0.45)))
        ob.addWidget(self.inner_spin)
        ob.addWidget(QLabel("Corner"))
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0, 1000)
        ob.addWidget(self.radius_spin)
        ob.addSeparator()
        for ic, tip, fn in (("import", "Import image or SVG…",
                             self.import_file),
                            ("export", "Export…", self.export)):
            a = ob.addAction(icon(ic), tip)
            a.triggered.connect(fn)
        ob.addSeparator()
        a = ob.addAction(icon("repeat"), "Fit repeat view")
        a.triggered.connect(self.canvas.fit)
        a = ob.addAction(icon("fit"), "Fit the center tile")
        a.triggered.connect(self.canvas.fit_tile)
        self.zoom_label = QLabel("100%")
        ob.addWidget(self.zoom_label)

        # right dock: layers + settings
        right = QWidget()
        right.setObjectName("SidePanel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        self.layers_panel = LayersPanel(self)
        self.settings_panel = SettingsPanel(self)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.addWidget(self.layers_panel)
        self.right_splitter.addWidget(self.settings_panel)
        self.right_splitter.setStretchFactor(0, 0)
        self.right_splitter.setStretchFactor(1, 1)
        self.right_splitter.setSizes([230, 600])
        rl.addWidget(self.right_splitter)
        self._side_panel = right
        dock = QDockWidget("Layers && Settings", self)
        dock.setObjectName("SideDock")
        dock.setWidget(right)
        dock.setMinimumWidth(330)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.right_dock = dock
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        self.undo_view = QUndoView(self.undo_stack)
        hd = QDockWidget("History", self)
        hd.setObjectName("HistoryDock")
        hd.setWidget(self.undo_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, hd)
        hd.hide()
        self.history_dock = hd

        # collapse tab on the dock's left edge (as in Black-Werx)
        self.panel_tab = QToolButton(self)
        self.panel_tab.setFixedSize(12, 72)
        self.panel_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.panel_tab.setToolTip("Collapse/expand the side panel")
        self.panel_tab.clicked.connect(self._toggle_right_panel)
        self.canvas.installEventFilter(self)

        self.status_coords = QLabel("")
        self.status_info = QLabel("")
        self.statusBar().addWidget(self.status_coords)
        self.statusBar().addPermanentWidget(self.status_info)
        self._apply_styles()
        geo = self._settings.value("ui/geometry")
        if geo:
            self.restoreGeometry(geo)
        st = self._settings.value("ui/state")
        if st:
            self.restoreState(st)
        QTimer.singleShot(0, self._position_panel_tab)

    def _apply_styles(self):
        self._tools_bar.setStyleSheet(theme.bar_qss("Tools", "right"))
        self._opts_bar.setStyleSheet(theme.bar_qss("Options", "bottom"))
        self._side_panel.setStyleSheet(theme.side_panel_qss())
        self.panel_tab.setStyleSheet(theme.panel_tab_qss())
        icons = {t: ic for t, ic, _tip, _k in TOOL_TIPS}
        for tool, a in self.tool_actions.items():
            a.setIcon(icon(icons[tool]))

    def _set_theme(self, mode):
        self._settings.setValue("ui/theme", mode)
        for m, a in self._theme_acts.items():
            a.setChecked(m == mode)
        theme.apply_theme(mode)
        self._apply_styles()
        self.layers_panel.refresh()
        self.canvas.update()

    def _toggle_right_panel(self):
        self.right_dock.setVisible(not self.right_dock.isVisible())
        QTimer.singleShot(0, self._position_panel_tab)

    def _position_panel_tab(self):
        tab = self.panel_tab
        cv = self.canvas
        right = cv.mapTo(self, QPoint(cv.width(), 0)).x()
        top = cv.mapTo(self, QPoint(0, 0)).y()
        tab.move(right - tab.width(),
                 top + max(0, (cv.height() - tab.height()) // 2))
        tab.setText("❯" if self.right_dock.isVisible() else "❮")
        tab.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.canvas and ev.type() == QEvent.Type.Resize:
            self._position_panel_tab()
        return super().eventFilter(obj, ev)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "&New", self.new_project, QKeySequence.StandardKey.New)
        self._act(m, "&Open…", self.open_project,
                  QKeySequence.StandardKey.Open)
        self.recent_menu = m.addMenu("Open &Recent")
        self._refresh_recent()
        self._act(m, "&Save", self.save_project,
                  QKeySequence.StandardKey.Save)
        self._act(m, "Save &As…", self.save_project_as,
                  QKeySequence.StandardKey.SaveAs)
        m.addSeparator()
        self._act(m, "&Import Image / SVG…", self.import_file, "Ctrl+I")
        self._act(m, "&Export…", self.export, "Ctrl+E")
        m.addSeparator()
        self._act(m, "Save Pattern Preset…", self.save_preset)
        self._act(m, "Load Pattern Preset…", self.load_preset)
        m.addSeparator()
        self._act(m, "&Quit", self.close, QKeySequence.StandardKey.Quit)

        m = mb.addMenu("&Edit")
        u = self.undo_stack.createUndoAction(self, "&Undo")
        u.setShortcut(QKeySequence.StandardKey.Undo)
        r = self.undo_stack.createRedoAction(self, "&Redo")
        r.setShortcut(QKeySequence.StandardKey.Redo)
        m.addAction(u)
        m.addAction(r)
        m.addSeparator()
        self._act(m, "Cu&t", self.cut, QKeySequence.StandardKey.Cut)
        self._act(m, "&Copy", self.copy, QKeySequence.StandardKey.Copy)
        self._act(m, "&Paste", self.paste, QKeySequence.StandardKey.Paste)
        self._act(m, "&Duplicate", self.duplicate, "Ctrl+D")
        self._act(m, "De&lete", self.delete_selection)
        m.addSeparator()
        self._act(m, "Select &All", self.select_all,
                  QKeySequence.StandardKey.SelectAll)
        self._act(m, "Deselect", lambda: self.set_selection([]),
                  "Ctrl+Shift+A")

        m = mb.addMenu("&Arrange")
        self._act(m, "Bring to Front", lambda: self.arrange(999),
                  "Ctrl+Shift+]")
        self._act(m, "Bring Forward", lambda: self.arrange(1), "Ctrl+]")
        self._act(m, "Send Backward", lambda: self.arrange(-1), "Ctrl+[")
        self._act(m, "Send to Back", lambda: self.arrange(-999),
                  "Ctrl+Shift+[")
        m.addSeparator()
        self._act(m, "Flip Horizontal", lambda: self.flip_selection("x"))
        self._act(m, "Flip Vertical", lambda: self.flip_selection("y"))

        m = mb.addMenu("&Layer")
        self._act(m, "New Vector Layer", lambda: self.add_layer(VECTOR),
                  "Ctrl+Shift+N")
        self._act(m, "New Raster Layer", lambda: self.add_layer(RASTER))
        self._act(m, "New Generator Layer",
                  lambda: self.add_layer(GENERATOR), "Ctrl+Shift+G")
        m.addSeparator()
        self._act(m, "Duplicate Layer",
                  lambda: self.duplicate_layer(self.active_layer_id))
        self._act(m, "Merge Down",
                  lambda: self.merge_down(self.active_layer_id), "Ctrl+M")
        self._act(m, "Convert to Raster",
                  lambda: self.convert_to_raster(self.active_layer_id))
        self._act(m, "Bake Generator",
                  lambda: self.bake_layer(self.active_layer_id), "Ctrl+B")
        self._act(m, "Delete Layer",
                  lambda: self.delete_layer(self.active_layer_id))

        m = mb.addMenu("&View")
        self._act(m, "Fit Repeat", self.canvas.fit, "Ctrl+0")
        self._act(m, "Fit Tile", self.canvas.fit_tile, "Ctrl+1")
        self._act(m, "Zoom In", lambda: self.canvas.zoom_by(1.25),
                  QKeySequence.StandardKey.ZoomIn)
        self._act(m, "Zoom Out", lambda: self.canvas.zoom_by(0.8),
                  QKeySequence.StandardKey.ZoomOut)
        m.addSeparator()
        for n in (1, 3, 5):
            self._act(m, f"Repeat {n} × {n}",
                      lambda _=False, k=n: self.set_repeat(k))
        m.addSeparator()
        tm = m.addMenu("&Theme")
        self._theme_acts = {}
        cur = self._settings.value("ui/theme", "system")
        for mode, lab in (("system", "System"), ("light", "Light"),
                          ("dark", "Dark")):
            a = tm.addAction(lab)
            a.setCheckable(True)
            a.setChecked(mode == cur)
            a.triggered.connect(lambda _=False, md=mode: self._set_theme(md))
            self._theme_acts[mode] = a
        m.addAction(self.history_dock.toggleViewAction())
        m.addAction(self.right_dock.toggleViewAction())

        m = mb.addMenu("&Help")
        self._act(m, "User Guide", self.user_guide, "F1")
        self._act(m, "About Repeat-Werx", self.about)

    def _act(self, menu, text, fn, shortcut=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(fn)
        menu.addAction(a)
        return a

    # ====================================================== state
    def changed(self):
        lids = {l.id for l in self.doc.layers}
        if self.active_layer_id not in lids:
            self.active_layer_id = self.doc.layers[-1].id \
                if self.doc.layers else None
        lay = self.doc.layer(self.active_layer_id)
        valid = {i.id for i in lay.items} if lay else set()
        self.selection = [i for i in self.selection if i in valid]
        self.canvas.invalidate()
        self.layers_panel.refresh()
        self.settings_panel.refresh()
        self._update_title()
        self._update_status()

    def _on_clean_changed(self, _clean):
        try:
            self._update_title()
        except RuntimeError:
            pass

    def _update_title(self):
        name = Path(self._file_path).name if self._file_path else \
            self.doc.name
        dirty = "" if self.undo_stack.isClean() else " *"
        self.setWindowTitle(f"{name}{dirty} — Repeat-Werx")

    def _update_status(self):
        n = sum(len(l.items) for l in self.doc.layers
                if l.kind != GENERATOR)
        T = self.doc.tile_size
        self.status_info.setText(
            f"Tile {T}×{T} · {len(self.doc.layers)} layers · {n} items · "
            f"{len(self.selection)} selected")

    def show_coords(self, pt):
        self.status_coords.setText(f"x {pt.x():.0f}  y {pt.y():.0f}")

    def restore_state(self, state, sel):
        self.doc.restore(state)
        self.selection = list(sel)
        self.changed()

    def _push(self, label, before, sel_before, merge_key=None):
        after = self.doc.state()
        if after == before:
            return False
        self.undo_stack.push(SnapshotCommand(
            self, label, before, after, sel_before, list(self.selection),
            merge_key))
        self.changed()
        return True

    def commit(self, label, fn, merge_key=None):
        before = self.doc.state()
        sel = list(self.selection)
        fn()
        return self._push(label, before, sel, merge_key)

    def begin_edit(self):
        self._edit_before = (self.doc.state(), list(self.selection))

    def end_edit(self, label):
        if self._edit_before is None:
            return
        before, sel = self._edit_before
        self._edit_before = None
        if not self._push(label, before, sel):
            self.changed()

    def cancel_edit(self):
        self._edit_before = None

    # ================================================== selection
    def selected_items(self):
        lay = self.doc.layer(self.active_layer_id)
        if not lay:
            return []
        ids = set(self.selection)
        return [it for it in lay.items if it.id in ids]

    def set_selection(self, ids):
        self.selection = list(ids)
        self.settings_panel.refresh_item()
        if ids:
            self.settings_panel.setCurrentIndex(1)
        self._update_status()
        self.canvas.update()

    def set_active_layer(self, lid, keep_selection=False):
        if lid == self.active_layer_id:
            return
        self.active_layer_id = lid
        if not keep_selection:
            self.selection = []
        lay = self.doc.layer(lid)
        if lay and lay.kind == GENERATOR:
            self.settings_panel.setCurrentIndex(0)
        self.layers_panel.refresh()
        self.settings_panel.refresh()
        self._update_status()
        self.canvas.update()

    def focus_item_settings(self):
        self.right_dock.show()
        self.settings_panel.setCurrentIndex(1)

    def select_all(self):
        lay = self.doc.layer(self.active_layer_id)
        if lay and lay.kind != GENERATOR:
            self.set_selection([i.id for i in lay.items])

    # ===================================================== styles
    def current_style(self):
        return dict(self._style)

    def shape_options(self):
        return {"sides": self.sides_spin.value(),
                "points": self.points_spin.value(),
                "inner_ratio": self.inner_spin.value(),
                "corner_radius": self.radius_spin.value()}

    def _set_style(self, key, value):
        self._style[key] = value
        self._settings.setValue(
            {"fill": "style/fill", "stroke": "style/stroke",
             "stroke_width": "style/width"}[key],
            "none" if value is None else value)
        if self.selection:
            self.update_items(key, value)

    def set_current_color(self, color, stroke=False):
        if stroke:
            self.stroke_btn.set_color(color)
            self._set_style("stroke", color)
        else:
            self.fill_btn.set_color(color)
            self._set_style("fill", color)

    def _on_tool_changed(self, tool):
        a = self.tool_actions.get(tool)
        if a and not a.isChecked():
            a.setChecked(True)

    # ====================================================== items
    def _target_layer(self, kind):
        """Active layer if it accepts `kind` items, else a new layer."""
        want = RASTER if kind == IMAGE else VECTOR
        lay = self.doc.layer(self.active_layer_id)
        if lay and lay.kind == want and not lay.locked:
            return lay
        new = Layer(self.doc.unique_layer_name(
            "Raster" if want == RASTER else "Vector"), want)
        idx = self.doc.layer_index(self.active_layer_id)
        self.doc.layers.insert(idx + 1 if idx >= 0 else len(self.doc.layers),
                               new)
        self.active_layer_id = new.id
        return new

    def add_item(self, it: Item, label=None):
        T = self.doc.tile_size

        def fn():
            lay = self._target_layer(it.kind)
            it.cx %= T
            it.cy %= T
            lay.items.append(it)
            self.selection = [it.id]
        self.commit(label or f"Add {it.kind}", fn)
        self.settings_panel.setCurrentIndex(1)

    def update_items(self, key, value):
        sel = self.selected_items()
        if not sel:
            return
        lid = self.active_layer_id

        def fn():
            if key in ("cx", "cy") and len(sel) > 1:
                d = value - getattr(sel[0], key)
                for it in sel:
                    setattr(it, key, getattr(it, key) + d)
                return
            for it in sel:
                if key in ("fill", "stroke", "stroke_width") \
                        and it.kind in (IMAGE, SVG):
                    continue
                if key == "fill" and it.kind not in SHAPE_KINDS:
                    continue
                setattr(it, key, value)
        self.commit(f"Change {key}", fn,
                    merge_key=f"item:{key}:{lid}:{','.join(self.selection)}")

    def delete_selection(self):
        if not self.selection:
            return
        ids = set(self.selection)

        def fn():
            lay = self.doc.layer(self.active_layer_id)
            lay.items = [i for i in lay.items if i.id not in ids]
            self.selection = []
        self.commit("Delete", fn)

    def nudge(self, dx, dy):
        def fn():
            for it in self.selected_items():
                it.cx = (it.cx + dx) % self.doc.tile_size
                it.cy = (it.cy + dy) % self.doc.tile_size
        self.commit("Nudge", fn, merge_key="nudge:" + ",".join(
            self.selection))

    def flip_selection(self, axis):
        def fn():
            for it in self.selected_items():
                if axis == "x":
                    it.flip_x = not it.flip_x
                else:
                    it.flip_y = not it.flip_y
        self.commit("Flip", fn)

    def arrange(self, delta):
        lay = self.doc.layer(self.active_layer_id)
        if not lay or not self.selection:
            return
        ids = set(self.selection)

        def fn():
            items = lay.items
            sel = [i for i in items if i.id in ids]
            rest = [i for i in items if i.id not in ids]
            if delta >= 999:
                lay.items = rest + sel
            elif delta <= -999:
                lay.items = sel + rest
            else:
                order = list(items)
                rng = range(len(order) - 2, -1, -1) if delta > 0 \
                    else range(1, len(order))
                for i in rng:
                    j = i + (1 if delta > 0 else -1)
                    if order[i].id in ids and order[j].id not in ids:
                        order[i], order[j] = order[j], order[i]
                lay.items = order
        self.commit("Arrange", fn)

    def copy(self):
        sel = self.selected_items()
        if sel:
            self._clip = [i.to_dict() for i in sel]
            self._clip_assets = {i.asset: self.doc.assets[i.asset]
                                 for i in sel if i.asset in self.doc.assets}

    def cut(self):
        self.copy()
        self.delete_selection()

    def paste(self, offset=20):
        if not self._clip:
            return
        items = [Item.from_dict(d).clone() for d in self._clip]

        def fn():
            self.doc.assets.update(self._clip_assets)
            lay = self._target_layer(items[0].kind)
            for it in items:
                it.cx = (it.cx + offset) % self.doc.tile_size
                it.cy = (it.cy + offset) % self.doc.tile_size
                lay.items.append(it)
            self.selection = [i.id for i in items]
        self.commit("Paste", fn)

    def duplicate(self):
        self.copy()
        self.paste()

    def apply_palette_to_selection(self):
        sel = [i for i in self.selected_items() if i.kind in SHAPE_KINDS]
        if not sel:
            return
        pal = self.doc.palette
        cols = colors.harmony(pal["base_color"], pal["harmony"])
        shares = colors.role_shares(cols, pal["shares"])

        def area(it):
            t = it.clone()
            s = max(t.w, t.h, 1e-6)
            t.w, t.h = t.w / s, t.h / s
            return area_factor(t) * s * s

        def fn():
            order = list(range(len(sel)))
            random.Random(len(sel)).shuffle(order)
            roles = colors.assign_roles([area(i) for i in sel], shares, order)
            for it, r in zip(sel, roles):
                if render.is_closed(it):
                    it.fill = cols[r]
                else:
                    it.stroke = cols[r]
        self.commit("Apply palette", fn)

    # ===================================================== layers
    def add_layer(self, kind):
        base = {VECTOR: "Vector", RASTER: "Raster",
                GENERATOR: "Generator"}[kind]
        lay = Layer(self.doc.unique_layer_name(base), kind)
        if kind == GENERATOR:
            lay.generator["seed"] = random.randint(1, 99999)
            lay.generator["builtin_shape"] = "mixed"

        def fn():
            idx = self.doc.layer_index(self.active_layer_id)
            self.doc.layers.insert(idx + 1 if idx >= 0
                                   else len(self.doc.layers), lay)
            self.active_layer_id = lay.id
            self.selection = []
        self.commit(f"New {base.lower()} layer", fn)
        self.settings_panel.setCurrentIndex(0)

    def delete_layer(self, lid):
        if self.doc.layer(lid) is None:
            return

        def fn():
            idx = self.doc.layer_index(lid)
            self.doc.layers.pop(idx)
            if not self.doc.layers:
                self.doc.layers.append(Layer("Layer 1", VECTOR))
            self.active_layer_id = self.doc.layers[max(0, idx - 1)].id
            for l in self.doc.layers:
                if l.kind == GENERATOR and l.generator.get(
                        "motif_layer") == lid:
                    l.generator["motif_source"] = "builtin"
                    l.generator["motif_layer"] = None
            self.selection = []
        self.commit("Delete layer", fn)

    def duplicate_layer(self, lid):
        src = self.doc.layer(lid)
        if src is None:
            return

        def fn():
            d = src.to_dict()
            d["id"] = new_id()
            d["name"] = f"{src.name} copy"
            for it in d["items"]:
                it["id"] = new_id()
            lay = Layer.from_dict(d)
            self.doc.layers.insert(self.doc.layer_index(lid) + 1, lay)
            self.active_layer_id = lay.id
            self.selection = []
        self.commit("Duplicate layer", fn)

    def move_layer(self, lid, delta):
        i = self.doc.layer_index(lid)
        j = i + delta
        if i < 0 or not 0 <= j < len(self.doc.layers):
            return

        def fn():
            L = self.doc.layers
            L[i], L[j] = L[j], L[i]
        self.commit("Reorder layers", fn)

    def reorder_layers(self, ids):
        by_id = {l.id: l for l in self.doc.layers}
        if set(ids) != set(by_id):
            self.layers_panel.refresh()
            return
        self.commit("Reorder layers",
                    lambda: setattr(self.doc, "layers",
                                    [by_id[i] for i in ids]))

    def set_layer_prop(self, lid, key, value, label, merge=False):
        lay = self.doc.layer(lid)
        if lay is None:
            return
        self.commit(label, lambda: setattr(lay, key, value),
                    merge_key=f"layer:{lid}:{key}" if merge else None)

    def toggle_layer_lock(self, lid):
        lay = self.doc.layer(lid)
        if lay:
            self.set_layer_prop(lid, "locked", not lay.locked,
                                "Unlock layer" if lay.locked
                                else "Lock layer")
            if lay.locked:
                self.selection = []

    def _rasterize(self, lay) -> Item:
        T = self.doc.tile_size
        px = int(min(4096, T * 2))
        img = render.render_layer_image(self.doc, lay, px)
        key = imageproc.add_image_asset(self.doc, img, lay.name)
        return Item(IMAGE, cx=T / 2, cy=T / 2, w=T, h=T, fill=None,
                    stroke=None, stroke_width=0, asset=key)

    def _baked(self, lay) -> Layer:
        items, _st = generate(lay, self.doc)
        items = [i.clone() for i in items]
        if any(i.kind == IMAGE for i in items):
            out = Layer(f"{lay.name} (baked)", RASTER)
            out.items = [self._rasterize(lay)]
        else:
            out = Layer(f"{lay.name} (baked)", VECTOR,
                        opacity=lay.opacity, items=items)
        return out

    def bake_layer(self, lid):
        lay = self.doc.layer(lid)
        if lay is None or lay.kind != GENERATOR:
            self.statusBar().showMessage("Select a generator layer to bake",
                                         3000)
            return

        def fn():
            out = self._baked(lay)
            out.visible = lay.visible
            self.doc.layers[self.doc.layer_index(lid)] = out
            self.active_layer_id = out.id
        self.commit("Bake generator", fn)

    def convert_to_raster(self, lid):
        lay = self.doc.layer(lid)
        if lay is None or lay.kind == RASTER:
            return

        def fn():
            out = Layer(lay.name, RASTER, visible=lay.visible)
            out.items = [self._rasterize(lay)]
            self.doc.layers[self.doc.layer_index(lid)] = out
            self.active_layer_id = out.id
            self.selection = []
        self.commit("Convert to raster", fn)

    def merge_down(self, lid):
        i = self.doc.layer_index(lid)
        if i <= 0:
            self.statusBar().showMessage("No layer below to merge into",
                                         3000)
            return
        upper, lower = self.doc.layers[i], self.doc.layers[i - 1]
        ukind = upper.kind if upper.kind != GENERATOR else (
            RASTER if any(it.kind == IMAGE
                          for it in generate(upper, self.doc)[0])
            else VECTOR)
        lkind = lower.kind if lower.kind != GENERATOR else VECTOR
        if ukind == RASTER and lkind == VECTOR:
            r = QMessageBox.question(
                self, "Merge down",
                f"“{upper.name}” is a raster layer and “{lower.name}” is "
                "vector.\nConvert the result to a raster layer?")
            if r != QMessageBox.StandardButton.Yes:
                return

        def fn():
            up = self._baked(upper) if upper.kind == GENERATOR else upper
            lo = self._baked(lower) if lower.kind == GENERATOR else lower
            ratio = up.opacity / lo.opacity if lo.opacity > 0 else 1.0
            moved = []
            for it in up.items:
                c = it.clone()
                c.opacity = min(1.0, c.opacity * ratio)
                moved.append(c)
            if up.kind == lo.kind:
                lo.items = lo.items + moved
                result = lo
            elif lo.kind == RASTER:
                lo.items = lo.items + [self._rasterize(up)]
                result = lo
            else:
                result = Layer(lo.name, RASTER, visible=lo.visible)
                result.items = [self._rasterize(lo)] + moved
            self.doc.layers[i - 1] = result
            self.doc.layers.pop(i)
            self.active_layer_id = result.id
            self.selection = []
        self.commit("Merge down", fn)

    # ================================================== generators
    def _gen_targets(self, all_layers):
        if all_layers:
            return [l for l in self.doc.layers if l.kind == GENERATOR]
        lay = self.doc.layer(self.active_layer_id)
        return [lay] if lay and lay.kind == GENERATOR else []

    def update_generator(self, key, value, all_layers=False):
        targets = self._gen_targets(all_layers)
        if not targets:
            return

        def fn():
            for lay in targets:
                lay.generator[key] = value
                if key == "motif_source" and value == "layer" and \
                        not lay.generator.get("motif_layer"):
                    src = next((l for l in reversed(self.doc.layers)
                                if l.kind != GENERATOR and l.items), None)
                    lay.generator["motif_layer"] = src.id if src else None
        scope = "all" if all_layers else self.active_layer_id
        self.commit(f"Pattern: {key.replace('_', ' ')}", fn,
                    merge_key=f"gen:{scope}:{key}")

    def randomize_seed(self):
        all_layers = self.settings_panel.scope.currentData() == "all"
        targets = self._gen_targets(all_layers)

        def fn():
            for lay in targets:
                lay.generator["seed"] = random.randint(1, 999999)
        self.commit("New seed", fn)

    def reset_generator(self):
        targets = self._gen_targets(False)

        def fn():
            for lay in targets:
                seed = lay.generator.get("seed", 1)
                lay.generator = default_generator()
                lay.generator["seed"] = seed
        self.commit("Reset pattern settings", fn)

    def save_preset(self):
        lay = self.doc.layer(self.active_layer_id)
        if not lay or lay.kind != GENERATOR:
            QMessageBox.information(self, "Save preset",
                                    "Select a generator layer first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save pattern preset", str(self._last_dir() /
                                             f"{lay.name}.rwpat"),
            "Repeat-Werx pattern (*.rwpat)")
        if path:
            project_io.save_preset(lay.generator, self.doc.palette, path)
            self._settings.setValue("io/last_dir", str(Path(path).parent))

    def load_preset(self):
        lay = self.doc.layer(self.active_layer_id)
        if not lay or lay.kind != GENERATOR:
            QMessageBox.information(self, "Load preset",
                                    "Select a generator layer first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load pattern preset", str(self._last_dir()),
            "Repeat-Werx pattern (*.rwpat)")
        if not path:
            return
        try:
            g, pal = project_io.load_preset(path)
        except Exception as e:     # noqa: BLE001
            QMessageBox.critical(self, "Load preset", str(e))
            return

        def fn():
            g["motif_layer"] = lay.generator.get("motif_layer")
            if g["motif_source"] == "layer" and not g["motif_layer"]:
                g["motif_source"] = "builtin"
            lay.generator = g
            if pal and g.get("use_document_palette", True):
                self.doc.palette = dict(pal)
        self.commit("Load preset", fn)

    # =================================================== document
    def set_doc_prop(self, key, value):
        self.commit(f"Document {key}",
                    lambda: setattr(self.doc, key, value),
                    merge_key=f"doc:{key}")

    def set_palette(self, key, value):
        def fn():
            pal = dict(self.doc.palette)
            pal[key] = value
            self.doc.palette = pal
        self.commit("Palette", fn, merge_key=f"palette:{key}")

    def dominant_to_background(self):
        pal = self.doc.palette
        tint = colors.rotate(pal["base_color"], 0, 0.38, -0.25)
        self.set_doc_prop("background", tint)

    def set_tile_size(self, size, scale_content=True):
        old = self.doc.tile_size
        if size == old:
            return
        f = size / old

        def fn():
            self.doc.tile_size = int(size)
            if not scale_content:
                return
            for lay in self.doc.layers:
                for it in lay.items:
                    it.cx *= f
                    it.cy *= f
                    it.w *= f
                    it.h *= f
                    it.stroke_width *= f
                    it.corner_radius *= f
                if lay.kind == GENERATOR:
                    g = lay.generator
                    for k in ("base_size", "spacing", "qt_min_cell",
                              "qt_line_width", "motif_stroke_width"):
                        g[k] = g[k] * f
        self.commit("Tile size", fn)
        self.canvas.fit()

    def set_repeat(self, n):
        self.canvas.repeat_n = int(n)
        self._settings.setValue("view/repeat", int(n))
        self.canvas.fit()
        self.settings_panel.refresh_doc()

    def set_dim_neighbors(self, on):
        self.canvas.dim_neighbors = bool(on)
        self._settings.setValue("view/dim", "true" if on else "false")
        self.canvas.update()

    def set_show_border(self, on):
        self.canvas.show_border = bool(on)
        self._settings.setValue("view/border", "true" if on else "false")
        self.canvas.update()

    # ===================================================== files
    def _last_dir(self) -> Path:
        d = self._settings.value("io/last_dir", "")
        return Path(d) if d and Path(d).is_dir() else Path.home()

    def _confirm_discard(self) -> bool:
        if self.undo_stack.isClean():
            return True
        r = QMessageBox.question(
            self, "Unsaved changes", "Save changes to the current design?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save_project()
        return r == QMessageBox.StandardButton.Discard

    def _set_document(self, doc, path=None):
        self.doc = doc
        self.active_layer_id = doc.layers[-1].id
        self.selection = []
        self._file_path = path
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self.changed()
        self.canvas.fit()

    def new_project(self):
        if self._confirm_discard():
            self._set_document(Document())

    def open_project(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open design", str(self._last_dir()),
            "Repeat-Werx design (*.rwpx)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            doc = project_io.load_project(path)
        except Exception as e:     # noqa: BLE001
            QMessageBox.critical(self, "Open design", str(e))
            return
        self._set_document(doc, path)
        self._add_recent(path)

    def save_project(self) -> bool:
        if not self._file_path:
            return self.save_project_as()
        project_io.save_project(self.doc, self._file_path)
        self.undo_stack.setClean()
        self._update_title()
        self.statusBar().showMessage(f"Saved {self._file_path}", 3000)
        return True

    def save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save design", str(self._last_dir() /
                                     f"{self.doc.name}.rwpx"),
            "Repeat-Werx design (*.rwpx)")
        if not path:
            return False
        p = project_io.save_project(self.doc, path)
        self._file_path = str(p)
        self._settings.setValue("io/last_dir", str(p.parent))
        self._add_recent(str(p))
        self.undo_stack.setClean()
        self._update_title()
        return True

    def _recent(self):
        v = self._settings.value("io/recent", [])
        return [v] if isinstance(v, str) else list(v or [])

    def _add_recent(self, path):
        r = [path] + [p for p in self._recent() if p != path]
        self._settings.setValue("io/recent", r[:10])
        self._refresh_recent()

    def _refresh_recent(self):
        self.recent_menu.clear()
        for p in self._recent():
            self.recent_menu.addAction(
                p, lambda _=False, path=p: self._confirm_discard()
                and self.load_path(path))
        self.recent_menu.setEnabled(bool(self._recent()))

    def import_file(self, path=None):
        if not path:
            filt = imageproc.raster_filter().replace(
                "Images (", "Images and SVG (*.svg ")
            path, _ = QFileDialog.getOpenFileName(
                self, "Import image or SVG", str(self._last_dir()),
                f"{filt};;SVG (*.svg);;{imageproc.raster_filter()}")
        if not path:
            return
        self._settings.setValue("io/last_dir", str(Path(path).parent))
        T = self.doc.tile_size
        name = Path(path).stem
        if path.lower().endswith(".svg"):
            try:
                text = Path(path).read_text(encoding="utf-8")
                key, w, h = imageproc.add_svg_asset(self.doc, text, name)
            except Exception as e:     # noqa: BLE001
                QMessageBox.critical(self, "Import SVG", str(e))
                return
            s = T * 0.5 / max(w, h, 1)
            self.add_item(Item(SVG, cx=T / 2, cy=T / 2, w=w * s, h=h * s,
                               fill=None, stroke=None, stroke_width=0,
                               asset=key), "Import SVG")
            return
        act = self.doc.layer(self.active_layer_id)
        try:
            dlg = ImageImportDialogProxy(path, bool(
                act and act.kind == RASTER and not act.locked), self)
        except Exception as e:     # noqa: BLE001
            QMessageBox.critical(self, "Import image", str(e))
            return
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        img = dlg.result_image()
        key = imageproc.add_image_asset(self.doc, img, name)
        s = T * dlg.size_fraction() / max(img.width(), img.height(), 1)
        it = Item(IMAGE, cx=T / 2, cy=T / 2, w=img.width() * s,
                  h=img.height() * s, fill=None, stroke=None,
                  stroke_width=0, asset=key)
        if dlg.target_mode() == "new":
            def fn():
                lay = Layer(name or self.doc.unique_layer_name("Raster"),
                            RASTER, items=[it])
                idx = self.doc.layer_index(self.active_layer_id)
                self.doc.layers.insert(idx + 1, lay)
                self.active_layer_id = lay.id
                self.selection = [it.id]
            self.commit("Import image", fn)
        else:
            self.add_item(it, "Import image")

    def export(self):
        from .gui.export_dialog import ExportDialog
        dlg = ExportDialog(self.doc, self._settings, str(self._last_dir()),
                           self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.exported_path:
            self.statusBar().showMessage(f"Exported {dlg.exported_path}",
                                         5000)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for url in ev.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".rwpx"):
                if self._confirm_discard():
                    self.load_path(p)
                return
            if p:
                self.import_file(p)

    def closeEvent(self, ev):
        if not self._confirm_discard():
            ev.ignore()
            return
        self._settings.setValue("ui/geometry", self.saveGeometry())
        self._settings.setValue("ui/state", self.saveState())
        self._settings.setValue("shape/sides", self.sides_spin.value())
        self._settings.setValue("shape/points", self.points_spin.value())
        self._settings.setValue("shape/inner", self.inner_spin.value())
        super().closeEvent(ev)

    # ====================================================== help
    def user_guide(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Repeat-Werx User Guide")
        dlg.resize(640, 640)
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setHtml(USER_GUIDE)
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()

    def about(self):
        QMessageBox.about(
            self, "About Repeat-Werx",
            f"<h3>Repeat-Werx {__version__}</h3>"
            "<p>Seamless repeating pattern designer using constrained "
            "randomness: wrap-around collision (Poisson disc), tileable "
            "Perlin noise fields, Mondrian quadtrees, color harmonies and "
            "the 60-30-10 rule.</p>"
            f"<p>© {__author__}</p>")


def ImageImportDialogProxy(path, can_use_active, parent):
    from .gui.import_dialog import ImageImportDialog
    return ImageImportDialog(path, can_use_active, parent)


USER_GUIDE = """
<h2>Repeat-Werx</h2>
<p>Design one square <b>tile</b>; the canvas shows it repeated (3 × 3 by
default) so you see the pattern as it will tile. Anything crossing a tile
edge wraps to the opposite edge, so every design is seamless.</p>
<h3>Tools (left)</h3>
<ul>
<li><b>Select (V)</b> — click, Shift-click, or drag a box. Drag to move,
corner/edge handles to scale (Shift keeps proportions), round handle to
rotate (Shift snaps 15°). Arrow keys nudge.</li>
<li><b>Rectangle, Ellipse, Polygon, Star</b> — drag to draw. Shift
constrains, Alt draws from the center. A single click makes a default-size
shape. Sides, points, inner ratio and corner radius are on the top
bar.</li>
<li><b>Line</b> and <b>Pen</b> — pen: click for corners, drag for curves,
click the first point to close, double-click or Enter to finish.</li>
<li><b>Eyedropper</b> — sample a color (Shift for outline).</li>
<li>The two swatches set fill and outline (right-click for none).</li>
</ul>
<h3>Layers</h3>
<p><b>Vector</b> layers hold shapes and SVGs, <b>Raster</b> layers hold
images, and <b>Generator</b> layers create patterns. Drag to reorder;
the checkbox shows/hides; double-click renames. <b>Merge down</b> joins
same-type layers directly; a vector merged into a raster is rasterized,
and raster-into-vector converts the result to raster. <b>Bake</b> turns a
generator into an editable layer.</p>
<h3>Generators (Pattern tab)</h3>
<ul>
<li><b>Poisson disc</b> — random placement with collision detection on a
torus, so spacing holds across the seams.</li>
<li><b>Noise field</b> — tileable Perlin noise drives density, size,
color regions and (with rotation “Follow noise flow”) orientation.</li>
<li><b>Mondrian / quadtree</b> — recursive golden-ratio subdivision into
colored cells, or one motif per cell.</li>
<li><b>Jittered grid</b> — a lattice with jitter and staggered rows.</li>
</ul>
<p>Motifs can be built-in shapes or every item on another layer (hide
that layer to use it only as a source). <b>60-30-10</b>: size tiers and
color roles are balanced by area (shown under the settings).
<b>Boundary weighting</b> pushes motifs toward (+) or away from (−) the
tile seams. “Apply to: All generator layers” edits every generator at
once.</p>
<h3>Import</h3>
<p>SVG imports as vector. Raster images (PNG, JPEG, WebP, TIFF, BMP,
GIF…) open a dialog where the background is auto-detected or picked by
clicking, then made transparent with tolerance and soft edge.</p>
<h3>Files &amp; export</h3>
<p><b>.rwpx</b> designs keep everything editable (images embedded).
<b>.rwpat</b> presets store generator settings and palette. Export a
single tile, an N × M grid, or a fixed image size (scale by tile pixels
or by tiles across, optionally centered) as PNG, JPEG, TIFF, WebP, BMP,
SVG or PDF.</p>
"""


# ================================================================ startup
def _asset(name: str):
    here = Path(__file__).resolve()
    for d in (here.parents[2] / "Images", here.parents[1] / "Images",
              Path(sys.executable).resolve().parent / "Images"):
        if (d / name).exists():
            return d / name
    return None


def _splash_pixmap() -> QPixmap:
    """Splash drawn from a live generator so every launch differs."""
    from .core.export import ExportSpec, compose
    doc = Document(background="#f4f1ea")
    lay = Layer("splash", GENERATOR)
    lay.generator.update({"builtin_shape": "mixed", "base_size": 150,
                          "seed": random.randint(1, 9999)})
    doc.palette["harmony"] = random.choice(list(colors.HARMONIES))
    doc.layers = [lay]
    img = compose(doc, ExportSpec(mode="size", width=640, height=380,
                                  tile_px=320))
    pm = QPixmap.fromImage(img)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    panel = QRect(90, 120, 460, 140)
    p.setBrush(QColor(30, 28, 25, 215))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(panel, 18, 18)
    f = p.font()
    f.setPointSize(30)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(panel.adjusted(0, 18, 0, -50), Qt.AlignmentFlag.AlignCenter,
               "Repeat-Werx")
    f.setPointSize(11)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#d9d4c8"))
    p.drawText(panel.adjusted(0, 80, 0, -10), Qt.AlignmentFlag.AlignCenter,
               f"v{__version__}  ·  {__author__}")
    p.end()
    return pm


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Repeat-Werx")
    app.setDesktopFileName("repeatwerx")
    src = _asset("repeatwerx-icon-1024.png") or _asset("repeatwerx-icon.svg")
    if src is not None:
        app.setWindowIcon(QIcon(str(src)))
    splash = QSplashScreen(_splash_pixmap())
    splash.show()
    app.processEvents()
    win = MainWindow()

    def reveal():
        splash.finish(win)
        win.show()
    QTimer.singleShot(1800, reveal)
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        QTimer.singleShot(0, lambda: win.load_path(sys.argv[1]))
    sys.exit(app.exec())
