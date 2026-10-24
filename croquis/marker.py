# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Light and shade laid in with grey markers, as in a quick sketch.

Every face gets one of three values by how the light falls on it: the white
of the paper where it is lit, a light grey where it turns from the light, a
darker grey where it faces away; and where something stands between it and
the light (:mod:`.shadow`), a cool grey, the cast shadow. A sketcher does not
shade more finely than that. Under the greys, the colour of each material in
the nearest marker of the box (:mod:`.palette`), lighter where the light
falls.

The grey goes on as a broad marker does: parallel strokes, a little darker
where two overlap, along the face (up a wall, across a roof); the edges are
ragged, and the whole fill sits a little off the ink lines, never quite on
them, as when the marker goes on fast after the pen.

NumPy over images: the visible triangle of every pixel comes from the depth
buffer of :mod:`.visibility`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Warm greys (alcohol markers): the light one, and the dark one laid over.
LIGHT_GREY = (196, 190, 181)
DARK_GREY = (150, 144, 136)
#: Cast shadows: a cool grey, as in a marker sketch.
SHADOW_GREY = (140, 148, 160)
#: High contrast: the shade and the shadows near black.
CONTRAST_DARK = (92, 90, 88)
CONTRAST_SHADOW = (70, 74, 84)
COLOUR_MODES = ("colour", "greys", "contrast", "none")
#: A material's lightness below which it reads dark, and mid.
DARK_TONE, MID_TONE = 0.42, 0.68
LIGHTS = ("classic", "sun")
MEDIUMS = ("marker", "watercolour")


@dataclass
class MarkerStyle:
    """``offset`` and ``width`` in pixels at the reference height (1000)."""
    enabled: bool = True
    light: str = "classic"        # from the upper left, or the model's sun
    offset: float = 12.0          # how far the fill sits off the lines
    width: float = 26.0           # the marker's nib
    strength: float = 1.0         # 0..1.5, how much grey
    shadows: bool = True          # cast shadows, in cool grey
    colour: bool = True           # the materials (see colour_mode)
    colour_mode: str = "colour"   # colour, greys, contrast or none
    medium: str = "marker"        # or "watercolour"
    hatching: bool = False        # the shade in ink
    hatch_along: bool = True      # hatching along the faces (or diagonal)
    hatch_turn: float = 0.0       # degrees added to the hatching
    natural: bool = False         # each area its own turn of the hand
    ink_texture: bool = False     # high contrast: a dry brush's edge


def triangle_normals(tris: np.ndarray) -> np.ndarray:
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln < 1e-20] = 1.0
    return n / ln[:, None]



#: ``(scene) -> (x, y, z)`` toward the host's sun, or None (night): IngeTrazo's
#: Shadows panel (croquis/host.py). A scene's own ``croquis_sun()`` wins.
SUN = None

def light_direction(camera, scene, kind: str):
    """Unit vector toward the light, in world axes. ``classic``: from the
    upper left and a little behind the viewer, the sketcher's habit, so the
    drawing always reads; ``sun``: the sun of IngeTrazo's Shadows panel
    (the classic light when it is night there), or the one a scene's own
    ``croquis_sun()`` gives (Blender's Sun lamp)."""
    if kind == "sun":
        # A host other than IngeTrazo (Blender) says where its sun is.
        own = getattr(scene, "croquis_sun", None)
        if callable(own):
            d = own()
        else:
            try:
                d = SUN(scene) if SUN is not None else None
            except Exception:            # noqa: BLE001 (older IngeTrazo)
                d = None
        if d is not None:
            v = np.array(d, dtype=np.float64)
            return v / max(np.linalg.norm(v), 1e-12)
    f = camera.forward()
    u = camera.up_vector()
    fwd = np.array([f.x(), f.y(), f.z()])
    up = np.array([u.x(), u.y(), u.z()])
    right = np.cross(fwd, up)
    right /= max(np.linalg.norm(right), 1e-12)
    v = -0.62 * right + 0.70 * up - 0.35 * fwd
    return v / np.linalg.norm(v)


