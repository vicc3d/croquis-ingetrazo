# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The composition of the sheet: what makes a drawing look drawn, not
printed.

- **Unfinished edges:** the colour is laid where the eye goes, the middle of
  the subject, and thins out toward its edges, with a ragged limit; the ink
  lines stay whole.
- **Construction lines:** some of the long lines run on past the drawing,
  thin and light, as the guides a sketcher draws first.
- **Ground strokes:** a few loose strokes fanning out under the model, to
  sit it on the ground.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from . import strokes as st
from .marker import _noise


@dataclass
class Composition:
    unfinished: bool = True
    construction: bool = True
    ground: bool = False


def subject_mask(index: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """The pixels of the subject: the model without its ground, when it has
    one (its largest horizontal plane, if it takes a good part of the
    view). A ground would pull the middle of the drawing away from what
    stands on it."""
    model = index >= 0
    if not model.any() or not len(tris):
        return model
    from .marker import triangle_normals
    n = triangle_normals(tris)
    level = np.abs(n[:, 2]) > 0.97
    height = np.round(tris[:, 0, 2] * 50.0).astype(np.int64)
    ix = np.where(model, index, 0)
    flat = model & level[ix]
    if not flat.any():
        return model
    keys, counts = np.unique(height[ix[flat]], return_counts=True)
    k = int(np.argmax(counts))
    if counts[k] < 0.35 * model.sum():
        return model
    ground = flat & (height[ix] == keys[k])
    subject = model & ~ground
    return subject if subject.any() else model


def subject_box(index: np.ndarray):
    """``(cx, cy, rx, ry)`` of the model in the image (its pixels' box), or
    None when it shows nothing."""
    mask = index if index.dtype == bool else index >= 0
    rows = np.nonzero(mask.any(axis=1))[0]
    if not len(rows):
        return None
    cols = np.nonzero(mask.any(axis=0))[0]
    cy, cx = (rows[0] + rows[-1]) / 2.0, (cols[0] + cols[-1]) / 2.0
    ry = max(4.0, (rows[-1] - rows[0]) / 2.0)
    rx = max(4.0, (cols[-1] - cols[0]) / 2.0)
    return cx, cy, rx, ry


def fade_map(subject: np.ndarray, scale: float, seed: int = 61) -> np.ndarray:
    """(H, W) 0..1: how much of the colour stays at each pixel. Whole over
    the subject and a margin round it, thinning out past that, to a limit
    that wanders."""
    h, w = subject.shape
    box = subject_box(subject)
    if box is None:
        return np.ones((h, w))
    cx, cy, rx, ry = box
    # A margin round the subject: its shadow and the ground at its foot.
    rx, ry = rx * 1.35 + 30 * scale, ry * 1.25 + 30 * scale
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    d = np.hypot((xx - cx) / rx, (yy - cy) / ry)
    wander = _noise((h, w), 90.0 * scale, seed)
    return np.clip((1.1 - d) / 0.45 + (wander - 0.5) * 0.7, 0.0, 1.0)


def construction_strokes(segs: np.ndarray, height: int, width: int,
                         hand: float, seed: int = 17) -> list:
    """Thin, light strokes running on past the ends of some of the longest
    lines, as a sketcher's guides."""
    if not len(segs):
        return []
    s = height / st.REFERENCE_HEIGHT
    length = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    order = np.argsort(-length)
    long_ones = [i for i in order if length[i] > 0.10 * height]
    pick = long_ones[:max(4, min(14, len(long_ones) // 4))]
    rng = random.Random(seed)
    out_segs = []
    for i in pick:
        a, b = segs[i, :2], segs[i, 2:]
        d = (b - a) / length[i]
        for end, sign in ((a, -1.0), (b, 1.0)):
            if rng.random() < 0.35:
                continue
            reach = length[i] * rng.uniform(0.12, 0.45) + 20 * s
            far = end + sign * d * reach
            out_segs.append(np.r_[end + sign * d * 6 * s, far])
    if not out_segs:
        return []
    style = st.LineStyle(hand=min(1.0, hand * 0.7 + 0.1), width=0.7,
                         profile_scale=1.0, overshoot=0.0, double_stroke=False,
                         breaks=False, opacity=0.42)
    return st.strokes_for(np.array(out_segs), None, style, height)


def ground_strokes(subject: np.ndarray, to_drawing: float, height: int,
                   hand: float, seed: int = 23) -> list:
    """A few loose strokes on the ground under the subject: lines fanning
    out from its foot, as the lines of a street toward the viewer, and one
    or two along the ground."""
    rows = np.nonzero(subject.any(axis=1))[0]
    if not len(rows):
        return []
    top, bottom = rows[0], rows[-1]
    # The foot: the subject's width over its lowest fifth.
    foot = subject[max(top, bottom - max(3, (bottom - top) // 5)):bottom + 1]
    cols = np.nonzero(foot.any(axis=0))[0]
    if not len(cols):
        return []
    s = height / st.REFERENCE_HEIGHT
    cx = (cols[0] + cols[-1]) / 2.0 / to_drawing
    span = max(30.0 * s, (cols[-1] - cols[0]) / 2.0 / to_drawing)
    oy = bottom / to_drawing
    rng = random.Random(seed)
    segs = []
    n = rng.randint(6, 9)
    for k in range(n):
        u = (k + rng.uniform(0.2, 0.8)) / n * 2.0 - 1.0     # -1..1 across
        x0 = cx + u * span * 1.15
        y0 = oy + rng.uniform(6, 22) * s
        # Away from a point far above the subject: they open outward.
        ang = math.atan2(1.0, u * 0.75 + rng.uniform(-0.12, 0.12))
        length = rng.uniform(0.05, 0.11) * height
        segs.append(np.array([x0, y0, x0 + length * math.cos(ang),
                              y0 + length * math.sin(ang)]))
    for _k in range(2):
        y = oy + rng.uniform(3, 12) * s
        segs.append(np.array([cx - span * rng.uniform(1.3, 1.8), y,
                              cx + span * rng.uniform(1.3, 1.8),
                              y + rng.uniform(-3, 3) * s]))
    style = st.LineStyle(hand=min(1.0, hand * 0.8 + 0.2), width=0.9,
                         profile_scale=1.0, overshoot=0.0, double_stroke=False,
                         breaks=True, opacity=0.5)
    return st.strokes_for(np.array(segs), None, style, height)


def thin_out(strokes: list, fade: np.ndarray, to_buffer: float, seed: int = 29) -> list:
    """Leave out, at random, the strokes the fade takes (hatching that
    thins out toward the edges, like the colour)."""
    if not strokes:
        return strokes
    h, w = fade.shape
    rng = random.Random(seed)
    kept = []
    for s in strokes:
        cx, cy = s.outline.mean(axis=0) * to_buffer
        x = min(w - 1, max(0, int(cx)))
        y = min(h - 1, max(0, int(cy)))
        if rng.random() < fade[y, x] ** 0.7:
            kept.append(s)
    return kept
