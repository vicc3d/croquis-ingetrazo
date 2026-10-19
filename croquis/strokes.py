# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Hand-drawn strokes from exact line segments.

Pure Python and NumPy (no Qt), so it can be tested on its own. The input is
what IngeTrazo's hidden-line pass gives: the visible segments of the model,
in output pixels. Each one becomes one or two ink strokes, as an architect
draws them freehand:

- it runs past the corner (overshoot), but only at a real corner, where it
  meets another line; where a line ends behind something in front, it stops;
- it bows a little and wavers along its length (the hand), and the bow grows
  with the length, as a long line drawn in one go does;
- its width swells in the middle and thins at the ends (the pressure);
- now and then it is drawn twice, the second pass a little off, and a long
  one may be broken where the pen was lifted.

Everything random is seeded by the segment itself, so the same view always
gives the same drawing.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

#: Reference height of the drawing in pixels: sizes below are for this, and
#: scale with the real output so a bigger image is the same drawing.
REFERENCE_HEIGHT = 1000.0


@dataclass
class LineStyle:
    """How the hand draws. ``hand`` 0 is a ruler, 1 a loose sketch; the rest
    are in pixels at :data:`REFERENCE_HEIGHT`."""
    hand: float = 0.6
    width: float = 2.0              # ink width of an ordinary edge
    profile_scale: float = 2.0      # outlines this much heavier
    overshoot: float = 1.0          # 0 none, 1 as a sketcher does, 2 a lot
    double_stroke: bool = True
    breaks: bool = True
    opacity: float = 0.9


@dataclass
class Stroke:
    """One ink stroke: its outline polygon, (K, 2) pixels, and its opacity."""
    outline: np.ndarray
    opacity: float


