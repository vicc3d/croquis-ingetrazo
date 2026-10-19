# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The «Croquis» tab of the side tray, as a bento of small boxes, and the
window the drawing opens in.

One box per decision: the style to start from (cards with a real thumbnail),
the line (with a live sample of the hand), the technique, the light, the
materials, the hatching, the composition, the fine settings (folded), and
the size with the button that draws. The settings are one dict
(:mod:`.presets`), kept per user.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QSettings, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy, QSlider, QToolButton,
    QVBoxLayout, QWidget,
)

from . import drawing
from . import presets as ps
from . import strokes as st
from .texts import tr
from .ui import (Choice, Segmented, Switch, Tile, icon_pixmap, stylesheet,
                 swatch_pixmap, themed_icon)

_SETTINGS = ("ingetrazo-croquis", "croquis")
THUMBS = Path(__file__).resolve().parent / "thumbs"
SIZES = ((1600, "S"), (2400, "M"), (3600, "L"), (0, "…"))
FORMATS = (("px", "Width in pixels"), ("A5", "A5"), ("A4", "A4"), ("A3", "A3"))
#: A page format's margin round the drawing, as a share of each side.
PAGE_MARGIN = 0.07
MATERIALS = (("colour", ("#D85A30", "#BA7517")), ("greys", ("#B4B2A9", "#5F5E5A")),
             ("contrast", ("#F1EFE8", "#2C2C2A")), ("none", ("#F1EFE8",)))


class LinePreview(QWidget):
    """A sample of the line as the hand will draw it: a rectangle shaded with
    diagonal lines, redrawn as the settings change. The corners show the
    overshoot, the shading the hand's waver, the outline its weight."""

    W, H = 330.0, 58.0
    X0, X1, Y0, Y1 = 40.0, 290.0, 7.0, 51.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        self.style_ = st.LineStyle()
        x0, x1, y0, y1 = self.X0, self.X1, self.Y0, self.Y1
        edges = [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]]
        # Diagonals at 45°, cut to the rectangle.
        hatch = []
        h = y1 - y0
        for c in np.arange(x0 - h + 14.0, x1, 14.0):
            a = np.array([c, y1])
            b = np.array([c + h, y0])
            t0 = max(0.0, (x0 - a[0]) / h)
            t1 = min(1.0, (x1 - a[0]) / h)
            if t1 - t0 > 0.15:
                p0 = a + (b - a) * t0
                p1 = a + (b - a) * t1
                hatch.append([p0[0] + 2.0, p0[1] - 2.0, p1[0] - 2.0, p1[1] + 2.0])
        self.segs = np.array(edges + hatch, dtype=np.float64)
        self.kinds = np.array([True] * 4 + [False] * len(hatch))

    def set_style(self, style: st.LineStyle) -> None:
        self.style_ = style
        self.update()

    def paintEvent(self, _ev) -> None:            # noqa: N802 (Qt)
        from dataclasses import replace
        w = max(1, self.width())
        # Seen at about a fifth of a drawing's size; the ink a little
        # heavier, so the sample reads in a small box.
        style = replace(self.style_, width=self.style_.width * 1.3)
        strokes = st.strokes_for(self.segs, self.kinds, style, 600)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        ink = QColor(self.palette().color(QPalette.WindowText))
        k = min(w / self.W, self.height() / self.H)
        p.translate((w - self.W * k) / 2, (self.height() - self.H * k) / 2)
        p.scale(k, k)
        for s in strokes:
            c = QColor(ink)
            c.setAlphaF(max(0.0, min(1.0, s.opacity)))
            p.setBrush(c)
            p.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in s.outline]))
        p.end()


def _slider(lo: int, hi: int) -> QSlider:
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setMinimumWidth(60)
    s.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return s


