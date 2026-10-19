# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Hatching: the shade drawn in ink, with parallel diagonal lines.

As a sketcher shades with the pen: lines at one slant across the faces in
shade, closer together in the cast shadows, each one drawn by hand (the same
strokes as the edges, lighter). The lines run inside the shaded area: a
line across the area is cut where it leaves it.
"""
from __future__ import annotations

import math

import numpy as np

from . import strokes as st
from .visibility import _runs

#: The slant of the hatching on the paper, degrees (from the horizontal).
ANGLE = 58.0


def hatch_segments(mask: np.ndarray, angle_deg: float, spacing: float,
                   min_len: float, seed: int = 3) -> np.ndarray:
    """Parallel lines at ``angle_deg``, ``spacing`` pixels apart, cut to
    ``mask`` (H, W bools): (N, 4) segments in its pixels, the pieces
    shorter than ``min_len`` left out."""
    h, w = mask.shape
    if not mask.any() or spacing <= 0:
        return np.empty((0, 4))
    a = math.radians(angle_deg)
    d = np.array([math.cos(a), -math.sin(a)])       # y grows down
    n = np.array([-d[1], d[0]])
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], dtype=np.float64)
    cs, ts = corners @ n, corners @ d
    rng = np.random.default_rng(seed)
    offs = np.arange(cs.min(), cs.max(), spacing)
    offs = offs + rng.uniform(-0.18, 0.18, len(offs)) * spacing
    t = np.arange(ts.min(), ts.max(), 1.0)
    if not len(offs) or not len(t):
        return np.empty((0, 4))
    ids = np.repeat(np.arange(len(offs)), len(t))
    tt = np.tile(t, len(offs))
    x = offs[ids] * n[0] + tt * d[0]
    y = offs[ids] * n[1] + tt * d[1]
    xi, yi = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    inside = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    on = np.zeros(len(x), dtype=bool)
    on[inside] = mask[yi[inside], xi[inside]]
    s, e = _runs(on, ids)
    keep = (e - s) >= min_len
    s, e = s[keep], e[keep]
    return np.stack([x[s], y[s], x[e], y[e]], axis=1)


def hatch_strokes(maps: dict, style, scale_to_drawing: float, height: int,
                  hand: float, spacing: float = 11.0) -> list:
    """The hatching strokes for a view's shade maps (``values`` 2 in shade,
    3 in a cast shadow), in drawing pixels. Along the faces (the marker's
    direction on each, as sketchers hatch parallel to the edges) or at one
    diagonal, turned by ``style.hatch_turn``. ``spacing`` at the reference
    height."""
    values = maps["values"]
    s = height / st.REFERENCE_HEIGHT
    sp = spacing * s * scale_to_drawing      # in the values' pixels
    lstyle = st.LineStyle(hand=min(1.0, hand * 0.8 + 0.15), width=0.9,
                          profile_scale=1.0, overshoot=0.0,
                          double_stroke=False, breaks=False, opacity=0.62)
    turn = float(getattr(style, "hatch_turn", 0.0))
    if getattr(style, "hatch_along", True):
        ang = maps["angles"] + maps["jitter"]
        pl = maps["plane"]
        # Screen angle per pixel (y down), as degrees with y up, binned.
        deg = -np.degrees(np.where(pl >= 0, ang[np.clip(pl, 0, len(ang) - 1)], ang[-1]))
        deg = np.round(((deg + turn) % 180.0) / 4.0) * 4.0
    else:
        deg = np.full(values.shape, (ANGLE + turn) % 180.0)
    out = []
    for level, factor, seed in ((2, 1.0, 3), (3, 0.62, 5)):
        mask = values == level
        if not mask.any():
            continue
        for a in np.unique(deg[mask]):
            segs = hatch_segments(mask & (deg == a), float(a), sp * factor,
                                  min_len=4.0 * s * scale_to_drawing,
                                  seed=seed + int(a))
            if len(segs):
                out += st.strokes_for(segs / scale_to_drawing, None, lstyle, height)
    return out
