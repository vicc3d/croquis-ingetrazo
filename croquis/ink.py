# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""High contrast, as a comic or an ink drawing: contour and solid black.

Two values only. What the light reaches stays the white of the paper; the
faces turned away from it, the cast shadows and the dark materials are
filled with solid ink, right up to the lines (no offset: it is the same
pen). With the brush texture, the black breaks up at its edges as a dry
brush or a worn nib leaves it.
"""
from __future__ import annotations

import numpy as np

from .marker import DARK_TONE, _box_blur, _noise


def paint(base: np.ndarray, values: np.ndarray, tone, scale: float,
          ink=(29, 26, 23), texture: bool = False,
          strength: float = 1.0) -> np.ndarray:
    """Lay the black masses on ``base`` (H, W, 3 floats 0..255).
    ``values``: 2 away from the light, 3 in a cast shadow; ``tone``: the
    materials' lightness per pixel (dark ones are black too), or None."""
    mass = (values == 2) | (values == 3)
    if tone is not None:
        mass |= (tone >= 0) & (tone < DARK_TONE)
    if not mass.any():
        return base
    m = mass.astype(np.float64)
    h, w = m.shape
    if texture:
        # A dry brush: the edge of the mass breaks into specks, more of
        # them the nearer the edge, and a few gaps inside.
        r = max(1, int(round(6 * scale)))
        near = _box_blur(m, r)
        speck = _noise((h, w), 1.6 * scale, 71)
        drag = _noise((h, w), 14.0 * scale, 73)
        m = ((near + (speck - 0.5) * 0.9 + (drag - 0.5) * 0.35) > 0.62).astype(np.float64)
        m *= mass | (near > 0.85)
    else:
        # A clean edge, softened a hair (antialiasing).
        m = np.clip(_box_blur(m, 1) * 1.2 - 0.1, 0.0, 1.0)
    a = np.clip(m * strength, 0.0, 1.0)[:, :, None]
    t = np.array(ink, dtype=np.float64)[None, None, :] / 255.0
    return base * (1.0 - a * (1.0 - t))