def face_values(index: np.ndarray, tris: np.ndarray, camera, light) -> tuple:
    """``(values, plane)`` images: 0 paper, 1 light grey, 2 dark grey, -1
    background; and an id per plane (faces in one plane share it), -1 for
    the background."""
    normals = triangle_normals(tris)
    # Two-sided: every face turned toward the eye.
    if camera.perspective:
        e = camera.eye()
        sight = tris.mean(axis=1) - np.array([e.x(), e.y(), e.z()])
    else:
        f = camera.forward()
        sight = np.broadcast_to(np.array([f.x(), f.y(), f.z()]), normals.shape)
    flip = np.einsum("ij,ij->i", normals, sight) > 0
    normals[flip] *= -1.0
    lit = normals @ light
    value = np.where(lit > 0.45, 0, np.where(lit > -0.05, 1, 2)).astype(np.int8)
    # A plane: its normal and its distance from the origin, rounded.
    dist = np.einsum("ij,ij->i", normals, tris[:, 0])
    key = np.round(np.c_[normals * 50.0, dist * 20.0]).astype(np.int64)
    _u, plane_of = np.unique(key, axis=0, return_inverse=True)
    plane_of = plane_of.reshape(-1)
    bg = index < 0
    ix = np.where(bg, 0, index)
    values = np.where(bg, -1, value[ix]).astype(np.int8)
    plane = np.where(bg, -1, plane_of[ix]).astype(np.int64)
    return values, plane, normals, plane_of


def _screen_angle(camera, M, width, height, p, d):
    from . import visibility as vis
    a = vis.to_clip(np.array([p, p + d]), M)
    if (a[:, 3] <= 1e-9).any():
        return None
    x, y, _q = vis._screen(a, width, height, bool(camera.perspective))
    return math.atan2(y[1] - y[0], x[1] - x[0])


def level_angle(camera, M, width: int, height: int) -> float:
    """The strokes' direction on a floor or a roof: along whichever of its
    world axes runs flatter on the paper."""
    t = camera.target
    centre = np.array([t.x(), t.y(), t.z()])
    cand = [c for c in (_screen_angle(camera, M, width, height, centre, np.array([1.0, 0, 0])),
                        _screen_angle(camera, M, width, height, centre, np.array([0, 1.0, 0])))
            if c is not None]
    return min(cand, key=lambda c: abs(math.sin(c))) if cand else 0.0


def long_axis_angles(plane: np.ndarray, angles: np.ndarray,
                     ratio: float = 2.2) -> np.ndarray:
    """Turn the strokes of every long, narrow area (a board, a slat, a
    beam as seen) along its length: the main axis of its pixels, when it is
    ``ratio`` times longer than wide. Squarer areas keep ``angles``."""
    n = len(angles)
    ids = plane[plane >= 0]
    if not len(ids):
        return angles
    ys, xs = np.nonzero(plane >= 0)
    cnt = np.bincount(ids, minlength=n).astype(np.float64)
    ok = cnt > 30
    cnt[cnt == 0] = 1.0
    mx = np.bincount(ids, xs, minlength=n) / cnt
    my = np.bincount(ids, ys, minlength=n) / cnt
    dx, dy = xs - mx[ids], ys - my[ids]
    cxx = np.bincount(ids, dx * dx, minlength=n) / cnt
    cyy = np.bincount(ids, dy * dy, minlength=n) / cnt
    cxy = np.bincount(ids, dx * dy, minlength=n) / cnt
    tr = cxx + cyy
    det = cxx * cyy - cxy * cxy
    disc = np.sqrt(np.maximum(tr * tr / 4 - det, 0.0))
    l1, l2 = tr / 2 + disc, np.maximum(tr / 2 - disc, 1e-9)
    long = ok & (l1 / l2 > ratio * ratio)
    axis = 0.5 * np.arctan2(2 * cxy, cxx - cyy)
    out = angles.copy()
    out[long[:n]] = axis[:n][long[:n]]
    return out


def stroke_angles(normals: np.ndarray, plane_of: np.ndarray, n_planes: int,
                  camera, M: np.ndarray, width: int, height: int) -> np.ndarray:
    """The marker's direction on screen for each plane, radians: up a wall
    (the world's vertical, as drawn), and across a floor or a roof along
    whichever of its world axes runs flatter on the paper."""
    from . import visibility as vis
    angle = np.zeros(max(1, n_planes))
    if not len(plane_of):
        return angle
    first = np.full(max(1, n_planes), -1)
    first[plane_of[::-1]] = np.arange(len(plane_of))[::-1]
    t = camera.target
    centre = np.array([t.x(), t.y(), t.z()])
    persp = bool(camera.perspective)

    def screen_angle(p, d):
        a = vis.to_clip(np.array([p, p + d]), M)
        if (a[:, 3] <= 1e-9).any():
            return None
        x, y, _q = vis._screen(a, width, height, persp)
        return math.atan2(y[1] - y[0], x[1] - x[0])

    # Measured at the camera's target, so the same two for every plane: up
    # a wall, and across a floor. Once, not once per plane (411 000 planes
    # took 19 s).
    up = screen_angle(centre, np.array([0.0, 0.0, 1.0]))
    wall = up if up is not None else math.pi / 2
    ax = screen_angle(centre, np.array([1.0, 0.0, 0.0]))
    ay = screen_angle(centre, np.array([0.0, 1.0, 0.0]))
    cand = [c for c in (ax, ay) if c is not None]
    floor = min(cand, key=lambda c: abs(math.sin(c))) if cand else 0.0
    seen = first >= 0
    is_wall = np.abs(normals[np.maximum(first, 0), 2]) < 0.7
    angle[seen & is_wall] = wall
    angle[seen & ~is_wall] = floor
    return angle


