# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The view of the model as a freehand drawing on paper.

One depth buffer of the view (:mod:`.visibility`) gives everything: the
visible parts of the edges, which become ink strokes (:mod:`.strokes`,
outlines heavier, straight runs joined into one stroke), and the face seen
at every pixel, which gets its value in grey marker (:mod:`.marker`). The
layers go down as on paper: the sheet, the marker, the ink.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

from . import marker as mk
from . import palette as pal
from . import shadow as sh
from . import strokes as st
from . import visibility as vis

PAPER = (247, 243, 234)          # a warm, slightly cream sheet
INK = (29, 26, 23)               # not black: a warm dark ink
#: The depth buffer is never wider than this (lines and fills are scaled up
#: from it): enough for a sketch, and quick.
MAX_BUFFER_WIDTH = 2000


class View:
    """What one view of the model gives the drawing, at the buffer's size
    (``scale`` = buffer pixels per drawing pixel)."""

    def __init__(self, viewport, width: int, height: int) -> None:
        cam = viewport.camera
        self.width, self.height = width, height
        self.scale = min(1.0, MAX_BUFFER_WIDTH / max(1, width))
        self.bw = max(1, int(round(width * self.scale)))
        self.bh = max(1, int(round(height * self.scale)))
        self.camera = cam
        self.scene = viewport.scene
        self.geom = viewport.hlr_geometry()
        coloured = pal.triangle_colours(viewport)
        if coloured is not None:
            self.tris, self.colour = coloured
        else:
            self.tris = np.asarray(self.geom[0], dtype=np.float64).reshape(-1, 3, 3)
            self.colour = None
        self.M = vis.clip_matrix(cam)
        self.zbuf, self.index = vis.depth_buffer(self.tris, self.M, self.bw,
                                                 self.bh, bool(cam.perspective))
        segs, outline = vis.visible_lines(self.geom, cam, self.bw, self.bh,
                                          zbuf=self.zbuf)
        segs, outline = vis.merge_collinear(segs, outline, tol=1.5)
        self.segs = segs / self.scale
        self.outline = outline

    def __len__(self) -> int:
        return len(self.segs)


def paper(width: int, height: int, seed: int = 7) -> np.ndarray:
    """A sheet of paper, (H, W, 3) floats: the paper tone, soft grain."""
    rng = np.random.default_rng(seed)
    gh, gw = max(2, height // 3 + 1), max(2, width // 3 + 1)
    grain = rng.normal(0.0, 1.0, (gh, gw))
    pad = np.pad(grain, 1, mode="edge")
    grain = sum(pad[i:i + gh, j:j + gw] for i in range(3) for j in range(3)) / 9.0
    grain = np.kron(grain, np.ones((3, 3)))[:height, :width]
    tone = 1.0 + 0.035 * grain
    return np.array(PAPER, dtype=np.float64)[None, None, :] * tone[:, :, None]


def to_qimage(rgb: np.ndarray) -> QImage:
    h, w = rgb.shape[:2]
    a = np.ascontiguousarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8),
                                        np.full((h, w), 255, dtype=np.uint8)]))
    img = QImage(a.tobytes(), w, h, w * 4, QImage.Format_RGBA8888)
    return img.convertToFormat(QImage.Format_ARGB32_Premultiplied)


def _resize(rgb: np.ndarray, width: int, height: int) -> np.ndarray:
    """Smoothly scale an (h, w, 3) float image."""
    if rgb.shape[1] == width and rgb.shape[0] == height:
        return rgb
    img = to_qimage(rgb).scaled(width, height, Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_RGBA8888)
    a = np.frombuffer(img.constBits(), dtype=np.uint8,
                      count=img.bytesPerLine() * height)
    return a.reshape(height, img.bytesPerLine())[:, :width * 4].reshape(
        height, width, 4)[:, :, :3].astype(np.float64)


def marker_layer(view: View, style: mk.MarkerStyle) -> np.ndarray:
    """The marker's effect, (H, W, 3) factors to multiply the paper by."""
    light = mk.light_direction(view.camera, view.scene, style.light)
    values, plane, normals, plane_of = mk.face_values(view.index, view.tris,
                                                      view.camera, light)
    if style.shadows:
        cast = sh.cast_shadow(view, normals, light)
        values = np.where(cast & (values >= 0), 3, values).astype(np.int8)
    colour = None
    if style.colour and view.colour is not None:
        colour = np.where(view.index >= 0,
                          view.colour[np.clip(view.index, 0, None)], -1)
    n_planes = int(plane_of.max()) + 1 if len(plane_of) else 0
    angles = mk.stroke_angles(normals, plane_of, n_planes, view.camera,
                              view.M, view.bw, view.bh)
    ones = np.full((view.bh, view.bw, 3), 255.0)
    factor = mk.paint(ones, values, plane, angles, style,
                      view.bh / st.REFERENCE_HEIGHT, colour=colour)
    return _resize(factor, view.width, view.height) / 255.0


def draw_strokes(img: QImage, strokes: list, ink=INK) -> None:
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    for s in strokes:
        alpha = int(255 * max(0.0, min(1.0, s.opacity)))
        p.setBrush(QColor(ink[0], ink[1], ink[2], alpha))
        p.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in s.outline]))
    p.end()


def drawing_size(camera, width: int) -> tuple:
    return width, max(1, int(round(width / max(camera.aspect, 1e-6))))


def sketch(viewport, style: st.LineStyle, width: int, view: View | None = None,
           marker: mk.MarkerStyle | None = None) -> QImage:
    """The current view as a freehand drawing, ``width`` pixels wide (the
    height follows the view): paper, grey marker (``marker``, if on), ink.
    ``view``: a :class:`View` the caller already made."""
    width, height = drawing_size(viewport.camera, width)
    view = view if view is not None else View(viewport, width, height)
    sheet = paper(width, height)
    if marker is not None and marker.enabled and len(view.tris):
        sheet = sheet * marker_layer(view, marker)
    img = to_qimage(sheet)
    kinds = view.outline if style.profile_scale != 1.0 else None
    draw_strokes(img, st.strokes_for(view.segs, kinds, style, height))
    return img
