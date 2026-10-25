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


def _rgb_of(viewport, attrs, default):
    """The colour a face shows (0..1): its paint, or its texture's average
    colour (as a shaded view shows it), or the default face colour."""
    tex = attrs.get("texture") if attrs else None
    if isinstance(tex, dict) and tex.get("path"):
        avg = getattr(viewport, "_texture_avg_color", None)
        if avg is not None:
            return avg(tex["path"])
    col = (attrs or {}).get("color")
    if col is not None and len(col) >= 3:
        return tuple(float(c) for c in col[:3])
    return default


def _lightness(rgb) -> float:
    r, g, b = (float(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


#: Where the host reads the visible faces and their paint, tried in order:
#: ``source(viewport, colour_of)`` -> ``(tris, marker, tone)`` or None.
#: A host that hands its colours with the view
#: (``viewport.croquis_colours``) sets none.
SOURCES = ()
#: The log a failed source is told in (the host may name its own).
LOGGER = "croquis"


def _cache_key(viewport):
    """What the colours depend on: the model's version, and which faces
    show (hiding a tag need not change the version). ``None`` when it
    cannot be told: then nothing is cached."""
    import hashlib
    scene = getattr(viewport, "scene", None)
    version = getattr(scene, "version", None)
    if version is None:
        return None
    try:
        idx = viewport._pick_flat(viewport._pick_index(near="all"))
        vis = hashlib.blake2b(np.ascontiguousarray(idx.ent_vis).tobytes(),
                              digest_size=16).digest()
        return (id(scene), version, id(idx.tri_v0), vis)
    except Exception:                    # noqa: BLE001 (another host)
        return None


def triangle_colours(viewport):
    """:func:`_triangle_colours`, kept until the model or what shows of it
    changes: the live preview asks on every new view, on the main thread,
    and on a model of 700 000 faces reading them takes seconds."""
    key = _cache_key(viewport)
    cached = getattr(viewport, "_croquis_colours", None)
    if key is not None and cached is not None and cached[0] == key:
        return cached[1]
    out = _triangle_colours(viewport)
    if key is not None:
        try:
            viewport._croquis_colours = (key, out)
        except AttributeError:           # a viewport that takes no attributes
            pass
    return out


def _triangle_colours(viewport):
    """``(tris (T,3,3), marker (T,) index or -1, tone (T,) lightness 0..1)``
    of the visible faces: the colour as the host draws the face (its own
    paint, or its group's; a texture by its average colour), read by the
    host's :data:`SOURCES` in turn. A face whose paint cannot be read counts
    as the default face; ``None`` only when nothing can be read (then the
    drawing has no colour, and the reason is in the log)."""
    import logging
    log = logging.getLogger(LOGGER)
    default = getattr(viewport, "DEFAULT_FACE_COLOR", (0.96, 0.95, 0.925))
    cache: dict = {}
    failures = [0]

    def colour_of(attrs):
        try:
            rgb = _rgb_of(viewport, attrs, default)
            key = tuple(round(float(c), 3) for c in rgb[:3])
        except Exception:                # noqa: BLE001 (one odd face)
            failures[0] += 1
            key = tuple(default[:3])
        if key not in cache:
            cache[key] = (nearest_marker(key), _lightness(key))
        return cache[key]

    for source in SOURCES:
        try:
            out = source(viewport, colour_of)
        except Exception:                # noqa: BLE001 (another host)
            log.warning("croquis: colours via %s failed", source.__name__,
                        exc_info=True)
            continue
        if out is not None:
            if failures[0]:
                log.warning("croquis: %d face paints could not be read",
                            failures[0])
            return out
    return None
