"""Small shared widgets."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QToolButton, QColorDialog, QMenu, QWidget,
                               QHBoxLayout, QSlider, QDoubleSpinBox)

from .icons import swatch_icon


class ColorButton(QToolButton):
    """Swatch button; click opens a color dialog. Optional 'None'."""
    color_changed = Signal(object)     # str | None

    def __init__(self, color: str | None = "#000000", allow_none=False,
                 stroke=False, parent=None):
        super().__init__(parent)
        self._color = color
        self._allow_none = allow_none
        self._stroke = stroke
        self.setAutoRaise(False)
        self.clicked.connect(self._pick)
        if allow_none:
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._menu)
        self._refresh()

    def color(self):
        return self._color

    def set_color(self, c, emit=False):
        self._color = c
        self._refresh()
        if emit:
            self.color_changed.emit(c)

    def _refresh(self):
        self.setIcon(swatch_icon(self._color, stroke=self._stroke))
        tip = self._color or "None"
        if self._allow_none:
            tip += "  (right-click for None)"
        self.setToolTip(tip)

    def _menu(self, pos):
        m = QMenu(self)
        m.addAction("Choose color…", self._pick)
        m.addAction("None", lambda: self.set_color(None, emit=True))
        m.exec(self.mapToGlobal(pos))

    def _pick(self):
        start = QColor(self._color or "#ffffff")
        c = QColorDialog.getColor(start, self, "Choose color")
        if c.isValid():
            self.set_color(c.name(), emit=True)


class SliderSpin(QWidget):
    """Slider + spin box bound to the same float value."""
    value_changed = Signal(float)

    def __init__(self, lo, hi, step=0.01, decimals=2, parent=None):
        super().__init__(parent)
        self._scale = 1 / step
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(lo * self._scale), int(hi * self._scale))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setFixedWidth(70)
        self.spin.setKeyboardTracking(False)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def _from_slider(self, v):
        val = v / self._scale
        self.spin.blockSignals(True)
        self.spin.setValue(val)
        self.spin.blockSignals(False)
        self.value_changed.emit(val)

    def _from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v * self._scale)))
        self.slider.blockSignals(False)
        self.value_changed.emit(v)

    def value(self) -> float:
        return self.spin.value()

    def setValue(self, v: float):
        self.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round(v * self._scale)))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)
        self.blockSignals(False)
