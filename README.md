# Repeat-Werx

Seamless repeating pattern designer built on **constrained randomness**:
algorithms that imitate nature, physics and architectural harmony, all
working on a wrap-around (toroidal) tile so every result repeats with no
visible seam.

## Features

- **Square tile canvas**: you edit the center tile while a 3×3 (or 5×5)
  repeat preview surrounds it. Shapes that cross an edge wrap to the
  opposite side.
- **Vector tools**: rectangle, ellipse, polygon, star, line and a
  pen/Bezier path, each with fill, outline, width and opacity. Move,
  scale and rotate handles, plus an eyedropper.
- **Import**: SVG goes in as vector. PNG, JPEG, WebP, TIFF, BMP, GIF and
  other raster formats go in with automatic or click-picked background
  removal, with tolerance and soft-edge controls.
- **Layers**: vector, raster and generator layers. Reorder by dragging,
  show/hide, lock, opacity, duplicate and delete. Merge down converts
  formats when needed. You can also convert a layer to raster and bake a
  generator into an editable layer.
- **Generators** (settings per layer, or applied to all generator layers):
  - *Poisson disc*: random placement with collision detection across the
    seams
  - *Noise field*: tileable Perlin noise that drives density, size, color
    and flow direction
  - *Mondrian / quadtree*: recursive subdivision into colored cells, or
    one motif per cell
  - *Jittered grid*: a lattice with jitter and staggered rows
  - **60-30-10** size tiers and color roles, balanced by area
  - **Color harmonies**: monochrome, analogous, complementary,
    split-complementary, triadic and tetradic
  - **Boundary weighting**: pulls motifs toward the tile seams or pushes
    them away
- **Files**: editable `.rwpx` designs (JSON with embedded images) and
  `.rwpat` pattern presets.
- **Export**: a single tile, an N×M grid, or a fixed image size (by tile
  pixel size or tiles across), as PNG, JPEG, TIFF, WebP, BMP, SVG or PDF,
  with a live preview.

## Running from source

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/repeatwerx          # or: .venv/bin/python -m repeatwerx
```

Python 3.12 is recommended. PySide6 has crashed under 3.10 here.

## Tests

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

## Layout

```
src/repeatwerx/
  core/   model, tileable noise, color harmonies, generators, rendering,
          image import/keying, project files, export (no widgets)
  gui/    canvas, layers panel, settings panel, dialogs, theme, icons
  app.py  main window
packaging/  PyInstaller spec, .deb and Windows (Inno Setup) builders
```

## Packaging

CI (`.github/workflows/build.yml`) runs the tests and builds a Linux `.deb`
and a Windows installer. To build locally:

```sh
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller packaging/repeatwerx.spec --noconfirm
sh packaging/build-deb.sh 0.1.0
```
