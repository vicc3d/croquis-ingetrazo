# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Light and shade laid in with grey markers, as in a quick sketch.

Every face gets one of three values by how the light falls on it: the white
of the paper where it is lit, a light grey where it turns from the light, a
darker grey where it faces away. A sketcher does not shade more finely than
that.

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
LIGHTS = ("classic", "sun")


@dataclass
class MarkerStyle:
    """``offset`` and ``width`` in pixels at the reference height (1000)."""
    enabled: bool = True
    light: str = "classic"        # from the upper left, or the model's sun
    offset: float = 12.0          # how far the fill sits off the lines
    width: float = 26.0           # the marker's nib
    strength: float = 1.0         # 0..1.5, how much grey


def triangle_normals(tris: np.ndarray) -> np.ndarray:
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln < 1e-20] = 1.0
    return n / ln[:, None]


def light_direction(camera, scene, kind: str):
    """Unit vector toward the light, in world axes. ``classic``: from the
    upper left and a little behind the viewer, the sketcher's habit, so the
    drawing always reads; ``sun``: the sun of IngeTrazo's Shadows panel
    (the classic light when it is night there)."""
    if kind == "sun":
        try:
            from core.render_blender import sun_toward
            d = sun_toward(scene)
        except Exception:                # noqa: BLE001 (older IngeTrazo)
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


def stroke_angles(normals: np.ndarray, plane_of: np.ndarray, n_planes: int,
                  camera, M: np.ndarray, width: int, height: int) -> np.ndarray:
    """The marker's direction on screen for each plane, radians: up a wall
    (the world's vertical, as drawn), and across a floor or a roof along
    whichever of its world axes runs flatter on the paper."""
    from . import visibility as vis
    angle = np.zeros(max(1, n_planes))
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

    for k in range(n_planes):
        i = first[k]
        if i < 0:
            continue
        n = normals[i]
        if abs(n[2]) < 0.7:                  # a wall: up it
            a = screen_angle(centre, np.array([0.0, 0.0, 1.0]))
        else:                                 # a floor or a roof
            ax = screen_angle(centre, np.array([1.0, 0.0, 0.0]))
            ay = screen_angle(centre, np.array([0.0, 1.0, 0.0]))
            cand = [c for c in (ax, ay) if c is not None]
            a = min(cand, key=lambda c: abs(math.sin(c))) if cand else 0.0
        angle[k] = a if a is not None else math.pi / 2
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
                 nib: float, seed: int) -> np.ndarray:
    """How much ink one pass of the marker leaves at each pixel (0..1):
    parallel strokes ``nib`` wide at ``angle_px`` (per pixel), overlapping a
    little, each stroke a touch lighter or darker, over the blurred fill
    ``soft``. Each stroke stops at its own point near the edge of the fill:
    some fall short, some run past."""
    h, w = soft.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
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
    # The strokes' own streaks: lighter and darker along each one.
    streak = 0.88 + 0.12 * _noise((h, w), nib * 0.35, seed + 5)
    ink = dens * streak * np.where(overlap, 1.45, 1.0)
    return np.clip(cover * ink, 0.0, 1.0)


def paint(base: np.ndarray, values: np.ndarray, plane: np.ndarray,
          angles: np.ndarray, style: MarkerStyle, scale: float) -> np.ndarray:
    """Lay the greys on ``base`` (H, W, 3 floats 0..255): the fills shifted
    by the offset, with ragged edges; multiplied, as a marker's ink is."""
    if not style.enabled:
        return base
    h, w = values.shape
    dx = int(round(style.offset * scale * 0.8))
    dy = int(round(style.offset * scale * 0.6))
    vals = _shift(values, dx, dy, -1)
    pl = _shift(plane, dx, dy, -1)
    angle_px = np.where(pl >= 0, angles[np.clip(pl, 0, len(angles) - 1)], 0.0)
    rough = _noise((h, w), 18.0 * scale, 11)
    r = max(1, int(round(5.0 * scale)))
    out = base.copy()
    nib = max(4.0, style.width * scale)
    for level, grey, seed, turn in ((1, LIGHT_GREY, 21, 0.0), (2, DARK_GREY, 37, 0.12)):
        ind = (vals >= level).astype(np.float64)
        if not ind.any():
            continue
        soft = _box_blur(ind, r) + (rough - 0.5) * 0.3
        ink = _marker_pass(soft, angle_px + turn, pl, nib, seed)
        alpha = np.clip(ink * 0.62 * style.strength, 0.0, 1.0)[:, :, None]
        tint = np.array(grey, dtype=np.float64)[None, None, :] / 255.0
        out *= 1.0 - alpha * (1.0 - tint)
    return out
