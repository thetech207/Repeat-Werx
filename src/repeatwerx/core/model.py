"""Document model: a square tile holding an ordered stack of layers.

Every item is positioned by its center (cx, cy), size (w, h) and rotation
(degrees); geometry is defined in a local unit box [-0.5, 0.5]^2 and
scaled by (w, h). Coordinates are tile units; anything that crosses a
tile edge wraps around when rendered, which keeps the tile seamless.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field, asdict

DEFAULT_TILE = 1024

# item kinds
RECT, ELLIPSE, POLYGON, STAR, PATH, IMAGE, SVG = (
    "rect", "ellipse", "polygon", "star", "path", "image", "svg")
SHAPE_KINDS = (RECT, ELLIPSE, POLYGON, STAR, PATH)

# layer kinds
VECTOR, RASTER, GENERATOR = "vector", "raster", "generator"
LAYER_KINDS = (VECTOR, RASTER, GENERATOR)


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class Item:
    kind: str
    cx: float = 0.0
    cy: float = 0.0
    w: float = 100.0
    h: float = 100.0
    rotation: float = 0.0
    fill: str | None = "#4a7ab5"
    stroke: str | None = "#1c1c1c"
    stroke_width: float = 2.0
    opacity: float = 1.0
    # polygon/star
    sides: int = 6
    inner_ratio: float = 0.5
    corner_radius: float = 0.0
    # path: list of segments in unit-box coords:
    #   ["M", x, y] ["L", x, y] ["C", x1, y1, x2, y2, x, y] ["Z"]
    segments: list = field(default_factory=list)
    # image / svg: key into Document.assets
    asset: str | None = None
    flip_x: bool = False
    flip_y: bool = False
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        d = asdict(self)
        # drop defaults that don't apply to this kind to keep files small
        if self.kind != PATH:
            d.pop("segments")
        if self.kind not in (IMAGE, SVG):
            d.pop("asset")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: copy.deepcopy(v) for k, v in d.items()
                      if k in known})

    def clone(self, new_identity: bool = True) -> "Item":
        it = Item.from_dict(self.to_dict())
        if new_identity:
            it.id = new_id()
        return it


def default_generator() -> dict:
    """Generator settings. Every algorithm reads only the keys it needs."""
    return {
        "algorithm": "poisson",       # poisson | noise | quadtree | grid
        "seed": 1,
        "motif_source": "builtin",    # builtin | layer
        "motif_layer": None,          # layer id when source == layer
        "builtin_shape": "circle",
        "base_size": 120.0,           # size of a "large" motif (units)
        # 60-30-10 size tiers: relative scale and share of covered area
        "tier_scales": [1.0, 0.55, 0.28],
        "tier_shares": [0.6, 0.3, 0.1],
        "coverage": 0.45,             # target fraction of tile covered
        "spacing": 6.0,               # collision padding (units)
        "allow_overlap": False,
        "rotation_mode": "random",    # none | random | flow | step
        "rotation_step": 90.0,
        "scale_jitter": 0.15,
        # noise field
        "noise_scale": 3,             # lattice cells per tile (period)
        "noise_octaves": 3,
        "noise_threshold": 0.45,      # density mask cutoff 0..1
        "noise_drives": ["density", "rotation"],
        # quadtree / mondrian
        "qt_max_depth": 5,
        "qt_min_cell": 48.0,
        "qt_split_chance": 0.75,
        "qt_ratio_mode": "golden",    # golden | random | half
        "qt_fill_mode": "cells",      # cells | motifs
        "qt_line_width": 6.0,
        "qt_line_color": "#1c1c1c",
        "qt_offset": True,            # shift so seams don't line up
        # grid
        "grid_cols": 6,
        "grid_jitter": 0.35,
        "grid_stagger": True,
        # boundary weighting: -1 avoid edges .. 0 even .. +1 favor edges
        "boundary_weight": 0.0,
        "boundary_band": 0.15,        # fraction of tile that counts as edge
        # color
        "color_mode": "harmony",      # harmony | original
        "use_document_palette": True,
        "harmony": "triadic",
        "base_color": "#2f6f8f",
        "color_shares": [0.6, 0.3, 0.1],
        "stroke_motifs": False,
        "motif_stroke": "#1c1c1c",
        "motif_stroke_width": 2.0,
    }


@dataclass
class Layer:
    name: str
    kind: str = VECTOR
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    items: list = field(default_factory=list)
    generator: dict | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        if self.kind == GENERATOR and self.generator is None:
            self.generator = default_generator()

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "visible": self.visible, "locked": self.locked,
                "opacity": self.opacity,
                "items": [it.to_dict() for it in self.items],
                "generator": copy.deepcopy(self.generator)}

    @classmethod
    def from_dict(cls, d: dict) -> "Layer":
        lay = cls(name=d.get("name", "Layer"), kind=d.get("kind", VECTOR),
                  visible=d.get("visible", True),
                  locked=d.get("locked", False),
                  opacity=d.get("opacity", 1.0),
                  items=[Item.from_dict(i) for i in d.get("items", [])],
                  generator=copy.deepcopy(d.get("generator")),
                  id=d.get("id") or new_id())
        if lay.kind == GENERATOR:
            gen = default_generator()
            gen.update(lay.generator or {})
            lay.generator = gen
        return lay


def default_palette() -> dict:
    return {"harmony": "triadic", "base_color": "#2f6f8f",
            "shares": [0.6, 0.3, 0.1]}


@dataclass
class Document:
    tile_size: int = DEFAULT_TILE
    background: str | None = "#f4f1ea"
    layers: list = field(default_factory=list)   # bottom -> top
    # assets: id -> {"type": "png"|"svg", "data": base64-png | svg text,
    #                "w": px, "h": px, "name": str}
    assets: dict = field(default_factory=dict)
    palette: dict = field(default_factory=default_palette)
    name: str = "Untitled"

    def __post_init__(self):
        if not self.layers:
            self.layers.append(Layer("Layer 1", VECTOR))

    # -- lookups -------------------------------------------------------
    def layer(self, lid: str) -> Layer | None:
        return next((l for l in self.layers if l.id == lid), None)

    def layer_index(self, lid: str) -> int:
        for i, l in enumerate(self.layers):
            if l.id == lid:
                return i
        return -1

    def find_item(self, iid: str):
        for lay in self.layers:
            for it in lay.items:
                if it.id == iid:
                    return lay, it
        return None, None

    def unique_layer_name(self, base: str) -> str:
        names = {l.name for l in self.layers}
        n = 1
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    # -- (de)serialisation --------------------------------------------
    def state(self) -> dict:
        """Undo snapshot (assets are append-only, so they're excluded)."""
        return {"tile_size": self.tile_size, "background": self.background,
                "layers": [l.to_dict() for l in self.layers],
                "palette": copy.deepcopy(self.palette), "name": self.name}

    def restore(self, st: dict):
        self.tile_size = st["tile_size"]
        self.background = st["background"]
        self.layers = [Layer.from_dict(l) for l in st["layers"]]
        self.palette = copy.deepcopy(st["palette"])
        self.name = st.get("name", self.name)

    def used_assets(self) -> set:
        used = {it.asset for l in self.layers for it in l.items if it.asset}
        return used

    def to_dict(self) -> dict:
        d = self.state()
        used = self.used_assets()
        d["assets"] = {k: v for k, v in self.assets.items() if k in used}
        d["format"] = "rwpx"
        d["version"] = 1
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        doc = cls(layers=[Layer("tmp")])
        doc.restore({"tile_size": d.get("tile_size", DEFAULT_TILE),
                     "background": d.get("background"),
                     "layers": d.get("layers") or [
                         Layer("Layer 1").to_dict()],
                     "palette": d.get("palette") or default_palette(),
                     "name": d.get("name", "Untitled")})
        doc.assets = dict(d.get("assets", {}))
        return doc
