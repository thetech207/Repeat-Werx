"""Constrained-randomness generators.

Each generator fills the tile with motif copies. All spatial tests are
toroidal (distances wrap at the tile size), so placements near one edge
respect placements near the opposite edge and the result tiles
seamlessly. Sizes follow 60-30-10 tiers by area and colors follow a
harmony split 60-30-10 by area.
"""

from __future__ import annotations

import json
import math
import random
from collections import OrderedDict

from PySide6.QtGui import QTransform

from .model import (Item, Layer, Document, RECT, ELLIPSE, POLYGON, STAR,
                    PATH, IMAGE, SVG, SHAPE_KINDS, default_generator)
from .noise import TileableField
from . import color as colors

ALGORITHMS = OrderedDict([
    ("poisson", "Poisson disc (collision)"),
    ("noise", "Noise field (Perlin)"),
    ("quadtree", "Mondrian / quadtree"),
    ("grid", "Jittered grid"),
])

BUILTIN_SHAPES = OrderedDict([
    ("circle", "Circle"), ("square", "Square"), ("triangle", "Triangle"),
    ("diamond", "Diamond"), ("hexagon", "Hexagon"), ("star", "Star"),
    ("leaf", "Leaf"), ("mixed", "Mixed"),
])

LEAF = [["M", 0, -0.5], ["C", 0.5, -0.2, 0.5, 0.2, 0, 0.5],
        ["C", -0.5, 0.2, -0.5, -0.2, 0, -0.5], ["Z"]]


def _mk(kind, **kw) -> Item:
    return Item(kind, w=1.0, h=1.0, fill="#888888", stroke=None,
                stroke_width=0, **kw)


def builtin_templates(name: str) -> list[Item]:
    table = {
        "circle": [_mk(ELLIPSE)],
        "square": [_mk(RECT)],
        "triangle": [_mk(POLYGON, sides=3)],
        "diamond": [_mk(POLYGON, sides=4)],
        "hexagon": [_mk(POLYGON, sides=6)],
        "star": [_mk(STAR, sides=5, inner_ratio=0.45)],
        "leaf": [_mk(PATH, segments=LEAF)],
    }
    if name == "mixed":
        return [t for k in ("circle", "triangle", "square", "star", "leaf")
                for t in table[k]]
    return table.get(name, table["circle"])


def layer_templates(layer: Layer | None) -> list[Item]:
    """Motifs taken from a layer's items, normalised to a unit box."""
    out = []
    for it in (layer.items if layer else []):
        t = it.clone()
        s = max(abs(t.w), abs(t.h), 1e-6)
        t.w, t.h = t.w / s, t.h / s
        t.cx = t.cy = 0.0
        out.append(t)
    return out


def area_factor(t: Item) -> float:
    """Fraction of a size x size box the motif covers (approx.)."""
    if t.kind in (IMAGE, SVG):
        return 0.6 * t.w * t.h
    from .render import unit_path
    poly = unit_path(t).toFillPolygon(QTransform.fromScale(t.w, t.h))
    a = 0.0
    n = poly.size()
    for i in range(n):
        p, q = poly.at(i), poly.at((i + 1) % n)
        a += p.x() * q.y() - q.x() * p.y()
    return max(abs(a) / 2, 0.02)


def boundary_factor(x: float, y: float, T: float, weight: float,
                    band: float) -> float:
    """Acceptance probability from distance to the tile edge.

    weight > 0 favors the seams, < 0 keeps motifs away from them, 0 is
    neutral. `band` is the edge zone as a fraction of the tile.
    """
    if not weight:
        return 1.0
    x %= T
    y %= T
    d = min(x, T - x, y, T - y) / T
    e = max(0.0, 1.0 - d / max(band, 1e-3))
    return max(0.0, min(1.0, (1 + weight * e) / (1 + max(weight, 0.0))))


