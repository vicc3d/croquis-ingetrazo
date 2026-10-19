# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The «Croquis» tab of the side tray, and the window the drawing opens in."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from . import drawing
from .compose import Composition
from .marker import MarkerStyle
from .strokes import LineStyle
from .texts import tr

SIZES = (1600, 2400, 3600)
_SETTINGS = ("ingetrazo-croquis", "croquis")


def _slider(lo: int, hi: int, value: int) -> QSlider:
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(value)
    s.setMinimumWidth(60)
    return s


class CroquisPanel(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._window = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        hint = QLabel(tr("Draws what the viewport shows, as a freehand sketch "
                         "on paper. Frame the view first."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        title = QLabel(f"<b>{tr('Line')}</b>")
        lay.addWidget(title)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        d = LineStyle()
        self.hand = _slider(0, 100, int(d.hand * 100))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Ruler")))
        row.addWidget(self.hand, 1)
        row.addWidget(QLabel(tr("Loose")))
        form.addRow(tr("Hand"), row)
        self.weight = _slider(5, 40, int(d.width * 10))
        form.addRow(tr("Line weight"), self.weight)
        self.overshoot = _slider(0, 200, int(d.overshoot * 100))
        form.addRow(tr("Overshoot"), self.overshoot)
        lay.addLayout(form)
        self.outlines = QCheckBox(tr("Heavier outlines"))
        self.outlines.setChecked(True)
        self.twice = QCheckBox(tr("Draw lines twice"))
        self.twice.setChecked(d.double_stroke)
        self.breaks = QCheckBox(tr("Lift the pen on long lines"))
        self.breaks.setChecked(d.breaks)
        for w in (self.outlines, self.twice, self.breaks):
            lay.addWidget(w)

        lay.addWidget(QLabel(f"<b>{tr('Colour and shade')}</b>"))
        m = MarkerStyle()
        self.marker_on = QCheckBox(tr("Colour, light and shade"))
        self.marker_on.setChecked(m.enabled)
        lay.addWidget(self.marker_on)
        mform = QFormLayout()
        mform.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.medium = QComboBox()
        self.medium.addItem(tr("Marker"), "marker")
        self.medium.addItem(tr("Watercolour"), "watercolour")
        mform.addRow(tr("Technique"), self.medium)
        self.light = QComboBox()
        self.light.addItem(tr("Classic, from the upper left"), "classic")
        self.light.addItem(tr("The model's sun (Shadows panel)"), "sun")
        mform.addRow(tr("Light"), self.light)
        self.offset = _slider(0, 40, int(m.offset))
        mform.addRow(tr("Off the lines"), self.offset)
        self.nib = _slider(10, 60, int(m.width))
        mform.addRow(tr("Nib"), self.nib)
        self.strength = _slider(20, 150, int(m.strength * 100))
        mform.addRow(tr("Intensity"), self.strength)
        lay.addLayout(mform)
        self.shadows = QCheckBox(tr("Cast shadows"))
        self.shadows.setChecked(m.shadows)
        self.colour = QComboBox()
        for key, text in (("colour", tr("Colour")), ("greys", tr("Greys")),
                          ("contrast", tr("High contrast")), ("none", tr("Light and shade only"))):
            self.colour.addItem(text, key)
        cform = QFormLayout()
        cform.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        cform.addRow(tr("Materials"), self.colour)
        self.natural = QCheckBox(tr("Natural variation (each area its own hand)"))
        self.natural.setChecked(m.natural)
        self.hatching = QCheckBox(tr("Hatching in the shade (ink)"))
        self.hatching.setChecked(m.hatching)
        self.hatch_dir = QComboBox()
        self.hatch_dir.addItem(tr("Along the faces"), True)
        self.hatch_dir.addItem(tr("Diagonal"), False)
        self.hatch_turn = _slider(-90, 90, int(m.hatch_turn))
        hform = QFormLayout()
        hform.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        hform.addRow(tr("Direction"), self.hatch_dir)
        hform.addRow(tr("Turn"), self.hatch_turn)
        lay.addLayout(cform)
        lay.addWidget(self.shadows)
        lay.addWidget(self.natural)
        lay.addWidget(self.hatching)
        lay.addLayout(hform)
        self.marker_on.toggled.connect(self._enable_marker)
        self.hatching.toggled.connect(self._enable_marker)
        self.medium.currentIndexChanged.connect(self._enable_marker)

        lay.addWidget(QLabel(f"<b>{tr('Composition')}</b>"))
        c = Composition()
        self.unfinished = QCheckBox(tr("Unfinished edges (colour fades out)"))
        self.unfinished.setChecked(c.unfinished)
        self.construction = QCheckBox(tr("Construction lines"))
        self.construction.setChecked(c.construction)
        self.ground = QCheckBox(tr("Ground strokes"))
        self.ground.setChecked(c.ground)
        for w in (self.unfinished, self.construction, self.ground):
            lay.addWidget(w)

        size_row = QFormLayout()
        self.size = QComboBox()
        for w in SIZES:
            self.size.addItem(tr("{w} px wide", w=w), w)
        size_row.addRow(tr("Size"), self.size)
        lay.addLayout(size_row)

        self.draw_btn = QPushButton(tr("Draw the view"))
        self.draw_btn.setDefault(True)
        self.draw_btn.clicked.connect(self.draw)
        lay.addWidget(self.draw_btn)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)
        self._load()
        for w in (self.hand, self.weight, self.overshoot, self.offset,
                  self.nib, self.strength):
            w.valueChanged.connect(self._save)
        for w in (self.outlines, self.twice, self.breaks, self.marker_on,
                  self.shadows, self.natural, self.hatching, self.unfinished,
                  self.construction, self.ground):
            w.toggled.connect(self._save)
        for w in (self.size, self.light, self.medium, self.colour, self.hatch_dir):
            w.currentIndexChanged.connect(self._save)
        self.hatch_turn.valueChanged.connect(self._save)
        self.hatching.toggled.connect(self._enable_marker)
        self._enable_marker()

    def _enable_marker(self, *_a) -> None:
        fill = self.marker_on.isChecked()
        shade = fill or self.hatching.isChecked()
        for w in (self.medium, self.offset, self.strength, self.colour, self.natural):
            w.setEnabled(fill)
        self.nib.setEnabled(fill and self.medium.currentData() == "marker")
        for w in (self.light, self.shadows):
            w.setEnabled(shade)
        for w in (self.hatch_dir, self.hatch_turn):
            w.setEnabled(self.hatching.isChecked())

    # ---- Settings (per user, not in the document) ---------------------------
    def _load(self) -> None:
        q = QSettings(*_SETTINGS)

        def num(key, default):
            try:
                return int(q.value(key, default))
            except (TypeError, ValueError):
                return default

        def flag(key, default):
            v = q.value(key, default)
            return v in (True, "true", "1", 1) if not isinstance(v, bool) else v

        self.hand.setValue(num("line/hand", self.hand.value()))
        self.weight.setValue(num("line/weight", self.weight.value()))
        self.overshoot.setValue(num("line/overshoot", self.overshoot.value()))
        self.outlines.setChecked(flag("line/outlines", True))
        self.twice.setChecked(flag("line/twice", self.twice.isChecked()))
        self.breaks.setChecked(flag("line/breaks", self.breaks.isChecked()))
        i = self.size.findData(num("size", SIZES[0]))
        self.size.setCurrentIndex(max(0, i))
        self.marker_on.setChecked(flag("marker/on", self.marker_on.isChecked()))
        i = self.light.findData(q.value("marker/light", "classic"))
        self.light.setCurrentIndex(max(0, i))
        self.offset.setValue(num("marker/offset", self.offset.value()))
        self.nib.setValue(num("marker/nib", self.nib.value()))
        self.strength.setValue(num("marker/strength", self.strength.value()))
        self.shadows.setChecked(flag("marker/shadows", self.shadows.isChecked()))
        i = self.colour.findData(q.value("marker/colour_mode", "colour"))
        self.colour.setCurrentIndex(max(0, i))
        self.natural.setChecked(flag("marker/natural", self.natural.isChecked()))
        i = self.hatch_dir.findData(flag("marker/hatch_along", True))
        self.hatch_dir.setCurrentIndex(max(0, i))
        self.hatch_turn.setValue(num("marker/hatch_turn", 0))
        self.hatching.setChecked(flag("marker/hatching", self.hatching.isChecked()))
        i = self.medium.findData(q.value("marker/medium", "marker"))
        self.medium.setCurrentIndex(max(0, i))
        self.unfinished.setChecked(flag("compose/unfinished", self.unfinished.isChecked()))
        self.construction.setChecked(flag("compose/construction", self.construction.isChecked()))
        self.ground.setChecked(flag("compose/ground", self.ground.isChecked()))

    def _save(self, *_a) -> None:
        q = QSettings(*_SETTINGS)
        q.setValue("line/hand", self.hand.value())
        q.setValue("line/weight", self.weight.value())
        q.setValue("line/overshoot", self.overshoot.value())
        q.setValue("line/outlines", self.outlines.isChecked())
        q.setValue("line/twice", self.twice.isChecked())
        q.setValue("line/breaks", self.breaks.isChecked())
        q.setValue("size", self.size.currentData())
        q.setValue("marker/on", self.marker_on.isChecked())
        q.setValue("marker/light", self.light.currentData())
        q.setValue("marker/offset", self.offset.value())
        q.setValue("marker/nib", self.nib.value())
        q.setValue("marker/strength", self.strength.value())
        q.setValue("marker/shadows", self.shadows.isChecked())
        q.setValue("marker/colour_mode", self.colour.currentData())
        q.setValue("marker/natural", self.natural.isChecked())
        q.setValue("marker/hatch_along", self.hatch_dir.currentData())
        q.setValue("marker/hatch_turn", self.hatch_turn.value())
        q.setValue("marker/hatching", self.hatching.isChecked())
        q.setValue("marker/medium", self.medium.currentData())
        q.setValue("compose/unfinished", self.unfinished.isChecked())
        q.setValue("compose/construction", self.construction.isChecked())
        q.setValue("compose/ground", self.ground.isChecked())

    def style(self) -> LineStyle:
        return LineStyle(
            hand=self.hand.value() / 100.0,
            width=self.weight.value() / 10.0,
            profile_scale=2.0 if self.outlines.isChecked() else 1.0,
            overshoot=self.overshoot.value() / 100.0,
            double_stroke=self.twice.isChecked(),
            breaks=self.breaks.isChecked())

    def composition(self) -> Composition:
        return Composition(unfinished=self.unfinished.isChecked(),
                           construction=self.construction.isChecked(),
                           ground=self.ground.isChecked())

    def marker_style(self) -> MarkerStyle:
        return MarkerStyle(
            enabled=self.marker_on.isChecked(),
            light=self.light.currentData(),
            offset=float(self.offset.value()),
            width=float(self.nib.value()),
            strength=self.strength.value() / 100.0,
            shadows=self.shadows.isChecked(),
            colour=True,
            colour_mode=self.colour.currentData(),
            natural=self.natural.isChecked(),
            hatch_along=bool(self.hatch_dir.currentData()),
            hatch_turn=float(self.hatch_turn.value()),
            medium=self.medium.currentData(),
            hatching=self.hatching.isChecked())

    # ---- Drawing ---------------------------------------------------------------
    def draw(self) -> None:
        vp = self.app.viewport
        self.status.setText(tr("Drawing…"))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            QApplication.processEvents()
            w, h = drawing.drawing_size(vp.camera, int(self.size.currentData()))
            view = drawing.View(vp, w, h)
            if not len(view):
                self.status.setText(tr("Nothing to draw: the view shows no lines."))
                return
            img = drawing.sketch(vp, self.style(), w, view=view,
                                 marker=self.marker_style(),
                                 composition=self.composition())
        finally:
            QApplication.restoreOverrideCursor()
        self.status.setText("")
        if self._window is None:
            self._window = SketchWindow(self.app)
        self._window.show_image(img)


class SketchWindow(QDialog):
    """The drawing, fitted to the window; saved or copied from here."""

    def __init__(self, app) -> None:
        super().__init__(app.window)
        self.app = app
        self.setWindowTitle("Croquis")
        self.setModal(False)
        self.resize(1000, 760)
        self._img = None
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
        for text, fn in ((tr("Save PNG…"), self.save), (tr("Copy"), self.copy),
                         (tr("Close"), self.close)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

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

    def save(self) -> None:
        if self._img is None:
            return
        path, _f = QFileDialog.getSaveFileName(
            self, tr("Save the sketch"), self._default_path(), "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        ok = self._img.save(path, "PNG")
        self.note.setText(tr("Saved: {path}", path=path) if ok
                          else tr("Could not save {path}", path=path))

    def copy(self) -> None:
        if self._img is not None:
            QGuiApplication.clipboard().setImage(self._img)
            self.note.setText(tr("Copied to the clipboard"))
