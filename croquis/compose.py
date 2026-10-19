# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The composition of the sheet: what makes a drawing look drawn, not
printed.

- **Unfinished edges:** the colour is laid where the eye goes, the middle of
  the subject, and thins out toward its edges, with a ragged limit; the ink
  lines stay whole.
- **Construction lines:** some of the long lines run on past the drawing,
  thin and light, as the guides a sketcher draws first.
- **Ground strokes:** a few loose strokes on the ground round the model's
  foot, along its main directions and in the view's perspective, to sit it
  on the ground.
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
                         hand: float, seed: int = 17, index=None,
                         to_buffer: float = 1.0) -> list:
    """Thin, light strokes running on past the ends of some of the longest
    lines, as a sketcher's guides: only over empty paper (``index``, the
    view's buffer, -1 where no model is; it stops where the model begins),
    and never two along nearly the same line."""
    if not len(segs):
        return []
    s = height / st.REFERENCE_HEIGHT
    length = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    order = np.argsort(-length)
    long_ones = [i for i in order if length[i] > 0.10 * height]
    rng = random.Random(seed)
    chosen: list = []                    # (point, unit direction) per line
    out_segs = []
    limit = max(4, min(14, len(long_ones) // 4))

    def same_line(p, d):
        for q, e in chosen:
            if abs(float(d[0] * e[1] - d[1] * e[0])) < 0.07:      # ~4°
                off = p - q
                if abs(float(off[0] * e[1] - off[1] * e[0])) < 0.03 * height:
                    return True
        return False

    def free_reach(end, d, reach):
        """How far from ``end`` along ``d`` the paper stays empty."""
        if index is None:
            return reach
        h, w = index.shape
        steps = np.arange(8.0 * s, reach, 2.0 * s)
        if not len(steps):
            return 0.0
        pts = (end[None, :] + steps[:, None] * d[None, :]) * to_buffer
        x, y = pts[:, 0].astype(np.int64), pts[:, 1].astype(np.int64)
        inside = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        hits = np.zeros(len(steps), dtype=bool)
        hits[inside] = index[y[inside], x[inside]] >= 0
        if hits.any():
            return float(steps[int(np.argmax(hits))]) - 4.0 * s
        return reach

    for i in long_ones:
        if len(chosen) >= limit:
            break
        a, b = segs[i, :2], segs[i, 2:]
        d = (b - a) / length[i]
        if same_line(a, d):
            continue
        made = False
        for end, sign in ((a, -1.0), (b, 1.0)):
            if rng.random() < 0.35:
                continue
            reach = free_reach(end, sign * d,
                               length[i] * rng.uniform(0.12, 0.45) + 20 * s)
            if reach < 18 * s:
                continue
            out_segs.append(np.r_[end + sign * d * 6 * s, end + sign * d * reach])
            made = True
        if made:
            chosen.append((a, d))
    if not out_segs:
        return []
    style = st.LineStyle(hand=min(1.0, hand * 0.7 + 0.1), width=0.7,
                         profile_scale=1.0, overshoot=0.0, double_stroke=False,
                         breaks=False, opacity=0.42)
    return st.strokes_for(np.array(out_segs), None, style, height)


def _main_axes(geom, tris) -> float:
    """The model's main direction on the ground, radians: the most common
    direction of its level edges (weighted by length, modulo a right
    angle), as the walls of a building run."""
    hard = np.asarray(geom[1], dtype=np.float64).reshape(-1, 2, 3)
    if len(hard):
        d = hard[:, 1] - hard[:, 0]
        level = np.abs(d[:, 2]) < 0.05 * np.maximum(np.linalg.norm(d, axis=1), 1e-9)
        d = d[level]
        if len(d):
            w = np.hypot(d[:, 0], d[:, 1])
            a = np.arctan2(d[:, 1], d[:, 0]) * 4.0      # a right angle → 2π
            return float(np.arctan2((w * np.sin(a)).sum(), (w * np.cos(a)).sum()) / 4.0)
    return 0.0


def ground_strokes(view, height: int, hand: float, seed: int = 23) -> list:
    """Loose strokes on the ground round the model's foot, along its two
    main directions: drawn in the view's own perspective, they run toward
    its vanishing points, as the lines of a pavement. Only over empty
    paper (the model hides them)."""
    from . import shadow as sh
    from . import visibility as vis
    tris = view.tris
    if not len(tris):
        return []
    z0 = sh.ground_level(tris)
    phi = _main_axes(view.geom, tris)
    u = np.array([math.cos(phi), math.sin(phi), 0.0])
    v = np.array([-math.sin(phi), math.cos(phi), 0.0])
    pts = tris.reshape(-1, 3)
    pu, pv = pts @ u, pts @ v
    u0, u1, v0, v1 = pu.min(), pu.max(), pv.min(), pv.max()
    size = max(u1 - u0, v1 - v0, 1e-6)
    rng = random.Random(seed)
    world = []
    # Along u: lines at a few offsets across v, running out past the
    # footprint at either end; and the same along v.
    for (a0, a1, b0, b1, along, across) in ((u0, u1, v0, v1, u, v),
                                            (v0, v1, u0, u1, v, u)):
        for _k in range(rng.randint(3, 5)):
            b = rng.uniform(b0 - 0.15 * size, b1 + 0.15 * size)
            if rng.random() < 0.5:
                s0 = a1 + rng.uniform(0.02, 0.15) * size
                s1 = s0 + rng.uniform(0.25, 0.8) * size
            else:
                s1 = a0 - rng.uniform(0.02, 0.15) * size
                s0 = s1 - rng.uniform(0.25, 0.8) * size
            p0 = along * s0 + across * b
            p1 = along * s1 + across * b
            p0[2] = p1[2] = z0
            world.append((p0, p1))
    persp = bool(view.camera.perspective)
    h, w = view.index.shape
    segs = []
    for p0, p1 in world:
        A, B = vis._clip_segments(vis.to_clip(p0[None, :], view.M),
                                  vis.to_clip(p1[None, :], view.M))
        if not len(A):
            continue
        ax, ay, _q = vis._screen(A, w, h, persp)
        bx, by, _q = vis._screen(B, w, h, persp)
        n = int(max(2, math.hypot(bx[0] - ax[0], by[0] - ay[0]) / 2.0))
        t = np.linspace(0.0, 1.0, n)
        x, y = ax[0] + t * (bx[0] - ax[0]), ay[0] + t * (by[0] - ay[0])
        xi, yi = x.astype(np.int64), y.astype(np.int64)
        inside = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        free = inside.copy()
        free[inside] = view.index[yi[inside], xi[inside]] < 0
        # The pieces over empty paper.
        edges = np.flatnonzero(np.diff(np.r_[0, free.astype(np.int8), 0]))
        for s0, s1 in zip(edges[0::2], edges[1::2] - 1):
            if s1 - s0 >= 4:
                segs.append(np.array([x[s0], y[s0], x[s1], y[s1]]) / view.scale)
    if not segs:
        return []
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