def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    if r < 1:
        return a
    k = 2 * r + 1
    p = np.pad(a, r, mode="edge")
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def _shift(a: np.ndarray, dx: int, dy: int, fill) -> np.ndarray:
    out = np.full_like(a, fill)
    h, w = a.shape
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    out[yd, xd] = a[ys, xs]
    return out


def _noise(shape, cell: float, seed: int) -> np.ndarray:
    """Smooth noise in 0..1 with features about ``cell`` pixels wide."""
    h, w = shape
    rng = np.random.default_rng(seed)
    gh, gw = int(h / cell) + 3, int(w / cell) + 3
    g = rng.random((gh, gw))
    ys = np.linspace(0, gh - 2.001, h)
    xs = np.linspace(0, gw - 2.001, w)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def _marker_pass(soft: np.ndarray, angle_px: np.ndarray, plane: np.ndarray,
                 nib: float, seed: int, skip: float = 0.0, grid=None,
                 streak=None) -> np.ndarray:
    """How much ink one pass of the marker leaves at each pixel (0..1):
    parallel strokes ``nib`` wide at ``angle_px`` (per pixel), overlapping a
    little, each stroke a touch lighter or darker, over the blurred fill
    ``soft``. Each stroke stops at its own point near the edge of the fill:
    some fall short, some run past. ``skip``: the share of strokes left out,
    so the paper shows between them (a lit face done quickly)."""
    h, w = soft.shape
    yy, xx = grid if grid is not None else np.mgrid[0:h, 0:w].astype(np.float64)
    # Across the strokes: the coordinate normal to their direction.
    u = -xx * np.sin(angle_px) + yy * np.cos(angle_px)
    spacing = nib * 0.82
    band = np.floor(u / spacing).astype(np.int64)
    local = u - band * spacing
    overlap = local < (nib - spacing)
    # Each stroke its own density (hash of the band and the plane).
    hsh = (band * 73856093) ^ (plane * 19349663) ^ seed
    dens = 0.80 + 0.20 * ((hsh & 1023) / 1023.0)
    reach = (((hsh >> 10) & 1023) / 1023.0 - 0.5) * 0.5
    cover = np.clip((soft + reach - 0.42) / 0.12, 0.0, 1.0)
    if skip > 0:
        cover = cover * (((hsh >> 20) & 1023) / 1023.0 >= skip)
    # The strokes' own streaks: lighter and darker along each one.
    if streak is None:
        streak = _noise((h, w), nib * 0.35, seed + 5)
    else:                                # the shared field, moved per pass
        streak = np.roll(streak, (seed * 37) % max(1, streak.shape[0]), axis=0)
    streak = 0.88 + 0.12 * streak
    ink = dens * streak * np.where(overlap, 1.45, 1.0)
    return np.clip(cover * ink, 0.0, 1.0)


def tone_masks(tone, col, mode: str):
    """``(mid, dark)`` bool images: the faces whose material reads mid or
    dark. In colour mode only the materials with no marker (greys,
    blacks); in greys mode, every material."""
    if tone is None or mode not in ("colour", "greys"):
        return None, None
    eligible = tone >= 0
    if mode == "colour" and col is not None:
        eligible &= col < 0
    dark = eligible & (tone < DARK_TONE)
    mid = eligible & (tone >= DARK_TONE) & (tone < MID_TONE)
    return mid, dark


def colour_mode(style) -> str:
    return style.colour_mode if style.colour else "none"


