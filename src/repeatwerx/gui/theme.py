"""Light/dark/system theme and palette-derived stylesheets.

Mirrors Black-Werx so the two apps look like siblings.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

_system = {"palette": None, "style": None}


def capture_system():
    if _system["palette"] is None:
        _system["palette"] = QApplication.palette()
        _system["style"] = QApplication.style().objectName()


def theme_palette(mode: str) -> QPalette:
    if mode == "system":
        return _system["palette"] or QApplication.palette()
    p = QPalette()
    if mode == "dark":
        win, base, alt = "#2e2b27", "#24211d", "#38342e"
        text, btn, hi = "#ece7dc", "#3a362f", "#4a7ab5"
    else:
        win, base, alt = "#f4f1ea", "#fdfcf8", "#ece8dd"
        text, btn, hi = "#2b261e", "#e7e2d5", "#3d6fb4"
    R = QPalette.ColorRole
    p.setColor(R.Window, QColor(win))
    p.setColor(R.WindowText, QColor(text))
    p.setColor(R.Base, QColor(base))
    p.setColor(R.AlternateBase, QColor(alt))
    p.setColor(R.Text, QColor(text))
    p.setColor(R.Button, QColor(btn))
    p.setColor(R.ButtonText, QColor(text))
    p.setColor(R.Highlight, QColor(hi))
    p.setColor(R.HighlightedText, QColor("#ffffff"))
    p.setColor(R.Mid, QColor(text).darker(130))
    p.setColor(R.PlaceholderText, QColor(text).darker(140))
    p.setColor(R.ToolTipBase, QColor(win))
    p.setColor(R.ToolTipText, QColor(text))
    return p


def apply_theme(mode: str):
    capture_system()
    if sys.platform == "win32":
        # native Windows style ignores the palette for menus/scrollbars
        QApplication.setStyle(_system["style"] if mode == "system"
                              else "fusion")
    QApplication.setPalette(theme_palette(mode))


def is_dark() -> bool:
    win = QApplication.palette().color(QPalette.ColorRole.Window)
    return (0.299 * win.red() + 0.587 * win.green()
            + 0.114 * win.blue()) < 140


def chrome() -> dict:
    pal = QApplication.palette()
    win = pal.color(QPalette.ColorRole.Window)
    txt = pal.color(QPalette.ColorRole.ButtonText)
    hi = pal.color(QPalette.ColorRole.Highlight)
    htxt = pal.color(QPalette.ColorRole.HighlightedText)
    if is_dark():
        btn, hover = win.lighter(150), win.lighter(180)
        pressed, border = win.lighter(165), win.lighter(200)
    else:
        btn, hover = win.darker(106), win.lighter(102)
        pressed, border = win.darker(112), win.darker(118)
    return {"win": win, "btn": btn, "hover": hover, "pressed": pressed,
            "border": border, "txt": txt, "hi": hi, "htxt": htxt}


def icon_ink() -> QColor:
    c = chrome()["btn"]
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("#1c1c1c") if lum > 140 else QColor("#f2f2f2")


def bar_qss(name: str, edge: str) -> str:
    c = chrome()
    edge_css = (f"border-{edge}: 1px solid {c['border'].name()};"
                if edge else "")
    return f"""
        QToolBar#{name} {{ background: {c['win'].name()}; {edge_css}
                           spacing: 2px; padding: 5px 7px; }}
        QToolBar#{name}::separator {{ background: {c['border'].name()};
                                      width: 1px; height: 1px;
                                      margin: 4px 3px; }}
        QToolBar#{name} QToolButton {{
            background: {c['btn'].name()}; color: {c['txt'].name()};
            border: 1px solid {c['border'].name()}; border-radius: 7px;
            padding: 1px 7px; margin: 2px; font-size: 11px; }}
        QToolBar#{name} QToolButton:hover {{
            background: {c['hover'].name()}; }}
        QToolBar#{name} QToolButton:pressed {{
            background: {c['pressed'].name()}; }}
        QToolBar#{name} QToolButton:checked {{
            background: {c['hi'].name()}; color: {c['htxt'].name()};
            border-color: {c['hi'].name()}; }}
        QToolBar#{name} QLabel {{ color: {c['txt'].name()};
                                  font-size: 11px; padding: 0 2px; }}
    """


def side_panel_qss() -> str:
    c = chrome()
    return f"""
        #SidePanel {{ background:{c['btn'].name()};
                      border-radius:10px; font-size:11px; }}
        #SidePanel QPushButton, #SidePanel QToolButton {{
            background:{c['win'].name()}; color:{c['txt'].name()};
            border:1px solid {c['border'].name()};
            border-radius:6px; padding:2px 8px; font-size:11px; }}
        #SidePanel QPushButton:hover, #SidePanel QToolButton:hover {{
            background:{c['hover'].name()}; }}
        #SidePanel QPushButton:checked, #SidePanel QToolButton:checked {{
            background:{c['hi'].name()}; color:{c['htxt'].name()};
            border-color:{c['hi'].name()}; }}
        #SidePanel QComboBox, #SidePanel QListWidget,
        #SidePanel QSpinBox, #SidePanel QDoubleSpinBox,
        #SidePanel QLineEdit {{
            background:{c['win'].name()}; color:{c['txt'].name()};
            border:1px solid {c['border'].name()};
            border-radius:6px; padding:1px 4px; }}
        #SidePanel QListWidget::item {{ padding:2px 3px; border-radius:4px;
                                        color:{c['txt'].name()}; }}
        #SidePanel QListWidget::item:selected {{
            color:{c['htxt'].name()}; background:{c['hi'].name()}; }}
        #SidePanel QLabel, #SidePanel QCheckBox, #SidePanel QRadioButton {{
            color:{c['txt'].name()}; }}
        #SidePanel QGroupBox {{ color:{c['txt'].name()};
            border:1px solid {c['border'].name()}; border-radius:8px;
            margin-top:10px; padding:8px 4px 4px 4px; font-weight:bold; }}
        #SidePanel QGroupBox::title {{ subcontrol-origin: margin;
            left: 8px; padding: 0 3px; }}
        #SidePanel QTabWidget::pane {{ border:none; }}
        #SidePanel QTabBar::tab {{ background:{c['win'].name()};
            color:{c['txt'].name()}; border:1px solid {c['border'].name()};
            border-radius:6px; padding:3px 10px; margin:2px; }}
        #SidePanel QTabBar::tab:selected {{ background:{c['hi'].name()};
            color:{c['htxt'].name()}; border-color:{c['hi'].name()}; }}
        #SidePanel QScrollArea {{ background: transparent; border:none; }}
        #SidePanel QScrollArea > QWidget > QWidget {{
            background: transparent; }}
    """


def panel_tab_qss() -> str:
    c = chrome()
    return f"""
        QToolButton {{ background:{c['btn'].name()}; color:{c['txt'].name()};
                      border:1px solid {c['border'].name()};
                      border-top-right-radius:5px;
                      border-bottom-right-radius:5px;
                      font-size:10px; padding:0px; }}
        QToolButton:hover {{ background:{c['hover'].name()}; }}
        QToolButton:pressed {{ background:{c['pressed'].name()}; }}
    """
