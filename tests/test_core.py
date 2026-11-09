import math

import pytest
from PySide6.QtGui import QImage, QColor

from repeatwerx.core import color, imageproc
from repeatwerx.core.export import ExportSpec, compose, export
from repeatwerx.core.generators import (ALGORITHMS, generate, torus_distance,
                                        boundary_factor)
from repeatwerx.core.model import (Document, Layer, Item, GENERATOR, VECTOR,
                                   RECT, ELLIPSE)
from repeatwerx.core.noise import PeriodicPerlin, TileableField
from repeatwerx.core.project import (save_project, load_project, save_preset,
                                     load_preset)
from repeatwerx.core.render import render_tile


def gen_doc(**g):
    doc = Document()
    lay = Layer("Gen", GENERATOR)
    lay.generator.update(g)
    doc.layers.append(lay)
    return doc, lay


def test_noise_is_periodic():
    n = PeriodicPerlin(4, seed=3)
    for x, y in ((0.3, 0.7), (1.9, 2.2), (3.5, 0.1)):
        assert n(x, y) == pytest.approx(n(x + 4, y), abs=1e-9)
        assert n(x, y) == pytest.approx(n(x, y + 4), abs=1e-9)
    f = TileableField(3, 3, seed=1)
    for u, v in ((0.0, 0.5), (0.25, 0.0)):
        assert f(u, v) == pytest.approx(f(u + 1, v), abs=1e-9)
        assert f(u, v) == pytest.approx(f(u, v + 1), abs=1e-9)
        assert 0.0 <= f(u, v) <= 1.0


@pytest.mark.parametrize("scheme", list(color.HARMONIES))
def test_harmonies(scheme):
    cols = color.harmony("#4a7ab5", scheme)
    assert len(cols) >= 3
    assert all(c.startswith("#") and len(c) == 7 for c in cols)


def test_assign_roles_approaches_60_30_10():
    areas = [1.0] * 200
    roles = color.assign_roles(areas, [0.6, 0.3, 0.1])
    counts = [roles.count(i) for i in range(3)]
    assert counts == pytest.approx([120, 60, 20], abs=4)


def test_torus_distance_wraps():
    assert torus_distance((5, 5), (1019, 5), 1024) == pytest.approx(10)
    assert torus_distance((5, 5), (1019, 1019), 1024) == \
        pytest.approx(math.hypot(10, 10))


def test_boundary_factor_signs():
    T = 1024
    edge, mid = (5, 512), (512, 512)
    assert boundary_factor(*edge, T, 1.0, 0.15) > \
        boundary_factor(*mid, T, 1.0, 0.15)
    assert boundary_factor(*edge, T, -1.0, 0.15) < \
        boundary_factor(*mid, T, -1.0, 0.15)


@pytest.mark.parametrize("algo", list(ALGORITHMS))
def test_generators_produce_items(algo):
    doc, lay = gen_doc(algorithm=algo, seed=7)
    items, stats = generate(lay, doc)
    assert items and stats["count"] > 0
    assert sum(stats["color_shares"]) == pytest.approx(1.0, abs=1e-6)
    items2, _ = generate(lay, doc)
    assert [(i.cx, i.cy) for i in items] == [(i.cx, i.cy) for i in items2]


def test_poisson_respects_spacing_across_seams():
    doc, lay = gen_doc(algorithm="poisson", seed=11, builtin_shape="circle",
                       spacing=4.0, overlap=0.0)
    items, _ = generate(lay, doc)
    T = doc.tile_size
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            d = torus_distance((a.cx, a.cy), (b.cx, b.cy), T)
            assert d >= (max(a.w, a.h) + max(b.w, b.h)) / 2 * 0.98


def test_size_tiers_follow_shares():
    doc, lay = gen_doc(algorithm="poisson", seed=5, coverage=0.5)
    _items, stats = generate(lay, doc)
    assert stats["tier_shares"][0] > stats["tier_shares"][1] > \
        stats["tier_shares"][2]


