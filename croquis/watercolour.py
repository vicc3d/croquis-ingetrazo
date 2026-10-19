# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Watercolour washes, the other way to lay colour and shade.

A wash is not a marker: it runs a little past the lines and stops short
elsewhere, its edge wanders, the pigment is uneven and gathers darker at
the rim where the water dried, and the paper's grain shows through. The
shade is a cool, bluish wash over the colour; a cast shadow, a deeper one.

The same images as the marker (:mod:`.marker`): ``values`` per pixel (0
lit, 1 turned, 2 away, 3 cast shadow) and a marker colour per pixel.
"""
from __future__ import annotations

import numpy as np

from .marker import _box_blur, _noise, _shift

#: The shade washes: a cool grey, and a deeper blue for cast shadows.
SHADE_WASH = (128, 134, 158)
SHADOW_WASH = (96, 108, 160)
#: A material's own tone (greys, blacks): a neutral wash.
TONE_WASH = (118, 116, 112)
#: High contrast: deep, near-black washes.
CONTRAST_WASH = (70, 72, 82)


def _wash(ind: np.ndarray, tint, strength: float, scale: float, seed: int,
          bleed: float) -> np.ndarray:
    """The factor (H, W, 3) one wash multiplies the paper by: over ``ind``
    (0..1), with a wandering edge that runs ``bleed`` px past it or stops
    short, uneven pigment, a darker rim and the paper's grain."""
    h, w = ind.shape
    r = max(1, int(round(bleed)))
    wander = _noise((h, w), 40.0 * scale, seed)
    blur = _box_blur(ind, r)
    soft = blur + (wander - 0.5) * 0.7
    m = np.clip((soft - 0.32) / 0.08, 0.0, 1.0)
    # The wandering edge only near the fill: never a drop far from it.
    m *= _box_blur(ind, 3 * r) > 0.02
    if not m.any():
        return np.ones((h, w, 3))
    blotch = _noise((h, w), 70.0 * scale, seed + 1)
    grain = _noise((h, w), 2.2 * scale, seed + 2)
    # The rim: where the wash ends, the pigment gathers.
    inner = _box_blur(m, max(1, int(round(4 * scale))))
    rim = np.clip(m - inner, 0.0, 1.0) * 2.2
    density = (0.55 + 0.6 * blotch) * (0.85 + 0.3 * grain) + rim
    alpha = np.clip(m * density * strength, 0.0, 1.0)[:, :, None]
    t = np.array(tint, dtype=np.float64)[None, None, :] / 255.0
    return 1.0 - alpha * (1.0 - t)


def paint(base: np.ndarray, values: np.ndarray, colour, style, scale: float,
          tone=None) -> np.ndarray:
    """Lay the washes on ``base`` (H, W, 3 floats 0..255): the colours,
    then the shade and the cast shadows over them, all shifted by the
    style's offset like the marker."""
    h, w = values.shape
    dx = int(round(style.offset * scale * 0.8))
    dy = int(round(style.offset * scale * 0.6))
    vals = _shift(values, dx, dy, -1)
    out = base.copy()
    bleed = 7.0 * scale
    from .marker import colour_mode, tone_masks
    mode = colour_mode(style)
    col = _shift(colour, dx, dy, -1) if colour is not None else None
    if col is not None and mode == "colour":
        from .palette import MARKERS
        for k in np.unique(col[col >= 0]):
            here = col == k
            # Lighter where the light falls: each face its own wash, so they
            # meet with a rim, as when painted one after the other.
            lit = (here & (vals == 0)).astype(np.float64)
            rest = (here & (vals != 0)).astype(np.float64)
            if lit.any():
                out *= _wash(lit, MARKERS[int(k)], 0.45 * style.strength,
                             scale, 300 + int(k), bleed)
            if rest.any():
                out *= _wash(rest, MARKERS[int(k)], 0.8 * style.strength,
                             scale, 340 + int(k), bleed)
    mid, dark = tone_masks(_shift(tone, dx, dy, -1.0) if tone is not None else None,
                           col, mode)
    if mid is not None:
        t = (mid * 0.45 + dark * 1.0).astype(np.float64)
        if t.any():
            out *= _wash(t, TONE_WASH, 0.75 * style.strength, scale, 411, bleed)
    if mode == "contrast":
        shade = (vals == 2).astype(np.float64)
        cast = (vals == 3).astype(np.float64)
        if shade.any():
            out *= _wash(shade, CONTRAST_WASH, 0.8 * style.strength, scale, 401, bleed)
        if cast.any():
            out *= _wash(cast, CONTRAST_WASH, 0.95 * style.strength, scale, 409, bleed)
        return out
    shade = ((vals == 1) * 0.45 + (vals == 2) * 1.0).astype(np.float64)
    if shade.any():
        out *= _wash(np.clip(shade, 0, 1), SHADE_WASH, 0.6 * style.strength,
                     scale, 401, bleed)
    cast = (vals == 3).astype(np.float64)
    if cast.any():
        out *= _wash(cast, SHADOW_WASH, 0.75 * style.strength, scale, 409, bleed)
    return out
