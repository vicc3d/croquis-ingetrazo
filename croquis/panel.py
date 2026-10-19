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
        for w in (self.hand, self.weight, self.overshoot):
            w.valueChanged.connect(self._save)
        for w in (self.outlines, self.twice, self.breaks):
            w.toggled.connect(self._save)
        self.size.currentIndexChanged.connect(self._save)

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

    def _save(self, *_a) -> None:
        q = QSettings(*_SETTINGS)
        q.setValue("line/hand", self.hand.value())
        q.setValue("line/weight", self.weight.value())
        q.setValue("line/overshoot", self.overshoot.value())
        q.setValue("line/outlines", self.outlines.isChecked())
        q.setValue("line/twice", self.twice.isChecked())
        q.setValue("line/breaks", self.breaks.isChecked())
        q.setValue("size", self.size.currentData())

    def style(self) -> LineStyle:
        return LineStyle(
            hand=self.hand.value() / 100.0,
            width=self.weight.value() / 10.0,
            profile_scale=2.0 if self.outlines.isChecked() else 1.0,
            overshoot=self.overshoot.value() / 100.0,
            double_stroke=self.twice.isChecked(),
            breaks=self.breaks.isChecked())

    # ---- Drawing ---------------------------------------------------------------
    def draw(self) -> None:
        vp = self.app.viewport
        self.status.setText(tr("Drawing…"))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            QApplication.processEvents()
            w, h = drawing.drawing_size(vp.camera, int(self.size.currentData()))
            lines = drawing.view_lines(vp, w, h)
            if not len(lines[0]):
                self.status.setText(tr("Nothing to draw: the view shows no lines."))
                return
            img = drawing.sketch(vp, self.style(), w, lines=lines)
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
