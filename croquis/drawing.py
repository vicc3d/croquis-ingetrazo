# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The view of the model as a freehand drawing on paper.

The lines are the visible parts of the model's edges in the camera's own
projection (perspective, two-point or parallel), found on a depth buffer by
:mod:`.visibility`; pieces that continue each other in a straight line are
joined, so a wall's edge is one stroke. :mod:`.strokes` turns them into ink,
outlines heavier, and they are laid on a sheet of paper.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

from . import strokes as st
from . import visibility as vis

PAPER = (247, 243, 234)          # a warm, slightly cream sheet
INK = (29, 26, 23)               # not black: a warm dark ink
#: The depth buffer is never wider than this (and the lines are scaled up
#: from it): enough for a sketch, and quick.
MAX_BUFFER_WIDTH = 2000


def view_lines(viewport, width: int, height: int):
    """``(segs, outline)`` of the current view in drawing pixels: segs
    (N, 4), outline (N,) bools."""
    cam = viewport.camera
    scale = min(1.0, MAX_BUFFER_WIDTH / max(1, width))
    bw, bh = max(1, int(round(width * scale))), max(1, int(round(height * scale)))
    geom = viewport.hlr_geometry()
    segs, outline = vis.visible_lines(geom, cam, bw, bh)
    segs, outline = vis.merge_collinear(segs, outline, tol=1.5)
    return segs / scale, outline


def paper(width: int, height: int, seed: int = 7) -> QImage:
    """A sheet of paper: the paper tone with a soft grain."""
    rng = np.random.default_rng(seed)
    gh, gw = max(2, height // 3 + 1), max(2, width // 3 + 1)
    grain = rng.normal(0.0, 1.0, (gh, gw))
    pad = np.pad(grain, 1, mode="edge")
    grain = sum(pad[i:i + gh, j:j + gw] for i in range(3) for j in range(3)) / 9.0
    grain = np.kron(grain, np.ones((3, 3)))[:height, :width]
    tone = 1.0 + 0.035 * grain
    rgb = np.clip(np.array(PAPER, dtype=np.float64)[None, None, :]
                  * tone[:, :, None], 0, 255).astype(np.uint8)
    rgba = np.ascontiguousarray(
        np.dstack([rgb, np.full((height, width), 255, dtype=np.uint8)]))
    img = QImage(rgba.tobytes(), width, height, width * 4, QImage.Format_RGBA8888)
    return img.convertToFormat(QImage.Format_ARGB32_Premultiplied)


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


def sketch(viewport, style: st.LineStyle, width: int, lines=None) -> QImage:
    """The current view as a freehand line drawing, ``width`` pixels wide
    (the height follows the view). ``lines`` = :func:`view_lines`' answer,
    when the caller already has it."""
    width, height = drawing_size(viewport.camera, width)
    segs, outline = lines if lines is not None else view_lines(viewport, width, height)
    kinds = outline if style.profile_scale != 1.0 else None
    img = paper(width, height)
    draw_strokes(img, st.strokes_for(segs, kinds, style, height))
    return img
