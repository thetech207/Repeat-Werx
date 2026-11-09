""".rwpx project files and .rwpat generator presets (versioned JSON)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .model import Document, default_generator

PROJECT_SUFFIX = ".rwpx"
PRESET_SUFFIX = ".rwpat"


def save_project(doc: Document, path) -> Path:
    path = Path(path)
    if path.suffix.lower() != PROJECT_SUFFIX:
        path = path.with_suffix(PROJECT_SUFFIX)
    path.write_text(json.dumps(doc.to_dict(), indent=1))
    return path


def load_project(path) -> Document:
    data = json.loads(Path(path).read_text())
    if data.get("format") != "rwpx":
        raise ValueError(f"not a Repeat-Werx project file: {path}")
    if int(data.get("version", 1)) > 1:
        raise ValueError("project was saved by a newer Repeat-Werx")
    return Document.from_dict(data)


def save_preset(generator: dict, palette: dict | None, path) -> Path:
    path = Path(path)
    if path.suffix.lower() != PRESET_SUFFIX:
        path = path.with_suffix(PRESET_SUFFIX)
    g = copy.deepcopy(generator)
    g.pop("motif_layer", None)      # layer ids are project-specific
    path.write_text(json.dumps({"format": "rwpat", "version": 1,
                                "generator": g, "palette": palette},
                               indent=1))
    return path


def load_preset(path):
    data = json.loads(Path(path).read_text())
    if data.get("format") != "rwpat":
        raise ValueError(f"not a Repeat-Werx pattern preset: {path}")
    g = default_generator()
    g.update(data.get("generator") or {})
    return g, data.get("palette")
