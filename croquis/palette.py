# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The box of colour markers, and the colour of every face of the model.

A sketcher does not mix colours: they reach for the nearest marker in the
box. Every material of the model goes to the nearest of these; a colour
with little colour in it (white, greys, the default face) gets none, and
the greys of light and shade are left to say it.
"""
from __future__ import annotations

import colorsys

import numpy as np

#: A box of alcohol markers (RGB, 0..255).
MARKERS = (
    (196, 72, 52),     # brick red
    (205, 110, 70),    # terracotta
    (226, 123, 98),    # coral
    (233, 150, 60),    # orange
    (214, 170, 80),    # ochre
    (240, 214, 90),    # yellow
    (225, 205, 160),   # sand
    (205, 160, 110),   # light wood
    (150, 100, 65),    # dark wood
    (120, 85, 60),     # brown
    (150, 160, 90),    # olive
    (110, 160, 90),    # leaf green
    (70, 115, 80),     # dark green
    (150, 200, 170),   # mint
    (130, 175, 215),   # sky blue
    (80, 120, 180),    # blue
    (60, 80, 120),     # navy
    (70, 150, 160),    # teal
    (140, 110, 170),   # violet
    (220, 150, 170),   # pink
)
#: Below this saturation a colour gets no marker.
MIN_SATURATION = 0.16


def nearest_marker(rgb) -> int:
    """The marker for a colour (0..1 floats), or -1 for none."""
    r, g, b = (float(c) for c in rgb[:3])
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s * min(1.0, 2.0 * min(l, 1.0 - l) + 0.2) < MIN_SATURATION or l > 0.93 or l < 0.06:
        return -1
    best, dist = -1, 1e9
    for k, m in enumerate(MARKERS):
        mh, ml, ms = colorsys.rgb_to_hls(*(c / 255.0 for c in m))
        dh = min(abs(h - mh), 1.0 - abs(h - mh))
        d = (3.0 * dh) ** 2 + (l - ml) ** 2 + 0.5 * (s - ms) ** 2
        if d < dist:
            best, dist = k, d
    return best


def triangle_colours(viewport):
    """``(tris (T,3,3), colour (T,) marker index or -1)`` from the
    viewport's pick index, in the order of its ``hlr_geometry`` triangles;
    the colour as IngeTrazo draws the face: its own paint, or its group's,
    a texture by its average colour. ``None`` when this IngeTrazo does not
    expose it (then the drawing has no colour)."""
    try:
        from core.group import effective_material
        from core.materials import effective_attrs
        idx = viewport._pick_flat(viewport._pick_index(near="all"))
        if getattr(idx, "tri_v0", None) is None or not len(idx.tri_v0):
            return None
        keep = idx.ent_vis[idx.tri_ent]
        v0 = idx.tri_v0[keep]
        tris = np.stack([v0, v0 + idx.tri_e1[keep], v0 + idx.tri_e2[keep]],
                        axis=1).astype(np.float64)
        ents = idx.tri_ent[keep]
        default = getattr(viewport, "DEFAULT_FACE_COLOR", (0.96, 0.95, 0.925))
        cache: dict = {}
        per_ent = np.full(len(idx.entities), -1, dtype=np.int64)
        for e in np.unique(ents):
            face, group = idx.entities[e]
            attrs = effective_attrs(face.attrs, effective_material(group)) \
                if group is not None else face.attrs
            tex = attrs.get("texture") if attrs else None
            if isinstance(tex, dict) and tex.get("path"):
                rgb = viewport._texture_avg_color(tex["path"])
            else:
                rgb = (attrs or {}).get("color") or default
            key = tuple(round(float(c), 3) for c in rgb[:3])
            if key not in cache:
                cache[key] = nearest_marker(key)
            per_ent[e] = cache[key]
        return tris, per_ent[ents]
    except Exception:                    # noqa: BLE001 (another IngeTrazo)
        return None
