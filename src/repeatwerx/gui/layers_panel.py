"""Layer stack: add, delete, reorder (buttons or drag), rename, show/hide,
lock, merge down, convert to raster, bake generators."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QToolButton,
                               QMenu, QAbstractItemView)

from ..core.model import VECTOR, RASTER, GENERATOR
from .icons import icon

KIND_LABEL = {VECTOR: "Vector", RASTER: "Raster", GENERATOR: "Generator"}


class LayersPanel(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        title = QLabel("<b>Layers</b>")
        lay.addWidget(title)
        self.list = QListWidget()
        self.list.setIconSize(QSize(20, 20))
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.currentItemChanged.connect(self._on_current)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.model().rowsMoved.connect(
            lambda *_: QTimer.singleShot(0, self._on_rows_moved))
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        row.setSpacing(3)

        def btn(ic, tip, fn=None, menu=None):
            b = QToolButton()
            b.setIcon(icon(ic, 20))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            if fn:
                b.clicked.connect(fn)
            if menu:
                b.setMenu(menu)
                b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            row.addWidget(b)
            return b

        add_menu = QMenu(self)
        add_menu.addAction(icon("vector"), "Vector layer",
                           lambda: win.add_layer(VECTOR))
        add_menu.addAction(icon("raster"), "Raster layer",
                           lambda: win.add_layer(RASTER))
        add_menu.addAction(icon("generator"), "Generator layer",
                           lambda: win.add_layer(GENERATOR))
        self.add_btn = btn("add", "Add layer", menu=add_menu)
        btn("duplicate", "Duplicate layer",
            lambda: win.duplicate_layer(win.active_layer_id))
        btn("up", "Move layer up",
            lambda: win.move_layer(win.active_layer_id, 1))
        btn("down", "Move layer down",
            lambda: win.move_layer(win.active_layer_id, -1))
        btn("merge", "Merge down (into the layer below)",
            lambda: win.merge_down(win.active_layer_id))
        self.lock_btn = btn("lock", "Lock / unlock layer",
                            lambda: win.toggle_layer_lock(
                                win.active_layer_id))
        more = QMenu(self)
        more.addAction(icon("raster"), "Convert to raster",
                       lambda: win.convert_to_raster(win.active_layer_id))
        more.addAction(icon("bake"), "Bake generator to layer",
                       lambda: win.bake_layer(win.active_layer_id))
        btn("bake", "More layer actions", menu=more)
        row.addStretch(1)
        btn("delete", "Delete layer",
            lambda: win.delete_layer(win.active_layer_id))
        lay.addLayout(row)
        self._building = False

    # top of the list = top of the stack
    def refresh(self):
        self._building = True
        doc = self.win.doc
        self.list.clear()
        current = None
        for lay in reversed(doc.layers):
            text = lay.name + ("  (locked)" if lay.locked else "")
            it = QListWidgetItem(icon(lay.kind, 20), text)
            it.setData(Qt.ItemDataRole.UserRole, lay.id)
            it.setFlags(Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsEditable
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsDragEnabled)
            it.setCheckState(Qt.CheckState.Checked if lay.visible
                             else Qt.CheckState.Unchecked)
            tip = f"{KIND_LABEL[lay.kind]} layer"
            if lay.locked:
                tip += " (locked)"
                f = it.font()
                f.setItalic(True)
                it.setFont(f)
            it.setToolTip(tip + " — double-click to rename, "
                          "checkbox toggles visibility, drag to reorder")
            self.list.addItem(it)
            if lay.id == self.win.active_layer_id:
                current = it
        if current is not None:
            self.list.setCurrentItem(current)
        act = doc.layer(self.win.active_layer_id)
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(bool(act and act.locked))
        self._building = False

    def _lid(self, item):
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_current(self, cur, _prev):
        if self._building or cur is None:
            return
        self.win.set_active_layer(self._lid(cur))

    def _on_item_changed(self, item):
        if self._building:
            return
        lay = self.win.doc.layer(self._lid(item))
        if lay is None:
            return
        vis = item.checkState() == Qt.CheckState.Checked
        name = item.text().replace("  (locked)", "").strip() or lay.name
        if vis != lay.visible:
            self.win.set_layer_prop(lay.id, "visible", vis,
                                    "Show layer" if vis else "Hide layer")
        elif name != lay.name:
            self.win.set_layer_prop(lay.id, "name", name, "Rename layer")

    def _on_rows_moved(self):
        if self._building:
            return
        ids = [self._lid(self.list.item(i))
               for i in range(self.list.count())]
        self.win.reorder_layers(list(reversed(ids)))

    def _context_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        lid = self._lid(item)
        w = self.win
        m = QMenu(self)
        m.addAction("Rename", lambda: self.list.editItem(item))
        m.addAction("Duplicate", lambda: w.duplicate_layer(lid))
        m.addAction("Lock / unlock", lambda: w.toggle_layer_lock(lid))
        m.addSeparator()
        m.addAction("Merge down", lambda: w.merge_down(lid))
        m.addAction("Convert to raster", lambda: w.convert_to_raster(lid))
        lay = w.doc.layer(lid)
        if lay and lay.kind == GENERATOR:
            m.addAction("Bake generator", lambda: w.bake_layer(lid))
        m.addSeparator()
        m.addAction("Delete", lambda: w.delete_layer(lid))
        m.exec(self.list.mapToGlobal(pos))