class _TorusHash:
    """Spatial hash for circle collision on a torus."""

    def __init__(self, T: float, cell: float):
        self.T = T
        self.n = max(1, int(T // max(cell, 1.0)))
        self.cs = T / self.n
        self.cells: dict = {}

    def _key(self, x, y):
        return (int(x // self.cs) % self.n, int(y // self.cs) % self.n)

    def add(self, x, y, r):
        self.cells.setdefault(self._key(x, y), []).append((x, y, r))

    def collides(self, x, y, r, pad, maxr) -> bool:
        T = self.T
        reach = r + maxr + pad
        k = min(int(math.ceil(reach / self.cs)), self.n // 2 + 1)
        ci, cj = self._key(x, y)
        seen = set()
        for di in range(-k, k + 1):
            for dj in range(-k, k + 1):
                key = ((ci + di) % self.n, (cj + dj) % self.n)
                if key in seen:
                    continue
                seen.add(key)
                for qx, qy, qr in self.cells.get(key, ()):
                    dx = abs(x - qx)
                    dx = min(dx, T - dx)
                    dy = abs(y - qy)
                    dy = min(dy, T - dy)
                    lim = r + qr + pad
                    if dx * dx + dy * dy < lim * lim:
                        return True
        return False


def torus_distance(a, b, T) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return math.hypot(min(dx, T - dx), min(dy, T - dy))


# ------------------------------------------------------------ helpers
def _norm(v):
    s = sum(v) or 1.0
    return [x / s for x in v]


def _rotation(g, rng, field, x, y, T) -> float:
    mode = g["rotation_mode"]
    if mode == "random":
        return rng.random() * 360
    if mode == "step":
        step = max(1.0, float(g["rotation_step"]))
        return rng.randrange(max(1, int(round(360 / step)))) * step
    if mode == "flow" and field is not None:
        return field.angle(x / T, y / T)
    return 0.0


def palette_for(g: dict, doc: Document):
    if g.get("use_document_palette", True):
        pal = doc.palette
        base, scheme = pal["base_color"], pal["harmony"]
        shares = pal.get("shares", [0.6, 0.3, 0.1])
    else:
        base, scheme, shares = g["base_color"], g["harmony"], \
            g["color_shares"]
    cols = colors.harmony(base, scheme)
    return cols, colors.role_shares(cols, shares)


# --------------------------------------------------------- algorithms
def _scatter(g, T, rng, field, templates, rfac, afac):
    shares = _norm(g["tier_shares"])
    scales = list(g["tier_scales"])
    base = max(4.0, float(g["base_size"]))
    jitter = max(0.0, min(0.9, float(g["scale_jitter"])))
    cov = max(0.01, min(1.5, float(g["coverage"])))
    mean_af = sum(afac) / len(afac)
    counts = [int(round(sh * cov * T * T / (mean_af * (base * sc) ** 2)))
              for sh, sc in zip(shares, scales)]
    total = sum(counts)
    if total > 4000:
        counts = [int(c * 4000 / total) for c in counts]
    maxr = base * max(scales) * 0.5 * (1 + jitter) * max(rfac)
    pad = max(0.0, float(g["spacing"]))
    grid = _TorusHash(T, 2 * maxr + pad)
    use_density = (g["algorithm"] == "noise"
                   and "density" in g["noise_drives"])
    use_scale = (g["algorithm"] == "noise" and "scale" in g["noise_drives"])
    thr = float(g["noise_threshold"])
    bw, band = float(g["boundary_weight"]), float(g["boundary_band"])
    out = []
    for tier, (count, sc) in enumerate(zip(counts, scales)):
        for _ in range(count):
            for _attempt in range(30):
                x, y = rng.random() * T, rng.random() * T
                if rng.random() > boundary_factor(x, y, T, bw, band):
                    continue
                nv = field(x / T, y / T) if field is not None else 0.5
                if use_density:
                    if nv < thr:
                        continue
                    if rng.random() > ((nv - thr) / max(1 - thr, 1e-6)) ** .5:
                        continue
                s = base * sc * (1 + rng.uniform(-jitter, jitter))
                if use_scale:
                    s *= 0.6 + 0.8 * nv
                m = rng.randrange(len(templates))
                r = s * 0.5 * rfac[m]
                if not g["allow_overlap"] and grid.collides(x, y, r, pad,
                                                            maxr):
                    continue
                grid.add(x, y, r)
                out.append({"x": x, "y": y, "size": s, "tier": tier,
                            "motif": m, "noise": nv,
                            "rot": _rotation(g, rng, field, x, y, T)})
                break
    return out


def _grid(g, T, rng, field, templates):
    cols = max(1, int(g["grid_cols"]))
    stagger = bool(g["grid_stagger"])
    rows = cols if (not stagger or cols % 2 == 0) else cols + 1
    cw, ch = T / cols, T / rows
    shares = _norm(g["tier_shares"])
    scales = list(g["tier_scales"])
    probs = _norm([sh / (sc * sc) for sh, sc in zip(shares, scales)])
    # motif size follows the cell so the lattice stays readable
    base = min(cw, ch) * 0.8 * max(0.1, float(g["coverage"]) / 0.45) ** .5
    # deal tiers from a shuffled deck so counts match the shares exactly
    n = rows * cols
    counts = [int(round(pr * n)) for pr in probs]
    counts[0] += n - sum(counts)
    deck = [t for t, c in enumerate(counts) for _ in range(max(c, 0))]
    deck = (deck + [0] * n)[:n]
    rng.shuffle(deck)
    jit = float(g["grid_jitter"])
    sj = float(g["scale_jitter"])
    bw, band = float(g["boundary_weight"]), float(g["boundary_band"])
    out = []
    for r in range(rows):
        for c in range(cols):
            x = (c + 0.5 + (0.5 if stagger and r % 2 else 0)) * cw
            y = (r + 0.5) * ch
            x += rng.uniform(-0.5, 0.5) * jit * cw
            y += rng.uniform(-0.5, 0.5) * jit * ch
            if rng.random() > boundary_factor(x, y, T, bw, band):
                continue
            tier = deck[r * cols + c]
            s = base * scales[tier] * (1 + rng.uniform(-sj, sj))
            nv = field(x / T, y / T) if field is not None else 0.5
            out.append({"x": x % T, "y": y % T, "size": s, "tier": tier,
                        "motif": rng.randrange(len(templates)), "noise": nv,
                        "rot": _rotation(g, rng, field, x, y, T)})
    return out


def quadtree_cells(g, T, rng):
    """Mondrian-style subdivision; returns [(x, y, w, h, depth)]."""
    max_depth = max(0, int(g["qt_max_depth"]))
    min_cell = max(4.0, float(g["qt_min_cell"]))
    chance = float(g["qt_split_chance"])
    mode = g["qt_ratio_mode"]
    bw, band = float(g["boundary_weight"]), float(g["boundary_band"])
    ox = rng.random() * T if g.get("qt_offset") else 0.0
    oy = rng.random() * T if g.get("qt_offset") else 0.0
    leaves = []

    def ratio():
        if mode == "golden":
            return rng.choice((0.381966, 0.618034))
        if mode == "half":
            return 0.5
        return rng.uniform(0.25, 0.75)

    def split(x, y, w, h, d):
        p = 1.0 if d < 2 else chance * (0.92 ** (d - 2))
        p *= boundary_factor(x + w / 2 + ox, y + h / 2 + oy, T, bw, band)
        if d >= max_depth or rng.random() > p:
            leaves.append((x + ox, y + oy, w, h, d))
            return
        vertical = w > h * 1.15 or (h <= w * 1.15 and rng.random() < .5)
        for vert in (vertical, not vertical):
            t = ratio()
            if vert and w * min(t, 1 - t) >= min_cell:
                split(x, y, w * t, h, d + 1)
                split(x + w * t, y, w * (1 - t), h, d + 1)
                return
            if not vert and h * min(t, 1 - t) >= min_cell:
                split(x, y, w, h * t, d + 1)
                split(x, y + h * t, w, h * (1 - t), d + 1)
                return
        leaves.append((x + ox, y + oy, w, h, d))

    split(0.0, 0.0, float(T), float(T), 0)
    return leaves


# ----------------------------------------------------------- assembly
def _make_items(g, doc, T, rng, field, places, templates, afac):
    cols, shares = palette_for(g, doc)
    areas = [p["size"] ** 2 * afac[p["motif"]] for p in places]
    if field is not None and "color" in g["noise_drives"] \
            and g["algorithm"] == "noise":
        order = sorted(range(len(places)), key=lambda i: places[i]["noise"])
    else:
        order = list(range(len(places)))
        rng.shuffle(order)
    roles = colors.assign_roles(areas, shares, order)
    harmonize = g["color_mode"] == "harmony"
    items = []
    for p, role in zip(places, roles):
        t = templates[p["motif"]]
        it = t.clone()
        it.cx, it.cy = p["x"] % T, p["y"] % T
        it.w, it.h = t.w * p["size"], t.h * p["size"]
        it.rotation = (t.rotation + p["rot"]) % 360
        if harmonize and it.kind in SHAPE_KINDS:
            from .render import is_closed
            if is_closed(it):
                it.fill = cols[role]
            else:
                it.stroke = cols[role]
        if g["stroke_motifs"] and it.kind in SHAPE_KINDS:
            it.stroke = g["motif_stroke"]
            it.stroke_width = float(g["motif_stroke_width"])
        items.append(it)
    stats = _stats(areas, [p["tier"] for p in places], roles, len(shares))
    return items, stats


def _stats(areas, tiers, roles, ncolors):
    tot = sum(areas) or 1.0
    tier_area = [0.0, 0.0, 0.0]
    role_area = [0.0] * ncolors
    for a, t, r in zip(areas, tiers, roles):
        tier_area[min(t, 2)] += a
        role_area[r] += a
    return {"count": len(areas),
            "tier_shares": [a / tot for a in tier_area],
            "color_shares": [a / tot for a in role_area]}


def generate(layer: Layer, doc: Document):
    """Return (items, stats) for a generator layer."""
    g = default_generator()
    g.update(layer.generator or {})
    T = float(doc.tile_size)
    rng = random.Random(int(g["seed"]))
    if g["motif_source"] == "layer":
        templates = layer_templates(doc.layer(g["motif_layer"]))
    else:
        templates = []
    if not templates:
        templates = builtin_templates(g["builtin_shape"])
    afac = [area_factor(t) for t in templates]
    rfac = [max(abs(t.w), abs(t.h)) for t in templates]
    need_field = g["algorithm"] == "noise" or g["rotation_mode"] == "flow"
    field = (TileableField(int(g["noise_scale"]), int(g["noise_octaves"]),
                           int(g["seed"])) if need_field else None)
    algo = g["algorithm"]
    if algo == "quadtree":
        return _quadtree_items(g, doc, T, rng, field, templates, afac)
    if algo == "grid":
        places = _grid(g, T, rng, field, templates)
    else:
        places = _scatter(g, T, rng, field, templates, rfac, afac)
    return _make_items(g, doc, T, rng, field, places, templates, afac)


def _quadtree_items(g, doc, T, rng, field, templates, afac):
    cells = quadtree_cells(g, T, rng)
    lw = max(0.0, float(g["qt_line_width"]))
    if g["qt_fill_mode"] == "motifs":
        sizes = sorted((min(w, h) for _x, _y, w, h, _d in cells),
                       reverse=True)
        # tiers by cell size rank, following the 60-30-10 shares
        cut1 = sizes[int(len(sizes) * 0.1)] if sizes else 0
        cut2 = sizes[int(len(sizes) * 0.4)] if sizes else 0
        places = []
        for x, y, w, h, _d in cells:
            m = min(w, h)
            tier = 0 if m >= cut1 else (1 if m >= cut2 else 2)
            cx, cy = x + w / 2, y + h / 2
            places.append({"x": cx, "y": cy, "size": m * 0.8, "tier": tier,
                           "motif": rng.randrange(len(templates)),
                           "noise": field(cx / T, cy / T) if field else .5,
                           "rot": _rotation(g, rng, field, cx, cy, T)})
        items, stats = _make_items(g, doc, T, rng, field, places,
                                   templates, afac)
        if lw > 0:
            items = [_cell_rect(c, T, None, g["qt_line_color"], lw)
                     for c in cells] + items
        return items, stats
    cols, shares = palette_for(g, doc)
    areas = [w * h for _x, _y, w, h, _d in cells]
    order = list(range(len(cells)))
    rng.shuffle(order)
    roles = colors.assign_roles(areas, shares, order)
    items = [_cell_rect(c, T, cols[r], g["qt_line_color"], lw)
             for c, r in zip(cells, roles)]
    tiers = [0 if d <= 1 else (1 if d <= 3 else 2)
             for _x, _y, _w, _h, d in cells]
    return items, _stats(areas, tiers, roles, len(shares))


def _cell_rect(cell, T, fill, line, lw) -> Item:
    x, y, w, h, _d = cell
    return Item(RECT, cx=(x + w / 2) % T, cy=(y + h / 2) % T, w=w, h=h,
                fill=fill, stroke=line if lw > 0 else None,
                stroke_width=lw)


# --------------------------------------------------------------- cache
_cache: "OrderedDict[str, tuple]" = OrderedDict()


def _cache_key(layer: Layer, doc: Document) -> str:
    g = layer.generator or {}
    src = None
    if g.get("motif_source") == "layer" and g.get("motif_layer"):
        ml = doc.layer(g["motif_layer"])
        src = [i.to_dict() for i in ml.items] if ml else None
    return json.dumps([g, src, doc.palette, doc.tile_size], sort_keys=True,
                      default=str)


def generate_cached(layer: Layer, doc: Document):
    key = _cache_key(layer, doc)
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit
    res = generate(layer, doc)
    _cache[key] = res
    while len(_cache) > 24:
        _cache.popitem(last=False)
    return res