def _seed(seg, salt: int) -> int:
    """A stable seed from a segment (its ends, to the pixel)."""
    key = tuple(int(round(v)) for v in seg) + (salt,)
    h = 2166136261
    for v in key:
        h = ((h ^ (v & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return h


def corner_ends(segs: np.ndarray, tol: float) -> np.ndarray:
    """``(N, 2)`` bools: does each end of each segment meet the end of
    another segment (a corner), within ``tol`` pixels? An end that does not
    is a free end or a line passing behind something (a T): no overshoot."""
    n = len(segs)
    if not n:
        return np.zeros((0, 2), dtype=bool)
    ends = segs.reshape(n * 2, 2)
    cells = np.floor(ends / tol).astype(np.int64)
    buckets: dict = {}
    for i, (cx, cy) in enumerate(map(tuple, cells)):
        buckets.setdefault((cx, cy), []).append(i)
    out = np.zeros(n * 2, dtype=bool)
    tol2 = tol * tol
    for i, (cx, cy) in enumerate(map(tuple, cells)):
        p = ends[i]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in buckets.get((cx + dx, cy + dy), ()):
                    if j // 2 != i // 2 and \
                            float(((ends[j] - p) ** 2).sum()) <= tol2:
                        out[i] = True
                        break
                if out[i]:
                    break
            if out[i]:
                break
    return out.reshape(n, 2)


def _centreline(a, b, rng: random.Random, style: LineStyle, s: float,
                over_a: float, over_b: float):
    """Points along the hand's path from a to b (extended by the overshoot
    at each end), as (M, 2), plus the unit tangent and normal."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    d = b - a
    length = float(math.hypot(*d))
    t_hat = d / length
    n_hat = np.array([-t_hat[1], t_hat[0]])
    h = style.hand
    # The whole line turns a hair about its start: a hand never lands
    # exactly on the far point.
    turn = math.radians(rng.uniform(-0.7, 0.7) * h)
    c, sn = math.cos(turn), math.sin(turn)
    t_rot = np.array([t_hat[0] * c - t_hat[1] * sn, t_hat[0] * sn + t_hat[1] * c])
    n_rot = np.array([-t_rot[1], t_rot[0]])
    start = a - t_rot * over_a
    total = length + over_a + over_b
    k = max(3, int(total / (6.0 * s)) + 1)
    u = np.linspace(0.0, 1.0, k)
    # A bow over the whole stroke plus a slower and a quicker waver; the
    # bow grows with the length (a long line in one go curves more).
    bow = rng.uniform(-1.0, 1.0) * h * (0.4 * s + 0.006 * total)
    wav = h * 0.55 * s
    f1, f2 = rng.uniform(1.2, 2.2), rng.uniform(3.5, 6.0)
    p1, p2 = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    off = (bow * np.sin(math.pi * u)
           + wav * np.sin(math.tau * f1 * u + p1)
           + 0.5 * wav * np.sin(math.tau * f2 * u + p2))
    pts = start[None, :] + np.outer(u * total, t_rot) + np.outer(off, n_rot)
    return pts, t_rot, n_rot


def _ribbon(pts: np.ndarray, width: float, rng: random.Random,
            taper: float = 0.55) -> np.ndarray:
    """The outline of a stroke of ``width`` along ``pts``: thicker in the
    middle, thinner at the ends (``taper`` = width kept at the very ends)."""
    k = len(pts)
    u = np.linspace(0.0, 1.0, k)
    swell = taper + (1.0 - taper) * np.sin(math.pi * u) ** 0.6
    grain = 1.0 + 0.12 * np.sin(math.tau * rng.uniform(2, 5) * u
                                + rng.uniform(0, math.tau))
    half = 0.5 * width * swell * grain
    tang = np.gradient(pts, axis=0)
    norm = np.hypot(tang[:, 0], tang[:, 1])
    norm[norm < 1e-9] = 1.0
    nrm = np.stack([-tang[:, 1] / norm, tang[:, 0] / norm], axis=1)
    left = pts + nrm * half[:, None]
    right = pts - nrm * half[:, None]
    return np.vstack([left, right[::-1]])


def strokes_for(segs: np.ndarray, kinds, style: LineStyle,
                height_px: float) -> list:
    """The ink strokes for ``segs`` ((N, 4) pixels: x0, y0, x1, y1).
    ``kinds`` (N,) marks outlines (True: drawn heavier), or None."""
    segs = np.asarray(segs, dtype=np.float64).reshape(-1, 4)
    s = height_px / REFERENCE_HEIGHT
    corners = corner_ends(segs, tol=max(1.5, 2.0 * s))
    h = max(0.0, min(1.0, style.hand))
    out: list = []
    for i, seg in enumerate(segs):
        a, b = seg[:2], seg[2:]
        length = float(math.hypot(*(b - a)))
        if length < 0.5 * s:
            continue
        rng = random.Random(_seed(seg, 1))
        heavy = kinds is not None and bool(kinds[i])
        width = style.width * s * (style.profile_scale if heavy else 1.0)
        # Overshoot at corners only; short lines overshoot less.
        reach = style.overshoot * h * s * rng.uniform(5.0, 14.0)
        reach = min(reach, 0.5 * length + 3.0 * s)
        over_a = reach * rng.uniform(0.5, 1.0) if corners[i, 0] else \
            -rng.uniform(0.0, 1.5) * s * h
        over_b = reach * rng.uniform(0.5, 1.0) if corners[i, 1] else \
            -rng.uniform(0.0, 1.5) * s * h
        if length + over_a + over_b < 1.0 * s:
            continue
        pts, _t, _n = _centreline(a, b, rng, style, s, over_a, over_b)
        pieces = [pts]
        # A long line may be broken where the pen was lifted.
        if style.breaks and h > 0.2 and length > 140 * s and \
                rng.random() < 0.35 * h:
            cut = int(len(pts) * rng.uniform(0.3, 0.7))
            gap = max(1, int(rng.uniform(0.6, 1.6) * h * 2))
            if 2 <= cut and cut + gap <= len(pts) - 2:
                pieces = [pts[:cut], pts[cut + gap:]]
        for piece in pieces:
            if len(piece) >= 2:
                out.append(Stroke(_ribbon(piece, width, rng), style.opacity))
        # Drawn twice: a second, lighter pass a little off the first.
        if style.double_stroke and h >= 0.35 and rng.random() < 0.25 + 0.6 * h:
            rng2 = random.Random(_seed(seg, 2))
            shift = rng2.uniform(-1.0, 1.0) * h * 1.6 * s
            d = (b - a) / length
            nrm = np.array([-d[1], d[0]])
            trim_a = rng2.uniform(0.0, 0.25) * length
            trim_b = rng2.uniform(0.0, 0.25) * length
            a2 = a + d * trim_a + nrm * shift
            b2 = b - d * trim_b + nrm * shift
            if math.hypot(*(b2 - a2)) > 2 * s:
                over2a = over_a * 0.6 if corners[i, 0] and trim_a < 1 else 0.0
                over2b = over_b * 0.6 if corners[i, 1] and trim_b < 1 else 0.0
                pts2, _t, _n = _centreline(a2, b2, rng2, style, s, over2a, over2b)
                out.append(Stroke(_ribbon(pts2, width * 0.7, rng2),
                                  style.opacity * 0.55))
    return out
