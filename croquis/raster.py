# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The ink strokes laid on an image with NumPy alone, for where there is no
Qt (Blender): each stroke's outline filled even-odd, as QPainter fills a
polygon, smoothed at its edges, and laid over what is already there.

A row of pixels is cut four times; on each cut the outline's crossings
give the spans inside, measured exactly across (a span that starts a third
into a pixel covers two thirds of it). The four cuts, averaged, are the
pixel's coverage.
"""
from __future__ import annotations

import numpy as np

#: Cuts per row of pixels.
SUB = 4


def _spans(outline: np.ndarray, h: int):
    """The spans inside the polygon on each cut of the rows ``0..h``:
    ``(rows, start, end)``, ``rows`` the cut's index (row * SUB + cut)."""
    a = np.asarray(outline, dtype=np.float64)
    b = np.roll(a, -1, axis=0)
    # Each edge meets only the cuts between its ends: cut k is at
    # y = (k + 0.5) / SUB, and an edge meets the cuts in [min, max) of its
    # ends (half-open, so a vertex on a cut counts once).
    lo_y = np.minimum(a[:, 1], b[:, 1])
    hi_y = np.maximum(a[:, 1], b[:, 1])
    k0 = np.clip(np.ceil(lo_y * SUB - 0.5), 0, h * SUB).astype(np.int64)
    k1 = np.clip(np.ceil(hi_y * SUB - 0.5), 0, h * SUB).astype(np.int64)
    m = np.maximum(k1 - k0, 0)
    edge = np.repeat(np.arange(len(a)), m)
    rows = np.repeat(k0, m) + (np.arange(len(edge)) - np.repeat(np.cumsum(m) - m, m))
    y = (rows + 0.5) / SUB
    ea, eb = a[edge], b[edge]
    xs = ea[:, 0] + (y - ea[:, 1]) / (eb[:, 1] - ea[:, 1]) * (eb[:, 0] - ea[:, 0])
    # Even-odd: along each cut, inside between the 1st and 2nd crossing,
    # the 3rd and 4th...
    order = np.lexsort((xs, rows))
    rows, xs = rows[order], xs[order]
    n = len(rows)
    first = np.r_[True, rows[1:] != rows[:-1]] if n else np.zeros(0, bool)
    start_of = np.maximum.accumulate(np.where(first, np.arange(n), 0)) if n else first
    nxt = np.minimum(np.arange(n) + 1, max(n - 1, 0))
    pair = ((np.arange(n) - start_of) % 2 == 0) & (nxt != np.arange(n)) \
        & (rows[nxt] == rows)
    return rows[pair], xs[pair], xs[nxt[pair]]


def stroke_pixels(outline: np.ndarray, w: int, h: int):
    """``(index, cover)``: the pixels of a ``w`` × ``h`` image the polygon
    touches (flat index, row * w + column) and how much of each it covers,
    0..1. Only those: a thin stroke across the sheet is a few thousand."""
    rows, start, end = _spans(outline, h)
    start = np.clip(start, 0.0, w)
    end = np.clip(end, 0.0, w)
    keep = end > start
    rows, start, end = rows[keep], start[keep], end[keep]
    i0 = np.floor(start).astype(np.int64)
    i1 = np.minimum(np.ceil(end).astype(np.int64), w)         # exclusive
    m = np.maximum(i1 - i0, 0)
    span = np.repeat(np.arange(len(m)), m)
    col = np.repeat(i0, m) + (np.arange(len(span)) - np.repeat(np.cumsum(m) - m, m))
    # The share of [col, col + 1) the span covers, on one cut of SUB.
    share = (np.minimum(end[span], col + 1) - np.maximum(start[span], col)) / SUB
    flat = (rows[span] // SUB) * w + col
    index, inv = np.unique(flat, return_inverse=True)
    cover = np.bincount(inv.reshape(-1), share, minlength=len(index))
    return index, np.clip(cover, 0.0, 1.0)


def coverage(outline: np.ndarray, x0: int, y0: int, w: int, h: int) -> np.ndarray:
    """``(h, w)`` how much of each pixel of the box at ``(x0, y0)`` the
    polygon ``outline`` (K, 2) covers, 0..1, filled even-odd."""
    index, cover = stroke_pixels(np.asarray(outline, dtype=np.float64) - (x0, y0), w, h)
    out = np.zeros(w * h)
    out[index] = cover
    return out.reshape(h, w)


def lay_strokes(rgb: np.ndarray, strokes, ink=(29, 26, 23)) -> np.ndarray:
    """``rgb`` (H, W, 3) floats 0..255 with ``strokes`` laid on it in
    ``ink``, one over the other, each at its opacity. In place."""
    h, w = rgb.shape[:2]
    flat = rgb.reshape(-1, 3)
    colour = np.asarray(ink, dtype=np.float64)
    for s in strokes:
        if len(s.outline) < 3:
            continue
        index, cover = stroke_pixels(s.outline, w, h)
        if not len(index):
            continue
        a = (cover * max(0.0, min(1.0, s.opacity)))[:, None]
        flat[index] += (colour - flat[index]) * a
    return rgb
