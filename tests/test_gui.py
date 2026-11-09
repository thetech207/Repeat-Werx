import pytest

from repeatwerx.app import MainWindow
from repeatwerx.core.model import GENERATOR, RASTER, VECTOR, Item, RECT
from repeatwerx.gui.canvas import Tool


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    w.show()
    qtbot.waitExposed(w)
    yield w
    w.undo_stack.setClean()
    w.close()
    w.deleteLater()


def test_starts_with_square_tile_and_3x3(win):
    assert win.canvas.repeat_n == 3
    assert win.doc.tile_size == 1024


def test_add_item_undo_redo(win):
    win.add_item(Item(RECT, cx=1100, cy=-20, w=100, h=100))
    it = win.doc.layers[-1].items[0]
    assert (it.cx, it.cy) == (76, 1004)          # wrapped into the tile
    win.undo_stack.undo()
    assert not win.doc.layers[-1].items
    win.undo_stack.redo()
    assert len(win.doc.layers[-1].items) == 1


def test_layer_operations(win):
    win.add_item(Item(RECT, cx=100, cy=100, w=50, h=50))
    win.add_layer(VECTOR)
    win.add_item(Item(RECT, cx=300, cy=300, w=50, h=50))
    assert len(win.doc.layers) == 2
    win.merge_down(win.active_layer_id)
    assert len(win.doc.layers) == 1
    assert len(win.doc.layers[0].items) == 2
    win.convert_to_raster(win.active_layer_id)
    assert win.doc.layers[0].kind == RASTER
    win.add_layer(GENERATOR)
    gid = win.active_layer_id
    win.move_layer(gid, -1)
    assert win.doc.layers[0].id == gid
    win.bake_layer(gid)
    assert win.doc.layers[0].kind == VECTOR and win.doc.layers[0].items
    win.delete_layer(win.doc.layers[0].id)
    assert len(win.doc.layers) == 1


def test_generator_settings_scope(win):
    win.add_layer(GENERATOR)
    a = win.active_layer_id
    win.add_layer(GENERATOR)
    b = win.active_layer_id
    win.update_generator("algorithm", "noise")
    assert win.doc.layer(b).generator["algorithm"] == "noise"
    assert win.doc.layer(a).generator["algorithm"] != "noise"
    win.update_generator("harmony", "analogous", all_layers=True)
    assert win.doc.layer(a).generator["harmony"] == "analogous"


def test_draw_rectangle_with_mouse(win, qtbot):
    from PySide6.QtCore import Qt, QPoint
    win.canvas.fit_tile()
    win.canvas.set_tool(Tool.RECT)
    c = win.canvas.rect().center()
    qtbot.mousePress(win.canvas, Qt.MouseButton.LeftButton,
                     pos=c - QPoint(40, 40))
    qtbot.mouseMove(win.canvas, c + QPoint(40, 30))
    qtbot.mouseRelease(win.canvas, Qt.MouseButton.LeftButton,
                       pos=c + QPoint(40, 30))
    items = win.doc.layers[-1].items
    assert len(items) == 1 and items[0].kind == RECT


def test_save_and_reload(win, tmp_path):
    win.add_layer(GENERATOR)
    win._file_path = str(tmp_path / "t.rwpx")
    assert win.save_project()
    n = len(win.doc.layers)
    win.load_path(win._file_path)
    assert len(win.doc.layers) == n


def test_import_dialog_opens_cleanly(qtbot, tmp_path):
    from PySide6.QtGui import QImage, QColor
    from repeatwerx.gui.import_dialog import ImageImportDialog
    img = QImage(40, 40, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    img.setPixelColor(20, 20, QColor("#000000"))
    p = tmp_path / "w.png"
    img.save(str(p))
    d = ImageImportDialog(str(p), False)
    qtbot.addWidget(d)
    assert d.mode_auto.isChecked()
    assert d.preview.img is not None
    assert d.result_image().pixelColor(0, 0).alpha() == 0


def test_merge_refuses_mixed_visibility(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win.add_item(Item(RECT, cx=100, cy=100, w=50, h=50))
    win.add_layer(VECTOR)
    win.add_item(Item(RECT, cx=300, cy=300, w=50, h=50))
    win.doc.layers[-1].visible = False
    win.merge_down(win.active_layer_id)
    assert len(win.doc.layers) == 2


def test_merge_preserves_effective_opacity(win):
    win.add_item(Item(RECT, cx=100, cy=100, w=50, h=50))
    win.doc.layers[0].opacity = 0.5
    win.add_layer(VECTOR)
    win.add_item(Item(RECT, cx=300, cy=300, w=50, h=50))
    win.doc.layers[1].opacity = 1.0
    win.merge_down(win.active_layer_id)
    lay = win.doc.layers[0]
    eff = sorted(it.opacity * lay.opacity for it in lay.items)
    assert eff == pytest.approx([0.5, 1.0])


def test_locked_layer_not_editable_via_select_all(win):
    win.add_item(Item(RECT, cx=100, cy=100, w=50, h=50))
    win.toggle_layer_lock(win.active_layer_id)
    win.select_all()
    win.selection = [win.doc.layers[0].items[0].id]
    win.delete_selection()
    assert len(win.doc.layers[0].items) == 1


def test_convert_keeps_generator_motif_link(win):
    win.add_item(Item(RECT, cx=100, cy=100, w=50, h=50))
    src = win.active_layer_id
    win.add_layer(GENERATOR)
    win.update_generator("motif_source", "layer")
    win.update_generator("motif_layer", src)
    gen = win.doc.layer(win.active_layer_id)
    win.convert_to_raster(src)
    assert win.doc.layer(src).kind == RASTER
    assert gen.generator["motif_layer"] == src
