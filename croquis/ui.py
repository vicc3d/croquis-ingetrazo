# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The pieces of the bento panel: tiles, segmented choices, chips, icons.

Plain Qt widgets and one stylesheet, so the panel is light. Every colour is
taken from IngeTrazo's palette (its light or dark theme), and the icons are
SVG in ``currentColor``, painted in the palette's text colour (the accent
when chosen) and remade when the theme changes.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

ICONS = Path(__file__).resolve().parent / "icons"
_cache: dict = {}


def icon_pixmap(name: str, px: int, colour: QColor, dpr: float = 1.0) -> QPixmap:
    """The icon ``name`` at ``px`` logical pixels, in ``colour``."""
    key = (name, px, colour.name(QColor.HexArgb), round(dpr, 2))
    pm = _cache.get(key)
    if pm is not None:
        return pm
    size = 16 if px <= 16 else 20 if px <= 20 else 24
    path = ICONS / str(size) / f"{name}.svg"
    if not path.is_file():
        path = ICONS / "24" / f"{name}.svg"
    pm = QPixmap(int(px * dpr), int(px * dpr))
    pm.fill(Qt.transparent)
    if path.is_file():
        data = path.read_text(encoding="utf-8").replace("currentColor", colour.name())
        r = QSvgRenderer(QByteArray(data.encode("utf-8")))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, px * dpr, px * dpr))
        p.end()
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def themed_icon(widget: QWidget, name: str, px: int) -> QIcon:
    """An icon in the widget's text colour, and the accent when checked."""
    pal = widget.palette()
    dpr = widget.devicePixelRatioF()
    ic = QIcon()
    ic.addPixmap(icon_pixmap(name, px, pal.color(QPalette.WindowText), dpr), QIcon.Normal, QIcon.Off)
    ic.addPixmap(icon_pixmap(name, px, pal.color(QPalette.Highlight), dpr), QIcon.Normal, QIcon.On)
    dim = QColor(pal.color(QPalette.WindowText))
    dim.setAlpha(110)
    ic.addPixmap(icon_pixmap(name, px, dim, dpr), QIcon.Disabled, QIcon.Off)
    return ic


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def stylesheet(pal: QPalette) -> str:
    """The panel's look, from the theme's palette."""
    win = pal.color(QPalette.Window)
    text = pal.color(QPalette.WindowText)
    acc = pal.color(QPalette.Highlight)
    dark = win.lightness() < 128
    tile = _mix(win, QColor("white") if dark else QColor("white"), 0.06 if dark else 0.55)
    well = _mix(win, QColor("black"), 0.18 if dark else 0.05)
    border = _mix(win, text, 0.16)
    hover = _mix(tile, text, 0.07)
    on_bg = _mix(tile, acc, 0.22 if dark else 0.14)
    muted = _mix(win, text, 0.6)
    acc_text = "#ffffff" if acc.lightness() < 170 else "#111111"
    return f"""
#croquisPanel {{ background: transparent; }}
#croquisPanel QLabel {{ background: transparent; }}
QFrame#tile {{ background: {tile.name()}; border: 1px solid {border.name()};
  border-radius: 12px; }}
QLabel#tileTitle {{ color: {muted.name()}; font-size: 12px; }}
QLabel#hint, QLabel#scale {{ color: {muted.name()}; font-size: 11px; }}
QFrame#well {{ background: {well.name()}; border-radius: 8px; border: none; }}
QFrame#well QToolButton {{ border: none; border-radius: 6px; padding: 4px 2px;
  background: transparent; color: {muted.name()}; font-size: 11px; }}
QFrame#well QToolButton:hover {{ background: {hover.name()}; }}
QFrame#well QToolButton:checked {{ background: {tile.name()}; color: {text.name()};
  border: 1px solid {border.name()}; }}
QToolButton#chip {{ border: 1px solid {border.name()}; border-radius: 8px;
  padding: 5px 3px; background: transparent; color: {muted.name()}; font-size: 11px; }}
QToolButton#chip:hover {{ background: {hover.name()}; }}
QToolButton#chip:checked {{ background: {on_bg.name()}; border-color: {acc.name()};
  color: {text.name()}; }}
QToolButton#fold {{ border: none; background: transparent; color: {muted.name()};
  font-size: 12px; text-align: left; }}
QPushButton#draw {{ background: {acc.name()}; color: {acc_text}; border: none;
  border-radius: 8px; padding: 9px 10px; font-size: 13px; }}
QPushButton#draw:hover {{ background: {acc.lighter(112).name()}; }}
QPushButton#draw:pressed {{ background: {acc.darker(110).name()}; }}
"""


class Tile(QFrame):
    """One box of the bento: a small icon and title, then its body."""

    def __init__(self, icon: str | None, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("tile")
        self._icon_name = icon
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(7)
        self.head = QHBoxLayout()
        self.head.setSpacing(6)
        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        self.title = QLabel(title)
        self.title.setObjectName("tileTitle")
        if icon:
            self.head.addWidget(self.icon)
        self.head.addWidget(self.title)
        self.head.addStretch(1)
        lay.addLayout(self.head)
        self.body = lay
        self.refresh_icons()

    def refresh_icons(self) -> None:
        if self._icon_name:
            pal = self.palette()
            dim = QColor(pal.color(QPalette.WindowText))
            dim.setAlpha(170)
            self.icon.setPixmap(icon_pixmap(self._icon_name, 16, dim,
                                            self.devicePixelRatioF()))


class Choice(QToolButton):
    """A button with an icon over its label: a chip, or a segment."""

    def __init__(self, icon: str | None, text: str, value=None, chip: bool = True,
                 icon_px: int = 20, parent=None) -> None:
        super().__init__(parent)
        if chip:
            self.setObjectName("chip")
        self.value = value
        self._icon_name = icon
        self._icon_px = icon_px
        self.setText(text)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if icon else Qt.ToolButtonTextOnly)
        self.setIconSize(QSize(icon_px, icon_px))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        self.refresh_icons()

    def refresh_icons(self) -> None:
        if self._icon_name:
            self.setIcon(themed_icon(self, self._icon_name, self._icon_px))


class Segmented(QFrame):
    """One choice among a few, all in sight: segments in a well."""

    changed = Signal(object)

    def __init__(self, options, parent=None, icon_px: int = 18) -> None:
        super().__init__(parent)
        self.setObjectName("well")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list = []
        for value, icon, text in options:
            b = Choice(icon, text, value, chip=False, icon_px=icon_px)
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons.append(b)
        self.group.buttonClicked.connect(lambda b: self.changed.emit(b.value))

    def value(self):
        b = self.group.checkedButton()
        return b.value if b is not None else None

    def set_value(self, value) -> None:
        for b in self.buttons:
            if b.value == value:
                b.setChecked(True)
                return

    def refresh_icons(self) -> None:
        for b in self.buttons:
            b.refresh_icons()


def swatch_pixmap(colours, w: int, h: int, dpr: float) -> QPixmap:
    """A small colour sample: the colours side by side, rounded."""
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    n = len(colours)
    p.setClipRect(0, 0, w, h)
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), 4, 4)
    p.setClipPath(path)
    for i, c in enumerate(colours):
        p.setBrush(QColor(c))
        p.drawRect(QRectF(i * w / n, 0, w / n + 1, h))
    p.end()
    return pm