def test_render_is_seamless():
    doc = Document(background="#ffffff")
    doc.layers[0].items.append(Item(ELLIPSE, cx=0, cy=512, w=200, h=200,
                                    fill="#ff0000", stroke=None))
    img = render_tile(doc, 256)
    left, right = img.pixelColor(2, 128), img.pixelColor(253, 128)
    assert left.red() > 200 and left.green() < 60
    assert right.red() > 200 and right.green() < 60


def test_project_roundtrip(tmp_path):
    doc, lay = gen_doc(algorithm="quadtree", seed=3)
    doc.layers[0].items.append(Item(RECT, cx=100, cy=200, w=50, h=60))
    img = QImage(8, 8, QImage.Format.Format_ARGB32)
    img.fill(QColor("#00ff00"))
    key = imageproc.add_image_asset(doc, img, "green")
    r = Layer("Raster", "raster")
    r.items.append(Item("image", cx=10, cy=10, w=8, h=8, asset=key))
    doc.layers.append(r)
    p = save_project(doc, tmp_path / "design")
    assert p.suffix == ".rwpx"
    back = load_project(p)
    assert back.state() == doc.state()
    assert key in back.assets
    pp = save_preset(lay.generator, doc.palette, tmp_path / "preset")
    g, pal = load_preset(pp)
    assert g["algorithm"] == "quadtree" and pal == doc.palette


def test_load_rejects_other_formats(tmp_path):
    p = tmp_path / "x.rwpx"
    p.write_text('{"format": "bwpx"}')
    with pytest.raises(Exception):
        load_project(p)


def test_key_out_background():
    img = QImage(20, 20, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    for x in range(8, 12):
        for y in range(8, 12):
            img.setPixelColor(x, y, QColor("#000000"))
    assert imageproc.detect_background(img) == "#ffffff"
    out = imageproc.key_out(img, "#ffffff", tolerance=10, feather=0)
    assert out.pixelColor(0, 0).alpha() == 0
    assert out.pixelColor(10, 10).alpha() == 255


@pytest.mark.parametrize("spec,size", [
    (ExportSpec(mode="tile", tile_px=128), (128, 128)),
    (ExportSpec(mode="grid", tile_px=64, cols=4, rows=3), (256, 192)),
    (ExportSpec(mode="size", width=300, height=200, tile_px=100),
     (300, 200)),
])
def test_compose_sizes(spec, size):
    doc, _ = gen_doc(seed=2)
    img = compose(doc, spec)
    assert (img.width(), img.height()) == size


@pytest.mark.parametrize("ext", ["png", "jpg", "webp", "svg", "pdf"])
def test_export_formats(tmp_path, ext):
    doc, _ = gen_doc(seed=2)
    p = export(doc, ExportSpec(mode="grid", tile_px=64, cols=2, rows=2),
               tmp_path / f"out.{ext}")
    assert p.exists() and p.stat().st_size > 0


def test_wrap_offsets_cover_oversized_items():
    from PySide6.QtCore import QRectF
    from repeatwerx.core.render import wrap_offsets
    T = 100.0
    offs = wrap_offsets(QRectF(-150, -150, 400, 400), T)
    assert len(offs) == 25          # spans x/y in [-150, 250]
    assert (200.0, -200.0) in offs and (300.0, 0.0) not in offs
    assert len(wrap_offsets(QRectF(10, 10, 20, 20), T)) == 1


def test_export_does_not_mutate_spec(tmp_path):
    doc, _ = gen_doc(seed=2)
    spec = ExportSpec(mode="tile", tile_px=32, background=False)
    export(doc, spec, tmp_path / "a.jpg")
    assert spec.background is False


def test_noise_scaled_motifs_do_not_overlap():
    doc, lay = gen_doc(algorithm="noise", seed=4, builtin_shape="circle",
                       noise_drives=["density", "scale"], noise_threshold=0.2,
                       coverage=0.8, spacing=0.0)
    items, _ = generate(lay, doc)
    T = doc.tile_size
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            d = torus_distance((a.cx, a.cy), (b.cx, b.cy), T)
            assert d >= (a.w + b.w) / 2 * 0.98