class CroquisPanel(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._window = None
        self._styling = False
        self._loading = False
        self.setObjectName("croquisPanel")
        self.s = self._read()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("croquisPanel")
        scroll.setWidget(body)
        grid = QGridLayout(body)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        row = 0
        for tile, span in self._build():
            if span == 2:
                grid.addWidget(tile, row, 0, 1, 2)
            else:
                grid.addWidget(tile[0], row, 0)
                grid.addWidget(tile[1], row, 1)
            row += 1
        grid.setRowStretch(row, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self._restyle()
        self._show_state()
        # IngeTrazo switches themes with the application's palette, which a
        # widget with its own stylesheet is not told about: listen to it.
        inst = QApplication.instance()
        if inst is not None and hasattr(inst, "paletteChanged"):
            inst.paletteChanged.connect(self._on_app_palette)

    def _on_app_palette(self, _pal) -> None:
        try:
            self._restyle()
        except RuntimeError:                   # the panel is gone
            pass

    # ---- Building --------------------------------------------------------------
    def _build(self):
        out = []
        # Style: the cards.
        t = Tile("estilo", tr("Style"))
        self.custom = QLabel(tr("Custom"))
        self.custom.setObjectName("hint")
        t.head.addWidget(self.custom)
        cards = QGridLayout()
        cards.setSpacing(6)
        self.cards: dict = {}
        for i, (key, (label, _c)) in enumerate(ps.PRESETS.items()):
            b = Choice(None, tr(label), key)
            pm = QPixmap(str(THUMBS / f"{key}.png"))
            if not pm.isNull():
                pm.setDevicePixelRatio(2.0)
                b.setIcon(QIcon(pm))
                b.setIconSize(QSize(64, 44))
                b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.clicked.connect(lambda _c=False, k=key: self._preset(k))
            self.cards[key] = b
            cards.addWidget(b, i // 3, i % 3)
        t.body.addLayout(cards)
        self.reset_all_btn = QPushButton(tr("Reset all"))
        self.reset_all_btn.setObjectName("reset")
        self.reset_all_btn.setCursor(Qt.PointingHandCursor)
        self.reset_all_btn.setToolTip(tr("Every setting of the panel back to how it "
                                         "comes, as just installed"))
        self.reset_all_btn.clicked.connect(self.reset_all)
        t.body.addWidget(self.reset_all_btn)
        out.append((t, 2))

        # Line: a live sample, the hand, three chips.
        t = Tile("linea", tr("Line"))
        self.preview = LinePreview()
        t.body.addWidget(self.preview)
        self.hand = _slider(0, 100)
        self.hand.valueChanged.connect(lambda v: self._set("hand", v))
        t.body.addWidget(self.hand)
        scale = QHBoxLayout()
        for text, align in ((tr("Ruler"), Qt.AlignLeft), (tr("Hand"), Qt.AlignHCenter),
                            (tr("Loose"), Qt.AlignRight)):
            lab = QLabel(text)
            lab.setObjectName("scale")
            lab.setAlignment(align)
            scale.addWidget(lab, 1)
        t.body.addLayout(scale)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.toggles: dict = {}
        for key, icon, text in (("outlines", "contornos", tr("Outlines")),
                                ("twice", "repasar", tr("Twice")),
                                ("breaks", "cortes", tr("Breaks"))):
            chips.addWidget(self._toggle(key, icon, text))
        t.body.addLayout(chips)
        out.append((t, 2))

        # Technique.
        t = Tile("tecnica", tr("Technique"))
        self.technique = Segmented([("marker", "rotulador", tr("Marker")),
                                    ("watercolour", "acuarela", tr("Watercolour")),
                                    ("ink", "solo-tinta", tr("Ink only"))])
        self.technique.changed.connect(lambda v: self._set("technique", v))
        t.body.addWidget(self.technique)
        out.append((t, 2))

        # Light, and materials, side by side.
        light = Tile("luz", tr("Light"))
        self.light = Segmented([("classic", "luz-clasica", tr("Classic")),
                                ("sun", "luz-sol", tr("Sun"))])
        self.light.changed.connect(lambda v: self._set("light", v))
        light.body.addWidget(self.light)
        sh = self._toggle("shadows", "sombras", tr("Shadows"))
        sh.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        light.body.addWidget(sh)
        light.body.addStretch(1)
        mats = Tile("materiales", tr("Materials"))
        mgrid = QGridLayout()
        mgrid.setSpacing(4)
        self.materials: dict = {}
        labels = {"colour": tr("Colour"), "greys": tr("Greys"),
                  "contrast": tr("Contrast"), "none": tr("None")}
        for i, (key, colours) in enumerate(MATERIALS):
            b = Choice(None, labels[key], key)
            b._swatch = colours
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(40, 12))
            b.clicked.connect(lambda _c=False, k=key: self._set("materials", k))
            self.materials[key] = b
            mgrid.addWidget(b, i // 2, i % 2)
        mats.body.addLayout(mgrid)
        self.dry = Switch(tr("Dry brush"))
        self.dry.setToolTip(tr("High contrast: the black breaks up at its edges, "
                               "as a dry brush leaves it"))
        self.dry.toggled.connect(lambda v: self._set("ink_texture", v))
        mats.body.addWidget(self.dry)
        out.append(((light, mats), 1))

        # Hatching.
        t = Tile("rayado", tr("Hatching in the shade"))
        self.hatch_on = Switch()
        self.hatch_on.setToolTip(tr("Hatching in the shade (ink)"))
        self.hatch_on.toggled.connect(lambda v: self._set("hatching", v))
        t.head.addWidget(self.hatch_on)
        row = QHBoxLayout()
        self.hatch_dir = Segmented([(True, "rayado-caras", tr("Along the faces")),
                                    (False, "rayado-diagonal", tr("Diagonal"))])
        self.hatch_dir.changed.connect(lambda v: self._set("hatch_along", v))
        row.addWidget(self.hatch_dir, 2)
        turn = QVBoxLayout()
        turn.setSpacing(2)
        self.turn_icon = QLabel()
        self.turn_icon.setAlignment(Qt.AlignHCenter)
        self.turn = _slider(-90, 90)
        self.turn.valueChanged.connect(lambda v: self._set("hatch_turn", v))
        self.turn_label = QLabel()
        self.turn_label.setObjectName("scale")
        self.turn_label.setAlignment(Qt.AlignHCenter)
        turn.addWidget(self.turn_icon)
        turn.addWidget(self.turn)
        turn.addWidget(self.turn_label)
        row.addLayout(turn, 1)
        t.body.addLayout(row)
        out.append((t, 2))

        # Composition.
        t = Tile("composicion", tr("Composition"))
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for key, icon, text in (("unfinished", "bordes-libres", tr("Free edges")),
                                ("construction", "construccion", tr("Construction")),
                                ("ground", "suelo", tr("Ground"))):
            chips.addWidget(self._toggle(key, icon, text))
        t.body.addLayout(chips)
        out.append((t, 2))

        # Paper.
        t = Tile(None, tr("Paper"))
        pgrid = QGridLayout()
        pgrid.setSpacing(4)
        self.papers: dict = {}
        from . import paper as pp
        keys = list(pp.PAPERS) + ["custom"]
        for i, key in enumerate(keys):
            label = tr(pp.PAPERS[key][0]) if key in pp.PAPERS else tr("Your image…")
            b = Choice(None, label, key)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(40, 26))
            b.clicked.connect(lambda _c=False, k=key: self._pick_paper(k))
            self.papers[key] = b
            pgrid.addWidget(b, i // 4, i % 4)
        t.body.addLayout(pgrid)
        out.append((t, 2))

        # Fine settings, folded.
        t = Tile("ajustes", tr("Fine settings"))
        self.fold = QToolButton()
        self.fold.setObjectName("fold")
        self.fold.setCheckable(True)
        self.fold.setArrowType(Qt.RightArrow)
        self.fold.setToolTip(tr("Line weight, overshoot, offset, nib and intensity"))
        t.head.addWidget(self.fold)
        self.fine = QWidget()
        fl = QGridLayout(self.fine)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setHorizontalSpacing(8)
        fl.setVerticalSpacing(4)
        self.sliders: dict = {}
        for i, (key, text, lo, hi) in enumerate((
                ("weight", tr("Line weight"), 5, 40),
                ("overshoot", tr("Overshoot"), 0, 200),
                ("offset", tr("Off the lines"), 0, 40),
                ("nib", tr("Nib"), 10, 60),
                ("strength", tr("Intensity"), 20, 150))):
            lab = QLabel(text)
            lab.setObjectName("scale")
            sl = _slider(lo, hi)
            sl.valueChanged.connect(lambda v, k=key: self._set(k, v))
            self.sliders[key] = sl
            fl.addWidget(lab, i, 0)
            fl.addWidget(sl, i, 1)
        nat = Switch(tr("Natural variation"))
        nat.toggled.connect(lambda v: self._set("natural", v))
        self.toggles["natural"] = nat
        nat.setToolTip(tr("On: each area of colour or hatching gets its own slant, "
                          "as a hand never repeats one exactly. Off: all alike."))
        fl.addWidget(nat, 5, 0, 1, 2)
        self.reset_btn = QPushButton(tr("Reset fine settings"))
        self.reset_btn.setObjectName("reset")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setToolTip(tr("Back to the usual line weight, overshoot, "
                                     "offset, nib and intensity"))
        self.reset_btn.clicked.connect(self.reset_fine)
        fl.addWidget(self.reset_btn, 6, 0, 1, 2)
        self.fine.setVisible(False)
        t.body.addWidget(self.fine)
        self.fold.toggled.connect(self._unfold)
        t.title.mousePressEvent = lambda _e: self.fold.toggle()
        out.append((t, 2))

        # Size and the button that draws.
        t = Tile(None, "")
        t.title.hide()
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.size = Segmented([(w, None, label) for w, label in SIZES])
        self.size.setToolTip(tr("Drawing width: 1600, 2400 or 3600 px, or another size"))
        self.size.changed.connect(lambda v: self._set("size", v))
        bottom.addWidget(self.size, 1)
        self.draw_btn = QPushButton(tr("Draw the view"))
        self.draw_btn.setObjectName("draw")
        self.draw_btn.setCursor(Qt.PointingHandCursor)
        self.draw_btn.clicked.connect(self.draw)
        bottom.addWidget(self.draw_btn, 2)
        t.body.addLayout(bottom)
        from PySide6.QtWidgets import QComboBox, QSpinBox
        self.custom_box = QWidget()
        cl = QHBoxLayout(self.custom_box)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.fmt = QComboBox()
        for key, label in FORMATS:
            self.fmt.addItem(tr(label), key)
        self.fmt.currentIndexChanged.connect(
            lambda _i: self._set("custom_format", self.fmt.currentData()))
        self.px = QSpinBox()
        self.px.setRange(400, 12000)
        self.px.setSingleStep(100)
        self.px.setSuffix(" px")
        self.px.valueChanged.connect(lambda v: self._set("custom_width", v))
        self.dpi = QComboBox()
        for d in (150, 300):
            self.dpi.addItem(tr("{d} dpi", d=d), d)
        self.dpi.currentIndexChanged.connect(lambda _i: self._set("dpi", self.dpi.currentData()))
        cl.addWidget(self.fmt, 2)
        cl.addWidget(self.px, 1)
        cl.addWidget(self.dpi, 1)
        t.body.addWidget(self.custom_box)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        t.body.addWidget(self.status)
        out.append((t, 2))
        return out

    def _toggle(self, key: str, icon, text: str) -> Choice:
        b = Choice(icon, text, key)
        b.toggled.connect(lambda v, k=key: self._set(k, v))
        self.toggles[key] = b
        return b

    def _unfold(self, open_: bool) -> None:
        self.fine.setVisible(open_)
        self.fold.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)

    # ---- Theme -------------------------------------------------------------------
    def theme_palette(self) -> QPalette:
        """IngeTrazo's palette: the application's, which its theme switch
        sets (views/theme.py). The panel's own is changed by its stylesheet
        (a transparent background leaves its Window role transparent black),
        so it cannot be the source."""
        return QPalette(QApplication.palette())

    def _restyle(self) -> None:
        if self._styling:
            return
        self._styling = True
        try:
            pal = self.theme_palette()
            self.setStyleSheet(stylesheet(pal))
            for w in self.findChildren(QWidget):
                fn = getattr(w, "refresh_icons", None)
                if callable(fn):
                    fn()
            for sw in self.findChildren(Switch):
                sw.set_colours(pal)
            dpr = self.devicePixelRatioF()
            for b in self.materials.values():
                b.setIcon(QIcon(swatch_pixmap(b._swatch, 40, 12, dpr)))
            self._paper_icons(pal, dpr)
            self.turn_icon.setPixmap(icon_pixmap(
                "giro", 16, pal.color(QPalette.WindowText), dpr))
            acc = pal.color(QPalette.Highlight)
            on_acc = QColor("#ffffff" if acc.lightness() < 170 else "#111111")
            self.draw_btn.setIcon(QIcon(icon_pixmap("dibujar", 18, on_acc, dpr)))
            self.draw_btn.setIconSize(QSize(18, 18))
        finally:
            self._styling = False

    def _paper_icons(self, pal, dpr) -> None:
        from PySide6.QtGui import QPainter as _P, QPen
        from . import paper as pp
        from .drawing import to_qimage
        for key, b in self.papers.items():
            if key == "custom":
                pm = QPixmap(int(40 * dpr), int(26 * dpr))
                pm.fill(Qt.transparent)
                pm.setDevicePixelRatio(dpr)
                p = _P(pm)
                p.setRenderHint(_P.Antialiasing)
                c = QColor(pal.color(QPalette.WindowText))
                c.setAlpha(150)
                pen = QPen(c, 1.2, Qt.DashLine)
                p.setPen(pen)
                p.drawRoundedRect(1, 1, 38, 24, 4, 4)
                p.setPen(QPen(c, 1.6))
                p.drawLine(20, 8, 20, 18)
                p.drawLine(15, 13, 25, 13)
                p.end()
            else:
                sheet = pp.make(key, int(40 * dpr), int(26 * dpr), seed=3)
                pm = QPixmap.fromImage(to_qimage(sheet))
                pm.setDevicePixelRatio(dpr)
            b.setIcon(QIcon(pm))

    def _pick_paper(self, key: str) -> None:
        """A paper, or an image of your own (chosen each time, so it can be
        changed)."""
        if key == "custom":
            start = self.s.get("paper_image") or str(Path.home())
            path, _f = QFileDialog.getOpenFileName(
                self, tr("Choose an image for the paper"), start,
                tr("Images") + " (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
            if not path:
                self._show_state()                 # undo the chip's own check
                return
            self.s["paper_image"] = path
            self._write()
        self._set("paper", key)
        self._show_state()

    def changeEvent(self, ev) -> None:            # noqa: N802 (Qt)
        if ev.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            self._restyle()
        super().changeEvent(ev)

    # ---- Settings ------------------------------------------------------------------
    def _read(self) -> dict:
        return ps.clean(QSettings(*_SETTINGS).value("state", ""))

    def _write(self) -> None:
        QSettings(*_SETTINGS).setValue("state", json.dumps(self.s))

    def _preset(self, key: str) -> None:
        self.s = ps.apply_preset(self.s, key)
        self._write()
        self._show_state()

    def _set(self, key: str, value) -> None:
        if self._loading or self.s.get(key) == value:
            return
        self.s[key] = value
        self.s["preset"] = ps.matching_preset(self.s)
        self._write()
        self._show_state()

    FINE = ("weight", "overshoot", "offset", "nib", "strength", "natural")

    def reset_fine(self) -> None:
        """The fine settings back to their usual values; the rest is kept."""
        for key in self.FINE:
            self.s[key] = ps.DEFAULTS[key]
        self.s["preset"] = ps.matching_preset(self.s)
        self._write()
        self._show_state()

    def reset_all(self) -> None:
        """Every setting back to how the panel comes, as just installed."""
        self.s = dict(ps.DEFAULTS)
        self._write()
        self._show_state()

    def set(self, key: str, value) -> None:
        """Change one setting (as the controls do) and show it."""
        self._set(key, value)

    def _show_state(self) -> None:
        """Put the settings on the controls (without echoing back)."""
        s = self.s
        self._loading = True
        try:
            for key, b in self.cards.items():
                b.setChecked(s["preset"] == key)
            self.custom.setVisible(s["preset"] == "custom")
            self.hand.setValue(s["hand"])
            for key, b in self.toggles.items():
                b.setChecked(bool(s[key]))
            self.technique.set_value(s["technique"])
            self.light.set_value(s["light"])
            for key, b in self.materials.items():
                b.setChecked(s["materials"] == key)
            self.hatch_on.setChecked(s["hatching"])
            self.dry.setChecked(s["ink_texture"])
            self.hatch_dir.set_value(s["hatch_along"])
            self.turn.setValue(s["hatch_turn"])
            self.turn_label.setText(f"{tr('Turn')} {s['hatch_turn']}°")
            for key, sl in self.sliders.items():
                sl.setValue(s[key])
            self.size.set_value(s["size"])
            i = self.fmt.findData(s["custom_format"])
            self.fmt.setCurrentIndex(max(0, i))
            self.px.setValue(s["custom_width"])
            i = self.dpi.findData(s["dpi"])
            self.dpi.setCurrentIndex(max(0, i))
            for key, b in self.papers.items():
                b.setChecked(s["paper"] == key)
            img = s.get("paper_image") or ""
            self.papers["custom"].setToolTip(Path(img).name if img else
                                             tr("Choose an image of your own"))
        finally:
            self._loading = False
        fill = s["technique"] != "ink"
        for b in self.materials.values():
            b.setEnabled(fill)
        self.dry.setEnabled(fill and s["materials"] == "contrast")
        for key in ("offset", "strength"):
            self.sliders[key].setEnabled(fill)
        self.sliders["nib"].setEnabled(s["technique"] == "marker")
        self.toggles["natural"].setEnabled(fill or s["hatching"])
        shade = fill or s["hatching"]
        self.light.setEnabled(shade)
        self.toggles["shadows"].setEnabled(shade)
        self.hatch_dir.setEnabled(s["hatching"])
        self.turn.setEnabled(s["hatching"])
        custom = s["size"] == 0
        self.custom_box.setVisible(custom)
        self.px.setVisible(s["custom_format"] == "px")
        self.dpi.setVisible(s["custom_format"] != "px")
        self.preview.set_style(self.style())

    # ---- What the drawing is given -------------------------------------------------
    def style(self) -> st.LineStyle:
        return ps.line_style(self.s)

    def marker_style(self):
        return ps.marker_style(self.s)

    def composition(self):
        return ps.composition(self.s)

    # ---- Drawing ---------------------------------------------------------------
    def _say(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def draw(self) -> None:
        vp = self.app.viewport
        self._say(tr("Drawing…"))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            QApplication.processEvents()
            width, page = self.output_size(vp.camera)
            w, h = drawing.drawing_size(vp.camera, width)
            view = drawing.View(vp, w, h)
            if not len(view):
                self._say(tr("Nothing to draw: the view shows no lines."))
                return
            layers = drawing.render(vp, self.style(), w, view=view,
                                    marker=self.marker_style(),
                                    composition=self.composition(),
                                    paper_kind=self.s["paper"],
                                    paper_image=self.s["paper_image"], page=page)
        finally:
            QApplication.restoreOverrideCursor()
        self._say("")
        if self._window is None:
            self._window = SketchWindow(self.app)
        self._window.show_layers(layers, self.s["dpi"] if page else None)

    def output_size(self, camera) -> tuple:
        """``(drawing width, page or None)``: S/M/L, a width of your own, or
        a paper format (the drawing centred with a margin, the page turned
        to the drawing's shape)."""
        s = self.s
        if s["size"]:
            return int(s["size"]), None
        if s["custom_format"] == "px":
            return int(s["custom_width"]), None
        aspect = max(camera.aspect, 1e-6)
        pw, ph = drawing.page_size(s["custom_format"], int(s["dpi"]), aspect >= 1.0)
        avail_w, avail_h = pw * (1 - 2 * PAGE_MARGIN), ph * (1 - 2 * PAGE_MARGIN)
        width = int(min(avail_w, avail_h * aspect))
        return width, (pw, ph)


class SketchWindow(QDialog):
    """The drawing, fitted to the window; saved (PNG, SVG in layers, PDF)
    or copied from here."""

    def __init__(self, app) -> None:
        super().__init__(app.window)
        self.app = app
        self.setWindowTitle("Croquis")
        self.setModal(False)
        self.resize(1000, 760)
        self._img = None
        self._layers = None
        self._dpi = None
        lay = QVBoxLayout(self)
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.view)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.note = QLabel("")
        row.addWidget(self.note, 1)
        for icon, text, fn in (("guardar", tr("Save as…"), self.save),
                               ("copiar", tr("Copy"), self.copy),
                               (None, tr("Close"), self.close)):
            b = QPushButton(text)
            if icon:
                b.setIcon(themed_icon(b, icon, 20))
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

    def show_layers(self, layers, dpi=None) -> None:
        self._layers = layers
        self._dpi = dpi
        self.show_image(layers.image())

    def show_image(self, img) -> None:
        self._img = img
        self.note.setText(f"{img.width()} × {img.height()} px")
        self._fit()
        self.show()
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, ev) -> None:          # noqa: N802 (Qt)
        super().resizeEvent(ev)
        self._fit()

    def _fit(self) -> None:
        if self._img is None:
            return
        pm = QPixmap.fromImage(self._img)
        size = self.view.size()
        if size.width() > 10 and size.height() > 10:
            pm = pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.view.setPixmap(pm)

    def _default_path(self) -> str:
        win = self.app.window
        doc = getattr(win, "current_path", None) or getattr(win, "_current_path", None)
        if doc:
            p = Path(str(doc))
            return str(p.with_name(p.stem + "-croquis.png"))
        return str(Path.home() / "croquis.png")

    FILTERS = ("PNG (*.png)", "SVG (*.svg)", "PDF (*.pdf)")

    def save(self) -> None:
        if self._img is None:
            return
        path, chosen = QFileDialog.getSaveFileName(
            self, tr("Save the sketch"), self._default_path(), ";;".join(self.FILTERS))
        if not path:
            return
        ext = {"PNG": ".png", "SVG": ".svg", "PDF": ".pdf"}.get(chosen[:3], ".png")
        if not path.lower().endswith((".png", ".svg", ".pdf")):
            path += ext
        self.save_to(path)

    def save_to(self, path: str) -> bool:
        from . import export
        if self._layers is not None:
            if path.lower().endswith(".pdf") and self._dpi:
                ok = export.save_pdf(self._layers, path, self._dpi)
            else:
                ok = export.save(self._layers, path)
        else:
            ok = self._img.save(path, "PNG")
        self.note.setText(tr("Saved: {path}", path=path) if ok
                          else tr("Could not save {path}", path=path))
        return ok

    def copy(self) -> None:
        if self._img is not None:
            QGuiApplication.clipboard().setImage(self._img)
            self.note.setText(tr("Copied to the clipboard"))
