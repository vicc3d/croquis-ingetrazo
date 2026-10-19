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

from . import compose as cp
from . import hatch
from . import ink
from . import marker as mk
from . import palette as pal
from . import shadow as sh
from . import strokes as st
from . import visibility as vis
from . import watercolour as wc

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
            self.tris, self.colour, self.tone = coloured
        else:
            self.tris = np.asarray(self.geom[0], dtype=np.float64).reshape(-1, 3, 3)
            self.colour = self.tone = None
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


def shade_maps(view: View, style: mk.MarkerStyle) -> dict:
    """What the light does to the view, at the buffer's size: ``values``
    (0 lit, 1 turned, 2 away, 3 cast shadow, -1 nothing; the shadows on
    the ground under the model too), ``plane`` ids (the ground's is the
    last), ``angles`` of the strokes per plane, ``jitter`` per plane (a
    natural hand, or zeros), ``colour`` (a marker per pixel, or None) and
    ``tone`` (the material's lightness per pixel, or None)."""
    light = mk.light_direction(view.camera, view.scene, style.light)
    values, plane, normals, plane_of = mk.face_values(view.index, view.tris,
                                                      view.camera, light)
    n_planes = int(plane_of.max()) + 1 if len(plane_of) else 0
    if style.shadows and len(view.tris):
        pack = sh.shadow_map(view.tris, light)
        cast = sh.cast_shadow(view, normals, light, pack)
        values = np.where(cast & (values >= 0), 3, values).astype(np.int8)
        ground = sh.ground_shadow(view, light, pack=pack)
        values = np.where(ground, 3, values).astype(np.int8)
        plane = np.where(ground, n_planes, plane)
    colour = tone = None
    model = view.index >= 0
    ix = np.clip(view.index, 0, None)
    if view.colour is not None:
        colour = np.where(model, view.colour[ix], -1)
    if view.tone is not None:
        tone = np.where(model, view.tone[ix], -1.0)
    angles = mk.stroke_angles(normals, plane_of, n_planes, view.camera,
                              view.M, view.bw, view.bh)
    angles = np.r_[angles[:n_planes],
                   mk.level_angle(view.camera, view.M, view.bw, view.bh)]
    # Long, narrow areas (boards, slats): along their length.
    angles = mk.long_axis_angles(np.where(plane < n_planes, plane, -1), angles)
    if style.natural:
        rng = np.random.default_rng(97)
        jitter = rng.normal(0.0, 0.14, len(angles))
    else:
        jitter = np.zeros(len(angles))
    return {"values": values, "plane": plane, "angles": angles,
            "jitter": jitter, "colour": colour, "tone": tone}


def fill_layer(view: View, style: mk.MarkerStyle, maps: dict | None = None,
               fade: np.ndarray | None = None) -> np.ndarray:
    """The fill's effect (marker or watercolour), (H, W, 3) factors to
    multiply the paper by, at the drawing's size; ``fade`` (at the
    buffer's size) thins it out toward the edges."""
    maps = maps if maps is not None else shade_maps(view, style)
    ones = np.full((view.bh, view.bw, 3), 255.0)
    scale = view.bh / st.REFERENCE_HEIGHT
    if mk.colour_mode(style) == "contrast":
        # High contrast is its own technique: contour and solid ink.
        factor = ink.paint(ones, maps["values"], maps["tone"], scale, INK,
                           texture=style.ink_texture, strength=min(1.0, style.strength))
    elif style.medium == "watercolour":
        factor = wc.paint(ones, maps["values"], maps["colour"], style, scale,
                          tone=maps["tone"])
    else:
        factor = mk.paint(ones, maps["values"], maps["plane"], maps["angles"],
                          style, scale, colour=maps["colour"], tone=maps["tone"],
                          jitter=maps["jitter"])
    if fade is not None:
        factor = 255.0 - (255.0 - factor) * fade[:, :, None]
    return _resize(factor, view.width, view.height) / 255.0


#: The name it had in 0.3.0.
marker_layer = fill_layer


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
           marker: mk.MarkerStyle | None = None,
           composition: cp.Composition | None = None) -> QImage:
    """The current view as a freehand drawing, ``width`` pixels wide (the
    height follows the view): paper, the fill (``marker``: grey and colour
    marker or watercolour, if on), the ink: hatching, then the lines.
    ``view``: a :class:`View` the caller already made."""
    width, height = drawing_size(viewport.camera, width)
    view = view if view is not None else View(viewport, width, height)
    comp = composition if composition is not None else cp.Composition(
        unfinished=False, construction=False, ground=False)
    sheet = paper(width, height)
    subject = cp.subject_mask(view.index, view.tris) \
        if (comp.unfinished or comp.ground) else None
    fade = (cp.fade_map(subject, view.bh / st.REFERENCE_HEIGHT)
            if comp.unfinished else None)
    maps = None
    if marker is not None and (marker.enabled or marker.hatching) and len(view.tris):
        maps = shade_maps(view, marker)
        if marker.enabled:
            sheet = sheet * fill_layer(view, marker, maps, fade)
    img = to_qimage(sheet)
    kinds = view.outline if style.profile_scale != 1.0 else None
    strokes = []
    if comp.construction:
        strokes += cp.construction_strokes(view.segs, height, width, style.hand,
                                           index=view.index, to_buffer=view.scale)
    if comp.ground:
        strokes += cp.ground_strokes(view, height, style.hand)
    if maps is not None and marker.hatching:
        shade = hatch.hatch_strokes(maps, marker, view.scale, height, style.hand)
        if fade is not None:
            shade = cp.thin_out(shade, fade, view.scale)
        strokes += shade
    strokes += st.strokes_for(view.segs, kinds, style, height)
    draw_strokes(img, strokes)
    return img
