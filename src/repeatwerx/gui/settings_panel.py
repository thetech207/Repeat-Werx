"""Right-hand settings: Pattern (generator algorithms), Item, Document."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
                               QFormLayout, QGroupBox, QLabel, QComboBox,
                               QSpinBox, QDoubleSpinBox, QCheckBox,
                               QPushButton, QScrollArea, QLineEdit,
                               QToolButton, QSizePolicy)

from ..core.model import VECTOR, RASTER, GENERATOR, IMAGE, SVG, POLYGON, \
    STAR, RECT, PATH, default_generator
from ..core.generators import ALGORITHMS, BUILTIN_SHAPES
from ..core import color as colors
from .widgets import ColorButton, SliderSpin
from .icons import icon, swatch_icon

ROTATION_MODES = {"none": "None", "random": "Random", "step": "Stepped",
                  "flow": "Follow noise flow"}
RATIO_MODES = {"golden": "Golden ratio", "random": "Random",
               "half": "Halves"}
FILL_MODES = {"cells": "Colored cells", "motifs": "Motif per cell"}


def _scroll(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setWidget(inner)
    return sa


def _combo(options: dict) -> QComboBox:
    c = QComboBox()
    for k, v in options.items():
        c.addItem(v, k)
    return c


def _dspin(lo, hi, step=1.0, dec=1, suffix="") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(dec)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def _spin(lo, hi, suffix="") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def _set_combo(c: QComboBox, data):
    i = c.findData(data)
    if i >= 0:
        c.setCurrentIndex(i)


class _Triple(QWidget):
    """Three spin boxes for 60-30-10 style triples."""

    def __init__(self, maker, labels=("L", "M", "S")):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.spins = []
        for lab in labels:
            s = maker()
            s.setToolTip(lab)
            lay.addWidget(s)
            self.spins.append(s)


class SettingsPanel(QTabWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._loading = False
        self.addTab(_scroll(self._build_pattern_tab()), "Pattern")
        self.addTab(_scroll(self._build_item_tab()), "Item")
        self.addTab(_scroll(self._build_doc_tab()), "Document")

    # ================================================== pattern tab
    def _build_pattern_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 2, 2)
        v.setSpacing(4)
        self._gen_widgets = {}
        self._row_widgets = {}

        # layer props (any layer kind)
        lg = QGroupBox("Layer")
        lf = QFormLayout(lg)
        self.layer_name = QLabel()
        lf.addRow("Active:", self.layer_name)
        self.layer_opacity = SliderSpin(0, 1, 0.01, 2)
        self.layer_opacity.value_changed.connect(
            lambda val: self._layer_prop("opacity", val))
        lf.addRow("Opacity:", self.layer_opacity)
        v.addWidget(lg)

        self.no_gen = QWidget()
        nv = QVBoxLayout(self.no_gen)
        nv.setContentsMargins(4, 4, 4, 4)
        msg = QLabel("Pattern algorithms live on <b>Generator</b> layers. "
                     "Select a generator layer, or add one:")
        msg.setWordWrap(True)
        nv.addWidget(msg)
        b = QPushButton(icon("generator", 18), " New generator layer")
        b.clicked.connect(lambda: self.win.add_layer(GENERATOR))
        nv.addWidget(b)
        v.addWidget(self.no_gen)

        self.gen_box = QWidget()
        gv = QVBoxLayout(self.gen_box)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.setSpacing(4)

        top = QGroupBox("Algorithm")
        tf = QFormLayout(top)
        self.scope = _combo({"layer": "This layer",
                             "all": "All generator layers"})
        self.scope.setToolTip("Apply setting changes to this layer only, "
                              "or to every generator layer at once")
        tf.addRow("Apply to:", self.scope)
        self._add(tf, "algorithm", "Algorithm:", _combo(ALGORITHMS))
        seed_row = QWidget()
        sr = QHBoxLayout(seed_row)
        sr.setContentsMargins(0, 0, 0, 0)
        seed = _spin(0, 999999)
        self._bind("seed", seed)
        dice = QToolButton()
        dice.setIcon(icon("dice", 18))
        dice.setToolTip("New random seed")
        dice.clicked.connect(self.win.randomize_seed)
        sr.addWidget(seed, 1)
        sr.addWidget(dice)
        tf.addRow("Seed:", seed_row)
        gv.addWidget(top)

        # motifs
        self.motif_group = QGroupBox("Motifs")
        mf = QFormLayout(self.motif_group)
        self._add(mf, "motif_source", "Source:",
                  _combo({"builtin": "Built-in shape",
                          "layer": "Items from a layer"}))
        self._add(mf, "builtin_shape", "Shape:", _combo(BUILTIN_SHAPES))
        self.motif_layer = QComboBox()
        self.motif_layer.setToolTip(
            "Every item on this layer becomes a motif. Hide the layer to "
            "use it only as a source.")
        self.motif_layer.currentIndexChanged.connect(
            lambda _i: self._gen_changed(
                "motif_layer", self.motif_layer.currentData()))
        mf.addRow("Layer:", self.motif_layer)
        self._add(mf, "rotation_mode", "Rotation:", _combo(ROTATION_MODES))
        self._add(mf, "rotation_step", "Step:", _dspin(1, 180, 15, 0, "°"))
        self._add(mf, "scale_jitter", "Size jitter:",
                  _dspin(0, 0.9, 0.05, 2))
        gv.addWidget(self.motif_group)

        # 60-30-10 sizing / density
        self.size_group = QGroupBox("Size && density (60-30-10)")
        zf = QFormLayout(self.size_group)
        self._add(zf, "base_size", "Large size:", _dspin(4, 4000, 5, 0))
        scales = _Triple(lambda: _dspin(0.05, 3, 0.05, 2),
                         ("Large", "Medium", "Small"))
        self._bind_triple("tier_scales", scales, pct=False)
        zf.addRow("Tier scale:", scales)
        shares = _Triple(lambda: _spin(0, 100, "%"),
                         ("Large", "Medium", "Small"))
        self._bind_triple("tier_shares", shares, pct=True)
        zf.addRow("Area share:", shares)
        self._add(zf, "coverage", "Coverage:", _dspin(0.02, 1.5, 0.05, 2))
        self._add(zf, "spacing", "Spacing:", _dspin(0, 400, 1, 1))
        self._add(zf, "allow_overlap", "", QCheckBox("Allow overlap"))
        gv.addWidget(self.size_group)

        # noise
        self.noise_group = QGroupBox("Noise field (tileable Perlin)")
        nf = QFormLayout(self.noise_group)
        self._add(nf, "noise_scale", "Period:", _spin(1, 32, " cells"))
        self._add(nf, "noise_octaves", "Octaves:", _spin(1, 6))
        self._add(nf, "noise_threshold", "Threshold:",
                  _dspin(0, 0.95, 0.05, 2))
        drives = QWidget()
        dl = QHBoxLayout(drives)
        dl.setContentsMargins(0, 0, 0, 0)
        self.drive_checks = {}
        for key, lab in (("density", "Density"), ("scale", "Size"),
                         ("color", "Color")):
            cb = QCheckBox(lab)
            cb.toggled.connect(self._drives_changed)
            dl.addWidget(cb)
            self.drive_checks[key] = cb
        nf.addRow("Drives:", drives)
        gv.addWidget(self.noise_group)

        # quadtree
        self.qt_group = QGroupBox("Mondrian / quadtree")
        qf = QFormLayout(self.qt_group)
        self._add(qf, "qt_fill_mode", "Fill:", _combo(FILL_MODES))
        self._add(qf, "qt_max_depth", "Max depth:", _spin(1, 12))
        self._add(qf, "qt_min_cell", "Min cell:", _dspin(4, 1024, 4, 0))
        self._add(qf, "qt_split_chance", "Split chance:",
                  _dspin(0, 1, 0.05, 2))
        self._add(qf, "qt_ratio_mode", "Proportion:", _combo(RATIO_MODES))
        self._add(qf, "qt_line_width", "Line width:", _dspin(0, 60, 1, 1))
        lc = ColorButton("#1c1c1c")
        lc.color_changed.connect(lambda c: self._gen_changed(
            "qt_line_color", c or "#1c1c1c"))
        self._gen_widgets["qt_line_color"] = lc
        qf.addRow("Line color:", lc)
        self._add(qf, "qt_offset", "", QCheckBox("Offset grid from seams"))
        gv.addWidget(self.qt_group)

        # grid
        self.grid_group = QGroupBox("Jittered grid")
        gf = QFormLayout(self.grid_group)
        self._add(gf, "grid_cols", "Columns:", _spin(1, 60))
        self._add(gf, "grid_jitter", "Jitter:", _dspin(0, 1, 0.05, 2))
        self._add(gf, "grid_stagger", "", QCheckBox("Stagger rows"))
        gv.addWidget(self.grid_group)

        # boundary weighting
        bg = QGroupBox("Boundary weighting")
        bf = QFormLayout(bg)
        bw = SliderSpin(-1, 1, 0.05, 2)
        bw.setToolTip("−1 keeps motifs off the tile seams, 0 is neutral, "
                      "+1 favors the seams. Collisions always wrap, so "
                      "seams stay invisible either way.")
        bw.value_changed.connect(
            lambda val: self._gen_changed("boundary_weight", val))
        self._gen_widgets["boundary_weight"] = bw
        bf.addRow("Edge weight:", bw)
        self._add(bf, "boundary_band", "Edge band:",
                  _dspin(0.02, 0.5, 0.01, 2))
        gv.addWidget(bg)

        # color
        cg = QGroupBox("Color (60-30-10)")
        cf = QFormLayout(cg)
        self._add(cf, "color_mode", "Colors:",
                  _combo({"harmony": "Color harmony",
                          "original": "Keep motif colors"}))
        self._add(cf, "use_document_palette", "",
                  QCheckBox("Use document palette"))
        self._add(cf, "harmony", "Harmony:", _combo(colors.HARMONIES))
        bc = ColorButton("#2f6f8f")
        bc.color_changed.connect(
            lambda c: self._gen_changed("base_color", c or "#2f6f8f"))
        self._gen_widgets["base_color"] = bc
        cf.addRow("Base color:", bc)
        self._row_widgets["base_color"] = bc
        cshares = _Triple(lambda: _spin(0, 100, "%"),
                          ("Dominant", "Secondary", "Accent"))
        self._bind_triple("color_shares", cshares, pct=True)
        cf.addRow("Shares:", cshares)
        self._row_widgets["color_shares"] = cshares
        self.gen_swatches = QLabel()
        cf.addRow("Palette:", self.gen_swatches)
        self._add(cf, "stroke_motifs", "", QCheckBox("Outline motifs"))
        sc = ColorButton("#1c1c1c")
        sc.color_changed.connect(
            lambda c: self._gen_changed("motif_stroke", c or "#1c1c1c"))
        self._gen_widgets["motif_stroke"] = sc
        cf.addRow("Outline:", sc)
        self._add(cf, "motif_stroke_width", "Outline width:",
                  _dspin(0, 40, 0.5, 1))
        gv.addWidget(cg)

        self.stats = QLabel()
        self.stats.setWordWrap(True)
        gv.addWidget(self.stats)

        btns = QHBoxLayout()
        bake = QPushButton(icon("bake", 18), " Bake")
        bake.setToolTip("Convert the generated result into an editable "
                        "vector (or raster) layer")
        bake.clicked.connect(
            lambda: self.win.bake_layer(self.win.active_layer_id))
        save = QPushButton("Save preset…")
        save.clicked.connect(self.win.save_preset)
        load = QPushButton("Load preset…")
        load.clicked.connect(self.win.load_preset)
        btns.addWidget(bake)
        btns.addWidget(save)
        btns.addWidget(load)
        gv.addLayout(btns)
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self.win.reset_generator)
        gv.addWidget(reset)

        v.addWidget(self.gen_box)
        v.addStretch(1)
        return w

    def _add(self, form, key, label, widget):
        self._bind(key, widget)
        form.addRow(label, widget)
        self._row_widgets[key] = widget

    def _bind(self, key, widget):
        self._gen_widgets[key] = widget
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(
                lambda _i, k=key, w=widget: self._gen_changed(
                    k, w.currentData()))
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(
                lambda val, k=key: self._gen_changed(k, bool(val)))
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.valueChanged.connect(
                lambda val, k=key: self._gen_changed(k, val))

    def _bind_triple(self, key, triple, pct):
        self._gen_widgets[key] = triple
        for s in triple.spins:
            s.valueChanged.connect(
                lambda _v, k=key, t=triple, p=pct: self._gen_changed(
                    k, [(x.value() / 100 if p else x.value())
                        for x in t.spins]))
        triple._pct = pct

    def _gen_changed(self, key, value):
        if self._loading:
            return
        self.win.update_generator(key, value,
                                  self.scope.currentData() == "all")

    def _drives_changed(self, *_):
        if self._loading:
            return
        val = [k for k, cb in self.drive_checks.items() if cb.isChecked()]
        self._gen_changed("noise_drives", val)

    def _layer_prop(self, key, value):
        if self._loading:
            return
        lid = self.win.active_layer_id
        self.win.set_layer_prop(lid, key, value, "Layer opacity",
                                merge=True)

    def refresh_pattern(self):
        doc = self.win.doc
        lay = doc.layer(self.win.active_layer_id)
        self._loading = True
        try:
            if lay is None:
                self.layer_name.setText("—")
                self.no_gen.show()
                self.gen_box.hide()
                return
            kind = {VECTOR: "vector", RASTER: "raster",
                    GENERATOR: "generator"}[lay.kind]
            self.layer_name.setText(f"{lay.name}  <i>({kind})</i>")
            self.layer_opacity.setValue(lay.opacity)
            is_gen = lay.kind == GENERATOR
            self.no_gen.setVisible(not is_gen)
            self.gen_box.setVisible(is_gen)
            if not is_gen:
                return
            g = default_generator()
            g.update(lay.generator or {})
            for key, w in self._gen_widgets.items():
                val = g.get(key)
                if isinstance(w, QComboBox):
                    _set_combo(w, val)
                elif isinstance(w, QCheckBox):
                    w.setChecked(bool(val))
                elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.setValue(val)
                elif isinstance(w, _Triple):
                    for s, x in zip(w.spins, val):
                        s.setValue(int(round(x * 100)) if w._pct else x)
                elif isinstance(w, ColorButton):
                    w.set_color(val)
                elif isinstance(w, SliderSpin):
                    w.setValue(float(val))
            for k, cb in self.drive_checks.items():
                cb.setChecked(k in g["noise_drives"])
            self.motif_layer.clear()
            for other in reversed(doc.layers):
                if other.id != lay.id and other.kind != GENERATOR:
                    self.motif_layer.addItem(
                        icon(other.kind, 16),
                        f"{other.name} ({len(other.items)} items)",
                        other.id)
            _set_combo(self.motif_layer, g["motif_layer"])
            if g["motif_source"] == "layer" and self.motif_layer.count() \
                    and self.motif_layer.findData(g["motif_layer"]) < 0:
                self.motif_layer.setCurrentIndex(-1)
            self._update_visibility(g)
            self._update_stats(lay, g)
        finally:
            self._loading = False

    def _update_visibility(self, g):
        algo = g["algorithm"]
        qt_cells = algo == "quadtree" and g["qt_fill_mode"] == "cells"
        self.motif_group.setVisible(not qt_cells)
        self.size_group.setVisible(algo in ("poisson", "noise", "grid"))
        self.noise_group.setVisible(algo == "noise"
                                    or g["rotation_mode"] == "flow")
        self.qt_group.setVisible(algo == "quadtree")
        self.grid_group.setVisible(algo == "grid")
        layer_src = g["motif_source"] == "layer"
        rw = self._row_widgets
        for key, show in (("builtin_shape", not layer_src),
                          ("rotation_step", g["rotation_mode"] == "step"),
                          ("base_size", algo != "grid"),
                          ("spacing", algo in ("poisson", "noise")),
                          ("allow_overlap", algo in ("poisson", "noise")),
                          ("noise_threshold", algo == "noise"),
                          ("motif_stroke_width", g["stroke_motifs"]),
                          ("motif_stroke", g["stroke_motifs"])):
            self._show_row(rw.get(key) or self._gen_widgets.get(key), show)
        self._show_row(self.motif_layer, layer_src)
        own = not g["use_document_palette"]
        for key in ("harmony", "base_color", "color_shares"):
            self._show_row(rw.get(key) or self._gen_widgets.get(key), own)

    @staticmethod
    def _show_row(widget, show):
        if widget is None:
            return
        form = widget.parentWidget().layout() if widget.parentWidget() \
            else None
        if isinstance(form, QFormLayout):
            form.setRowVisible(widget, show)
        else:
            widget.setVisible(show)

    def _update_stats(self, lay, g):
        from ..core.generators import generate_cached, palette_for
        items, st = generate_cached(lay, self.win.doc)
        cols, _sh = palette_for(g, self.win.doc)
        self.gen_swatches.setText(_swatch_html(cols))
        ts = " / ".join(f"{x * 100:.0f}" for x in st["tier_shares"])
        cs = " / ".join(f"{x * 100:.0f}" for x in st["color_shares"])
        self.stats.setText(
            f"<b>{st['count']}</b> elements placed<br>"
            f"Size tiers by area: {ts} %<br>"
            f"Color roles by area: {cs} %")

    # ===================================================== item tab
    def _build_item_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 2, 2)
        self.item_hint = QLabel("Nothing selected. Use the Select tool, "
                                "or draw a shape.")
        self.item_hint.setWordWrap(True)
        v.addWidget(self.item_hint)
        self.item_box = QWidget()
        iv = QVBoxLayout(self.item_box)
        iv.setContentsMargins(0, 0, 0, 0)

        sg = QGroupBox("Style")
        sf = QFormLayout(sg)
        self.i_fill = ColorButton("#4a7ab5", allow_none=True)
        self.i_fill.color_changed.connect(
            lambda c: self._item_changed("fill", c))
        sf.addRow("Fill:", self.i_fill)
        self.i_stroke = ColorButton("#1c1c1c", allow_none=True, stroke=True)
        self.i_stroke.color_changed.connect(
            lambda c: self._item_changed("stroke", c))
        sf.addRow("Outline:", self.i_stroke)
        self.i_sw = _dspin(0, 200, 0.5, 1)
        self.i_sw.valueChanged.connect(
            lambda val: self._item_changed("stroke_width", val))
        sf.addRow("Outline width:", self.i_sw)
        self.i_op = SliderSpin(0, 1, 0.01, 2)
        self.i_op.value_changed.connect(
            lambda val: self._item_changed("opacity", val))
        sf.addRow("Opacity:", self.i_op)
        iv.addWidget(sg)

        self.geo_group = QGroupBox("Geometry")
        gf = QFormLayout(self.geo_group)
        self.i_geo = {}
        for key, lab, lo, hi, dec, suf in (
                ("cx", "X:", -99999, 99999, 1, ""),
                ("cy", "Y:", -99999, 99999, 1, ""),
                ("w", "Width:", 1, 99999, 1, ""),
                ("h", "Height:", 1, 99999, 1, ""),
                ("rotation", "Rotation:", -360, 360, 1, "°")):
            s = _dspin(lo, hi, 1, dec, suf)
            s.valueChanged.connect(
                lambda val, k=key: self._item_changed(k, val))
            gf.addRow(lab, s)
            self.i_geo[key] = s
        self.i_sides = _spin(3, 64)
        self.i_sides.valueChanged.connect(
            lambda val: self._item_changed("sides", val))
        gf.addRow("Sides/points:", self.i_sides)
        self.i_inner = _dspin(0.05, 0.95, 0.05, 2)
        self.i_inner.valueChanged.connect(
            lambda val: self._item_changed("inner_ratio", val))
        gf.addRow("Inner ratio:", self.i_inner)
        self.i_radius = _dspin(0, 2000, 1, 1)
        self.i_radius.valueChanged.connect(
            lambda val: self._item_changed("corner_radius", val))
        gf.addRow("Corner radius:", self.i_radius)
        iv.addWidget(self.geo_group)

        row = QHBoxLayout()
        for ic, tip, fn in (
                ("flipx", "Flip horizontal",
                 lambda: self.win.flip_selection("x")),
                ("flipy", "Flip vertical",
                 lambda: self.win.flip_selection("y")),
                ("up", "Bring forward", lambda: self.win.arrange(1)),
                ("down", "Send backward", lambda: self.win.arrange(-1)),
                ("duplicate", "Duplicate", lambda: self.win.duplicate()),
                ("delete", "Delete", lambda: self.win.delete_selection())):
            b = QToolButton()
            b.setIcon(icon(ic, 18))
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        iv.addLayout(row)
        pal = QPushButton("Apply 60-30-10 palette to selection")
        pal.setToolTip("Recolor the selected shapes with the document "
                       "palette so color areas split 60/30/10")
        pal.clicked.connect(self.win.apply_palette_to_selection)
        iv.addWidget(pal)
        v.addWidget(self.item_box)
        v.addStretch(1)
        return w

    def _item_changed(self, key, value):
        if self._loading:
            return
        self.win.update_items(key, value)

    def refresh_item(self):
        sel = self.win.selected_items()
        self._loading = True
        try:
            self.item_hint.setVisible(not sel)
            self.item_box.setVisible(bool(sel))
            if not sel:
                return
            it = sel[0]
            if len(sel) > 1:
                self.item_hint.setVisible(True)
                self.item_hint.setText(f"{len(sel)} items selected — "
                                       "edits apply to all.")
            else:
                self.item_hint.setText("Nothing selected. Use the Select "
                                       "tool, or draw a shape.")
            shape = it.kind not in (IMAGE, SVG)
            self.i_fill.setEnabled(shape)
            self.i_stroke.setEnabled(shape)
            self.i_sw.setEnabled(shape)
            self.i_fill.set_color(it.fill)
            self.i_stroke.set_color(it.stroke)
            self.i_sw.setValue(it.stroke_width)
            self.i_op.setValue(it.opacity)
            for k, s in self.i_geo.items():
                s.setValue(getattr(it, k))
            self.i_sides.setValue(it.sides)
            self.i_inner.setValue(it.inner_ratio)
            self.i_radius.setValue(it.corner_radius)
            form = self.geo_group.layout()
            form.setRowVisible(self.i_sides, it.kind in (POLYGON, STAR))
            form.setRowVisible(self.i_inner, it.kind == STAR)
            form.setRowVisible(self.i_radius, it.kind == RECT)
        finally:
            self._loading = False

    # ================================================= document tab
    def _build_doc_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 2, 2)
        tg = QGroupBox("Tile")
        tf = QFormLayout(tg)
        self.d_name = QLineEdit()
        self.d_name.editingFinished.connect(
            lambda: self._doc_changed("name", self.d_name.text().strip()
                                      or "Untitled"))
        tf.addRow("Name:", self.d_name)
        tile_row = QWidget()
        tr = QHBoxLayout(tile_row)
        tr.setContentsMargins(0, 0, 0, 0)
        self.d_tile = _spin(64, 8192, " units")
        self.d_tile.setSingleStep(64)
        self.d_scale = QCheckBox("Scale content")
        self.d_scale.setChecked(True)
        apply_tile = QPushButton("Apply")
        apply_tile.clicked.connect(lambda: self.win.set_tile_size(
            self.d_tile.value(), self.d_scale.isChecked()))
        tr.addWidget(self.d_tile, 1)
        tr.addWidget(apply_tile)
        tf.addRow("Tile size:", tile_row)
        tf.addRow("", self.d_scale)
        self.d_bg = ColorButton("#f4f1ea", allow_none=True)
        self.d_bg.color_changed.connect(
            lambda c: self._doc_changed("background", c))
        tf.addRow("Background:", self.d_bg)
        self.d_bg_none = QCheckBox("Transparent background")
        self.d_bg_none.toggled.connect(
            lambda on: self._doc_changed(
                "background", None if on else (self.d_bg.color()
                                               or "#f4f1ea")))
        tf.addRow("", self.d_bg_none)
        v.addWidget(tg)

        pg = QGroupBox("Palette (color theory)")
        pf = QFormLayout(pg)
        self.p_harmony = _combo(colors.HARMONIES)
        self.p_harmony.currentIndexChanged.connect(
            lambda _i: self._palette_changed(
                "harmony", self.p_harmony.currentData()))
        pf.addRow("Harmony:", self.p_harmony)
        self.p_base = ColorButton("#2f6f8f")
        self.p_base.color_changed.connect(
            lambda c: self._palette_changed("base_color", c or "#2f6f8f"))
        pf.addRow("Base color:", self.p_base)
        self.p_shares = _Triple(lambda: _spin(0, 100, "%"),
                                ("Dominant", "Secondary", "Accent"))
        for s in self.p_shares.spins:
            s.valueChanged.connect(lambda _v: self._palette_changed(
                "shares", [x.value() / 100 for x in self.p_shares.spins]))
        pf.addRow("60-30-10:", self.p_shares)
        self.p_swatches = QWidget()
        self.p_sw_lay = QHBoxLayout(self.p_swatches)
        self.p_sw_lay.setContentsMargins(0, 0, 0, 0)
        self.p_sw_lay.setSpacing(3)
        pf.addRow("Colors:", self.p_swatches)
        hint = QLabel("Click a swatch to use it as the fill color "
                      "(Shift-click: outline).")
        hint.setWordWrap(True)
        pf.addRow(hint)
        bgbtn = QPushButton("Use dominant color as background")
        bgbtn.clicked.connect(self.win.dominant_to_background)
        pf.addRow(bgbtn)
        v.addWidget(pg)

        vg = QGroupBox("View")
        vf = QFormLayout(vg)
        self.v_repeat = _combo({1: "1 × 1 (tile only)", 3: "3 × 3",
                                5: "5 × 5"})
        self.v_repeat.currentIndexChanged.connect(
            lambda _i: self.win.set_repeat(self.v_repeat.currentData()))
        vf.addRow("Repeat view:", self.v_repeat)
        self.v_dim = QCheckBox("Dim neighbor tiles")
        self.v_dim.toggled.connect(self.win.set_dim_neighbors)
        vf.addRow("", self.v_dim)
        self.v_border = QCheckBox("Show tile border")
        self.v_border.toggled.connect(self.win.set_show_border)
        vf.addRow("", self.v_border)
        v.addWidget(vg)
        v.addStretch(1)
        return w

    def _doc_changed(self, key, value):
        if self._loading:
            return
        self.win.set_doc_prop(key, value)

    def _palette_changed(self, key, value):
        if self._loading:
            return
        self.win.set_palette(key, value)

    def refresh_doc(self):
        doc = self.win.doc
        cv = self.win.canvas
        self._loading = True
        try:
            self.d_name.setText(doc.name)
            self.d_tile.setValue(doc.tile_size)
            self.d_bg.set_color(doc.background or self.d_bg.color())
            self.d_bg_none.setChecked(doc.background is None)
            _set_combo(self.p_harmony, doc.palette["harmony"])
            self.p_base.set_color(doc.palette["base_color"])
            for s, x in zip(self.p_shares.spins, doc.palette["shares"]):
                s.setValue(int(round(x * 100)))
            _set_combo(self.v_repeat, cv.repeat_n)
            self.v_dim.setChecked(cv.dim_neighbors)
            self.v_border.setChecked(cv.show_border)
            while self.p_sw_lay.count():
                it = self.p_sw_lay.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            cols = colors.harmony(doc.palette["base_color"],
                                  doc.palette["harmony"])
            shares = colors.role_shares(cols, doc.palette["shares"])
            for c, sh in zip(cols, shares):
                b = _SwatchButton(c, self.win)
                b.setToolTip(f"{c} — {sh * 100:.0f}%")
                self.p_sw_lay.addWidget(b)
            self.p_sw_lay.addStretch(1)
        finally:
            self._loading = False

    def refresh(self):
        self.refresh_pattern()
        self.refresh_item()
        self.refresh_doc()


class _SwatchButton(QToolButton):
    def __init__(self, color, win):
        super().__init__()
        self.color = color
        self.win = win
        self.setIcon(swatch_icon(color, 24))
        self.setIconSize(self.iconSize().expandedTo(
            self.iconSize().__class__(22, 22)))

    def mousePressEvent(self, ev):
        stroke = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.win.set_current_color(self.color, stroke)


def _swatch_html(cols) -> str:
    cells = "".join(
        f'<td style="background:{c}; width:22px; height:14px;"></td>'
        for c in cols)
    return f'<table cellspacing="2"><tr>{cells}</tr></table>'
