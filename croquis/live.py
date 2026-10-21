# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The live preview: the sketch over the viewport, almost live.

While the camera moves, the model shows as usual. Once it has been still
for a moment, the view is drawn as a sketch, at the viewport's own size, in
the background (IngeTrazo does not freeze), and laid over the viewport. A
move of the camera, a change to the model or to the panel's settings, and
the sketch steps aside until the view is still again; a drawing the camera
has moved away from meanwhile is thrown away.

What a drawing needs from the viewport (its geometry, the faces' colours,
the camera) is read on the main thread, in a few tens of milliseconds; the
drawing itself runs on a worker thread, on that frozen copy.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QVector3D

#: How long the view must be still before it is drawn, in milliseconds.
SETTLE_MS = 500
#: How often the camera is looked at, in milliseconds.
POLL_MS = 120


def _copy_camera(cam):
    """A camera of its own, so the drawing does not follow the view."""
    new = type(cam).__new__(type(cam))
    for k, v in cam.__dict__.items():
        setattr(new, k, QVector3D(v) if isinstance(v, QVector3D) else v)
    return new


class _Frozen:
    """What the drawing reads from a viewport, read once on the main
    thread: the camera (a copy), the scene, the geometry, the colours."""

    def __init__(self, viewport, colours) -> None:
        self.camera = _copy_camera(viewport.camera)
        self.scene = viewport.scene
        self._geom = viewport.hlr_geometry()
        self.croquis_colours = colours
        self.DEFAULT_FACE_COLOR = getattr(viewport, "DEFAULT_FACE_COLOR",
                                          (0.96, 0.95, 0.925))
        self._w, self._h = viewport.width(), viewport.height()

    def hlr_geometry(self):
        return self._geom

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h


class LivePreview(QObject):
    """Watches the view and keeps a sketch of it, drawn over the viewport
    by :meth:`paint` (an overlay)."""

    def __init__(self, app, panel) -> None:
        super().__init__(panel)
        self.app = app
        self.panel = panel
        self.enabled = False
        self.image = None             # the sketch, and the view it is of
        self.image_key = None
        self.pending = None           # (future, key) of a drawing under way
        self._seen = None             # the view as last looked at
        self._still_since = 0
        self._pool = ThreadPoolExecutor(max_workers=1)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._tick)
        self._clock = 0

    # ---- On and off ------------------------------------------------------------
    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        self.image = self.image_key = None
        self._seen = None
        if self.enabled:
            self.timer.start()
        else:
            self.timer.stop()
        self.app.viewport.update()

    def shutdown(self) -> None:
        self.timer.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- Watching the view -------------------------------------------------------
    def view_key(self) -> str:
        """Everything a sketch of the view depends on: the camera, the
        viewport's size, the model's version and the panel's settings."""
        vp = self.app.viewport
        cam = vp.camera
        parts = [cam.eye().toTuple(), cam.target.toTuple(), cam.fov_deg,
                 bool(cam.perspective), bool(getattr(cam, "two_point", False)),
                 vp.width(), vp.height(), getattr(vp.scene, "version", 0),
                 json.dumps(self.panel.s, sort_keys=True)]
        return repr(parts)

    def _tick(self) -> None:
        self._clock += POLL_MS
        key = self.view_key()
        if key != self._seen:
            self._seen = key
            self._still_since = self._clock
            if self.image_key != key and self.image is not None:
                self.app.viewport.update()          # step aside while moving
            return
        if self.image_key == key:
            return
        if self.pending is not None:
            future, pkey = self.pending
            if not future.done():
                return
            self.pending = None
            try:
                img = future.result()
            except Exception:                         # noqa: BLE001
                import logging
                logging.getLogger("ingetrazo.plugins").warning(
                    "croquis: the live preview failed", exc_info=True)
                img = None
            if pkey == key and img is not None:
                self.image, self.image_key = img, key
                self.app.viewport.update()
            return
        if self._clock - self._still_since >= SETTLE_MS:
            try:
                self._start(key)
            except Exception:                         # noqa: BLE001
                # Not again for this view: the timer would retry it, and
                # log it, every tick.
                import logging
                logging.getLogger("ingetrazo.plugins").warning(
                    "croquis: the live preview could not start", exc_info=True)
                self.image, self.image_key = None, key
                self.app.viewport.update()

    def _start(self, key: str) -> None:
        from . import palette as pal
        vp = self.app.viewport
        frozen = _Frozen(vp, pal.triangle_colours(vp))
        p = self.panel
        style, marker, comp = p.style(), p.marker_style(), p.composition()
        kind, image = p.s["paper"], p.s["paper_image"]
        dpr = vp.devicePixelRatioF()
        width = max(200, int(vp.width() * min(dpr, 1.5)))

        def job():
            from . import drawing
            return drawing.sketch(frozen, style, width, marker=marker,
                                  composition=comp, paper_kind=kind,
                                  paper_image=image)

        self.pending = (self._pool.submit(job), key)
        vp.update()                                     # «drawing…»

    # ---- Over the viewport --------------------------------------------------------
    def paint(self, viewport, painter: QPainter) -> None:
        if not self.enabled:
            return
        w, h = viewport.width(), viewport.height()
        from PySide6.QtGui import QGuiApplication
        # While a button is held (drawing, moving), the model shows: what
        # the tool does must be seen.
        pressed = QGuiApplication.mouseButtons() != Qt.NoButton
        current = (self.image is not None and self.image_key == self._seen
                   and not pressed)
        if current:
            painter.drawImage(QRectF(0, 0, w, h), self.image)
        # A small badge: what is shown, or that it is being drawn.
        from .texts import tr
        drawing_now = self.pending is not None and not self.pending[0].done()
        text = tr("Croquis: drawing…") if drawing_now else (
            tr("Croquis live · right-click to save") if current
            else tr("Croquis: hold the view still"))
        f = QFont(painter.font())
        f.setPixelSize(12)
        painter.setFont(f)
        tw = painter.fontMetrics().horizontalAdvance(text) + 20
        r = QRectF(w - tw - 12, h - 34, tw, 22)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillPath(path, QColor(29, 26, 23, 200))
        painter.setPen(QColor(247, 243, 234))
        painter.drawText(r, int(Qt.AlignCenter), text)
