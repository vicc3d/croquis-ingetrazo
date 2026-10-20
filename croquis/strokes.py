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


#: Two lines meeting turn by at least this much to make a corner; less is
#: a curve drawn in short pieces (a pipe, an arc), which a hand draws on.
CORNER_ANGLE = 35.0
#: More ends than this in one small cell is a cluster of fine detail, not a
#: corner: no overshoot there (it bristled like a brush).
CROWD = 6
#: Two ends this close (a share of the tolerance) are one point: a curve's
#: pieces meet so, or nearly, where something in front cuts them.
_SAME_POINT = 0.5


def corner_ends(segs: np.ndarray, tol: float,
                min_angle: float = CORNER_ANGLE) -> np.ndarray:
    """``(N, 2)`` bools: does each end of each segment meet the end of
    another segment (a corner), within ``tol`` pixels, turning by
    ``min_angle`` degrees or more? An end that does not is a free end, a
    line passing behind something (a T), or a curve going on: no overshoot."""
    return end_joins(segs, tol, min_angle)[0]


def end_joins(segs: np.ndarray, tol: float, min_angle: float = CORNER_ANGLE):
    """How each segment's ends meet the others' within ``tol`` pixels:
    ``(corner, goes_on, pairs)``. ``corner`` (N, 2): an end meeting another
    that turns by ``min_angle`` or more; ``goes_on`` (N, 2): one meeting
    another that turns less (a curve in short pieces, or a line split
    along its way), or in a cluster of ends, and not a corner: drawn to its
    point; ``pairs`` (P, 2): the segments joined where they share their
    point, the links of a curve.

    On a grid of cells a little smaller than ``tol`` (their diagonal is
    ``tol``), only the cells around each end are looked at, all at once;
    a cell crowded with ends is detail too fine to join or turn."""
    n = len(segs)
    if not n:
        return (np.zeros((0, 2), dtype=bool), np.zeros((0, 2), dtype=bool),
                np.zeros((0, 2), dtype=np.int64))
    segs = np.asarray(segs, dtype=np.float64).reshape(n, 4)
    ends = segs.reshape(n * 2, 2)
    seg = np.arange(n * 2) // 2
    out = np.zeros(n * 2, dtype=bool)
    on = np.zeros(n * 2, dtype=bool)
    links = []
    # Each segment's direction, a unit vector (zero for a point).
    d = segs[:, 2:] - segs[:, :2]
    ln = np.hypot(d[:, 0], d[:, 1])
    d = np.where(ln[:, None] > 1e-9, d / np.maximum(ln, 1e-9)[:, None], 0.0)
    sin_min = math.sin(math.radians(min_angle))
    ok = np.isfinite(ends).all(axis=1)
    if not ok.any():
        return out.reshape(n, 2), on.reshape(n, 2), np.zeros((0, 2), dtype=np.int64)
    c = tol / math.sqrt(2.0)
    cells = np.zeros((n * 2, 2), dtype=np.int64)
    cells[ok] = np.floor(ends[ok] / c).astype(np.int64)
    lo_c = cells[ok].min(axis=0) - 2
    span_y = int(cells[ok][:, 1].max() - lo_c[1]) + 3
    key = (cells[:, 0] - lo_c[0]) * span_y + (cells[:, 1] - lo_c[1])
    key[~ok] = -1
    # A crowded cell takes no part, as an end or as the other end.
    _u, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    crowded = cnt[inv.reshape(-1)] > CROWD
    key[crowded] = -1
    # Nor is an end there free: drawn to its point, not short of it (a gap
    # in a cluster read as a cut ring).
    on[crowded & ok] = True
    order = np.argsort(key, kind="stable")
    order = order[key[order] >= 0]
    skey = key[order]
    tol2 = tol * tol
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            nk = key[order] + dx * span_y + dy
            lo = np.searchsorted(skey, nk, side="left")
            cnt_ = np.searchsorted(skey, nk, side="right") - lo
            has = cnt_ > 0
            p, lo, m = order[has], lo[has], cnt_[has]
            # At most CROWD ends in a cell: the pairs stay few.
            i = np.repeat(p, m)
            start = np.repeat(np.cumsum(m) - m, m)
            j = order[np.repeat(lo, m) + (np.arange(len(i)) - start)]
            dd = ends[j] - ends[i]
            si, sj = seg[i], seg[j]
            turn = np.abs(d[si, 0] * d[sj, 1] - d[si, 1] * d[sj, 0])
            dist2 = (dd * dd).sum(axis=1)
            meet = (si != sj) & (dist2 <= tol2)
            hit = meet & (turn >= sin_min)
            out[i[hit]] = True
            soft = meet & ~hit
            on[i[soft]] = True
            # Linked as one curve only where the pieces share their point
            # (one vertex of the model, or nearly where something in front
            # cuts them); lines of a crowd only pass near each other.
            same = soft & (dist2 <= (_SAME_POINT * tol) ** 2)
            links.append(np.c_[i[same], j[same]])
    on &= ~out
    pairs = (np.concatenate(links) if links else np.zeros((0, 2), dtype=np.int64))
    # Not at a corner. (Not «two pieces only» either: an imported model
    # often repeats an edge, so a clean ring's joints hold several ends.)
    if len(pairs):
        pairs = pairs[~out[pairs[:, 0]] & ~out[pairs[:, 1]]]
    return out.reshape(n, 2), on.reshape(n, 2), (pairs // 2).astype(np.int64)


def chains(n: int, pairs: np.ndarray) -> np.ndarray:
    """``(N,)`` the chain each segment belongs to (its smallest member):
    the segments ``pairs`` link, one after another (a curve's pieces)."""
    label = np.arange(n)
    if not len(pairs):
        return label
    a, b = pairs[:, 0], pairs[:, 1]
    while True:
        prev = label.copy()
        m = np.minimum(label[a], label[b])
        np.minimum.at(label, a, m)
        np.minimum.at(label, b, m)
        label = label[label]                # jump along what is known
        if np.array_equal(label, prev):
            return label


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


#: Ink per area (line length over area, in 1/px at the reference height)
#: where a zone starts to read as crowded, and where it is fully so.
CROWDED_FROM = 0.10
CROWDED_AT = 0.30


def line_density(segs: np.ndarray, height_px: float) -> np.ndarray:
    """``(N,)``: how much line there is around each segment's middle, as
    length of line per pixel of area over a few cells around it (about 30
    pixels across at the reference height)."""
    n = len(segs)
    if not n:
        return np.zeros(0)
    s = height_px / REFERENCE_HEIGHT
    cell = 10.0 * s
    a, b = segs[:, :2], segs[:, 2:]
    length = np.hypot(*(b - a).T)
    # Each segment's length spread along it, a share per cell it crosses.
    k = np.maximum(1, np.ceil(length / cell).astype(np.int64))
    ids = np.repeat(np.arange(n), k)
    t = (np.arange(len(ids)) - np.repeat(np.cumsum(k) - k, k) + 0.5) / np.repeat(k, k)
    pts = a[ids] + t[:, None] * (b - a)[ids]
    share = (length / k)[ids]
    cx = np.floor(pts[:, 0] / cell).astype(np.int64)
    cy = np.floor(pts[:, 1] / cell).astype(np.int64)
    x0, y0 = cx.min() - 1, cy.min() - 1
    w, h = int(cx.max() - x0) + 2, int(cy.max() - y0) + 2
    grid = np.zeros((h, w))
    np.add.at(grid, (cy - y0, cx - x0), share)
    # Over the 3x3 cells around.
    pad = np.pad(grid, 1)
    around = sum(pad[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3))
    mid = (a + b) / 2.0
    mx = np.clip(np.floor(mid[:, 0] / cell).astype(np.int64) - x0, 0, w - 1)
    my = np.clip(np.floor(mid[:, 1] / cell).astype(np.int64) - y0, 0, h - 1)
    return around[my, mx] / (9.0 * cell * cell) * s


def simplify(segs: np.ndarray, outline, height_px: float):
    """Fine detail as a hand draws it: where lines crowd (a valve, a
    railing, a machine's bolts), the short ones are left out and the rest
    drawn lighter, so the shape reads and not a black mass. Outlines stay,
    a little lighter: they are the shape. Returns ``(segs, outline, weight)``, ``weight`` (N,)
    1 for a line drawn as usual, down to 0.5 for one in a crowd."""
    segs = np.asarray(segs, dtype=np.float64).reshape(-1, 4)
    n = len(segs)
    outline = (np.zeros(n, dtype=bool) if outline is None
               else np.asarray(outline, dtype=bool))
    if not n:
        return segs, outline, np.ones(0)
    s = height_px / REFERENCE_HEIGHT
    crowd = np.clip((line_density(segs, height_px) - CROWDED_FROM)
                    / (CROWDED_AT - CROWDED_FROM), 0.0, 1.0)
    length = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    # A curve in short pieces counts by its whole length: its pieces stay
    # or go together (or a circle came out dashed).
    _c, _g, pairs = end_joins(segs, tol=max(1.5, 2.0 * s))
    chain = chains(n, pairs)
    length = np.bincount(chain, length, minlength=n)[chain]
    # The more crowded, the longer a line must be to stay. An outline always
    # stays, a little lighter: it is the shape (the fountain's ornament
    # vanished without it).
    keep = outline | (length >= 24.0 * s * crowd)
    weight = np.where(outline, 1.0 - 0.25 * crowd, 1.0 - 0.5 * crowd)
    return segs[keep], outline[keep], weight[keep]


def _overshoot(rng, reach: float, corner: bool, goes_on: bool, s: float,
               h: float) -> float:
    """How far a line's end runs past its point: past a corner, as a hand
    does; a hair into the next piece of a curve, so it reads unbroken;
    else a little short (a free end). One draw of ``rng`` either way, so
    the rest of the drawing stays the same."""
    if corner:
        return reach * rng.uniform(0.5, 1.0)
    pull = -rng.uniform(0.0, 1.5) * s * h
    return 0.5 * s if goes_on else pull


def strokes_for(segs: np.ndarray, kinds, style: LineStyle,
                height_px: float, weight=None) -> list:
    """The ink strokes for ``segs`` ((N, 4) pixels: x0, y0, x1, y1).
    ``kinds`` (N,) marks outlines (True: drawn heavier), or None;
    ``weight`` (N,) thins a line (1 as usual; :func:`simplify`'s), or None."""
    segs = np.asarray(segs, dtype=np.float64).reshape(-1, 4)
    s = height_px / REFERENCE_HEIGHT
    corners, goes_on, _pairs = end_joins(segs, tol=max(1.5, 2.0 * s))
    h = max(0.0, min(1.0, style.hand))
    out: list = []
    for i, seg in enumerate(segs):
        a, b = seg[:2], seg[2:]
        length = float(math.hypot(*(b - a)))
        if length < 0.5 * s:
            continue
        rng = random.Random(_seed(seg, 1))
        heavy = kinds is not None and bool(kinds[i])
        wt = 1.0 if weight is None else float(weight[i])
        width = style.width * s * (style.profile_scale if heavy else 1.0) * wt
        opacity = style.opacity * (0.6 + 0.4 * wt)
        # Overshoot at corners only; short lines overshoot less.
        reach = style.overshoot * h * s * rng.uniform(5.0, 14.0)
        reach = min(reach, 0.5 * length + 3.0 * s)
        over_a = _overshoot(rng, reach, corners[i, 0], goes_on[i, 0], s, h)
        over_b = _overshoot(rng, reach, corners[i, 1], goes_on[i, 1], s, h)
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
                out.append(Stroke(_ribbon(piece, width, rng), opacity))
        # Drawn twice: a second, lighter pass a little off the first.
        # (Not in a crowd: a second pass there is more of the mass.)
        if style.double_stroke and h >= 0.35 and wt > 0.85 \
                and rng.random() < 0.25 + 0.6 * h:
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
                                  opacity * 0.55))
    return out