def paint(base: np.ndarray, values: np.ndarray, plane: np.ndarray,
          angles: np.ndarray, style: MarkerStyle, scale: float,
          colour: np.ndarray | None = None, tone: np.ndarray | None = None,
          jitter: np.ndarray | None = None) -> np.ndarray:
    """Lay the markers on ``base`` (H, W, 3 floats 0..255): the colours
    first (``colour``: a marker index per pixel, -1 none), the greys over
    them; ``values`` 0 lit, 1 turned, 2 away, 3 cast shadow, -1 nothing;
    ``tone``: the material's lightness per pixel (-1 none), so a dark
    material is laid dark whatever the light. ``jitter``: per plane, a
    turn of the strokes (radians), for a less even hand.
    The fills shifted by the offset, with ragged edges; multiplied, as a
    marker's ink is."""
    if not style.enabled:
        return base
    h, w = values.shape
    dx = int(round(style.offset * scale * 0.8))
    dy = int(round(style.offset * scale * 0.6))
    vals = _shift(values, dx, dy, -1)
    pl = _shift(plane, dx, dy, -1)
    ang = angles if jitter is None else angles + jitter[:len(angles)]
    angle_px = np.where(pl >= 0, ang[np.clip(pl, 0, len(ang) - 1)], ang[-1])
    mode = colour_mode(style)
    rough = _noise((h, w), 18.0 * scale, 11)
    r = max(1, int(round(3.0 * scale)))
    out = base.copy()
    nib = max(4.0, style.width * scale)
    grid = np.mgrid[0:h, 0:w].astype(np.float64)
    streak = _noise((h, w), nib * 0.35, 5)

    def lay(ind, tint, seed, turn, strength, skip=0.0):
        rows = np.nonzero(ind.any(axis=1))[0]
        if not len(rows):
            return
        cols = np.nonzero(ind.any(axis=0))[0]
        # Only the box the fill takes, and a margin for its ragged edge.
        m = r + 2
        y0, y1 = max(0, rows[0] - m), min(h, rows[-1] + m + 1)
        x0, x1 = max(0, cols[0] - m), min(w, cols[-1] + m + 1)
        box = (slice(y0, y1), slice(x0, x1))
        soft = _box_blur(ind[box], r) + (rough[box] - 0.5) * 0.25
        ink = _marker_pass(soft, angle_px[box] + turn, pl[box], nib, seed, skip,
                           (grid[0][box], grid[1][box]), streak[box])
        alpha = np.clip(ink * strength, 0.0, 1.0)[:, :, None]
        t = np.array(tint, dtype=np.float64)[None, None, :] / 255.0
        out[box] *= 1.0 - alpha * (1.0 - t)

    col = _shift(colour, dx, dy, -1) if colour is not None else None
    if col is not None and mode == "colour":
        from .palette import MARKERS
        for k in np.unique(col[col >= 0]):
            here = col == k
            # Where the light falls, the colour goes on lighter and quicker:
            # some strokes left out, the paper showing between them.
            lit = here & (vals == 0)
            lay(lit.astype(np.float64), MARKERS[int(k)], 101 + int(k), -0.05,
                0.6, skip=0.4)
            lay((here & ~lit).astype(np.float64), MARKERS[int(k)], 131 + int(k),
                -0.05, 0.85)
    mid, dark = tone_masks(_shift(tone, dx, dy, -1.0) if tone is not None else None,
                           col, mode)
    if mid is not None:
        # The material's own tone: a dark one dark, a mid one grey, lit or not.
        lay((mid | dark).astype(np.float64), LIGHT_GREY, 71, 0.03, 0.62 * style.strength)
        lay(dark.astype(np.float64), DARK_GREY, 73, -0.08, 0.7 * style.strength)
        lay(dark.astype(np.float64), DARK_GREY, 79, 0.1, 0.55 * style.strength)
    if mode == "contrast":
        passes = [(lambda v: v == 2, CONTRAST_DARK, 37, 0.12),
                  (lambda v: v == 2, CONTRAST_DARK, 41, -0.1),
                  (lambda v: v == 3, CONTRAST_SHADOW, 53, 0.06),
                  (lambda v: v == 3, CONTRAST_SHADOW, 59, -0.1)]
    else:
        passes = [(lambda v: (v == 1) | (v == 2), LIGHT_GREY, 21, 0.0),
                  (lambda v: v == 2, DARK_GREY, 37, 0.12),
                  (lambda v: v == 3, SHADOW_GREY, 53, 0.06),
                  (lambda v: v == 3, SHADOW_GREY, 59, -0.1)]
    for test, grey, seed, turn in passes:
        ind = test(vals).astype(np.float64)
        if not ind.any():
            continue
        lay(ind, grey, seed, turn, 0.62 * style.strength)
    return out
