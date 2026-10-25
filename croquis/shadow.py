# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Cast shadows: which of the pixels the view shows the light cannot reach.

The ground: as a modeller's own view does, the shadows also fall on a
level ground under the model (at its foot, or at zero) even when the model has
no floor of its own.

A shadow map: the model's triangles drawn into a depth buffer seen from the
light (a parallel view along it, as the sun's rays are), with the same
rasteriser as the view (:mod:`.visibility`). Every pixel of the view is
taken back to its point on the model, and that point is in shadow when the
light's buffer has something nearer the light in front of it.
"""
from __future__ import annotations

import numpy as np

from . import visibility as vis

#: The shadow map's longer side, in texels.
MAP_SIZE = 1024


def light_matrix(tris: np.ndarray, light: np.ndarray):
    """A parallel "clip" matrix looking along ``-light`` that frames every
    triangle, as ``(M, texel)``: texel = the world size of one texel."""
    L = light / max(np.linalg.norm(light), 1e-12)
    a = np.array([0.0, 0.0, 1.0]) if abs(L[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(a, L)
    u /= np.linalg.norm(u)
    v = np.cross(L, u)
    pts = tris.reshape(-1, 3)
    su, sv, sd = pts @ u, pts @ v, pts @ L
    cu, cv, cd = (su.min() + su.max()) / 2, (sv.min() + sv.max()) / 2, (sd.min() + sd.max()) / 2
    hu = max((su.max() - su.min()) / 2, 1e-6) * 1.01
    hv = max((sv.max() - sv.min()) / 2, 1e-6) * 1.01
    hd = max((sd.max() - sd.min()) / 2, 1e-6) * 1.05
    # x_ndc = (p·u - cu)/hu, y_ndc = (p·v - cv)/hv, z_ndc = -(p·L - cd)/hd:
    # nearness q = -z_ndc grows toward the light.
    M = np.zeros((4, 4))
    M[0, :3], M[0, 3] = u / hu, -cu / hu
    M[1, :3], M[1, 3] = v / hv, -cv / hv
    M[2, :3], M[2, 3] = -L / hd, cd / hd
    M[3, 3] = 1.0
    return M, max(hu, hv) * 2.0 / MAP_SIZE


def pixel_points(view, index: np.ndarray, normals: np.ndarray, tris: np.ndarray,
                 at=(0.5, 0.5)):
    """World point of every model pixel of the view (where ``index`` ≥ 0),
    as (K, 3), plus the pixels' (row, col): the sight ray through the point
    ``at`` of the pixel (its centre by default), met with the plane of the
    triangle seen there."""
    rows, cols = np.nonzero(index >= 0)
    if not len(rows):
        return np.empty((0, 3)), rows, cols
    h, w = index.shape
    Minv = np.linalg.inv(view.M)
    nx = (cols + at[0]) / w * 2.0 - 1.0
    ny = 1.0 - (rows + at[1]) / h * 2.0

    def unproject(z):
        c = np.stack([nx, ny, np.full_like(nx, z), np.ones_like(nx)], axis=1)
        p = c @ Minv.T
        return p[:, :3] / p[:, 3:4]

    A, B = unproject(-1.0), unproject(1.0)
    t_idx = index[rows, cols]
    n = normals[t_idx]
    d = np.einsum("ij,ij->i", n, tris[t_idx, 0])
    D = B - A
    den = np.einsum("ij,ij->i", n, D)
    den = np.where(np.abs(den) < 1e-15, 1e-15, den)
    t = (d - np.einsum("ij,ij->i", n, A)) / den
    return A + t[:, None] * D, rows, cols


def _blocked(P: np.ndarray, M: np.ndarray, smap: np.ndarray) -> np.ndarray:
    c = P @ M[:, :3].T + M[:, 3]
    x = ((c[:, 0] * 0.5 + 0.5) * MAP_SIZE).astype(np.int64)
    y = ((0.5 - c[:, 1] * 0.5) * MAP_SIZE).astype(np.int64)
    q = -c[:, 2]
    inside = (x >= 0) & (x < MAP_SIZE) & (y >= 0) & (y < MAP_SIZE)
    out = np.zeros(len(P), dtype=bool)
    xi, yi = np.clip(x, 0, MAP_SIZE - 1), np.clip(y, 0, MAP_SIZE - 1)
    out[inside] = smap[yi[inside], xi[inside]] > q[inside] + 1e-6
    return out


def ground_level(tris: np.ndarray) -> float:
    """The ground's height: the model's foot, or zero if that is higher
    (where a render usually puts its ground)."""
    return min(float(tris[:, :, 2].min()), 0.0) if len(tris) else 0.0


def shadow_map(tris: np.ndarray, light: np.ndarray):
    """``(M, texel, smap)``: the light's matrix, a texel's world size and
    the depth buffer seen from the light, shared by the model's and the
    ground's shadows."""
    L = light / max(np.linalg.norm(light), 1e-12)
    M, texel = light_matrix(tris, L)
    smap, _sidx = vis.depth_buffer(tris, M, MAP_SIZE, MAP_SIZE, persp=False)
    return M, texel, smap


def ground_shadow(view, light: np.ndarray, reach: float = 4.0, pack=None,
                  at=(0.5, 0.5)) -> np.ndarray:
    """(H, W) bools: the background pixels where the view sees the level
    ground (:func:`ground_level`), no farther than ``reach`` times the
    model's size from it, and the model shades it."""
    index, tris = view.index, view.tris
    h, w = index.shape
    out = np.zeros((h, w), dtype=bool)
    if not len(tris) or light[2] <= 1e-3:
        return out
    L = light / max(np.linalg.norm(light), 1e-12)
    rows, cols = np.nonzero(index < 0)
    if not len(rows):
        return out
    z0 = ground_level(tris)
    Minv = np.linalg.inv(view.M)
    nx = (cols + at[0]) / w * 2.0 - 1.0
    ny = 1.0 - (rows + at[1]) / h * 2.0

    def unproject(z):
        c = np.stack([nx, ny, np.full_like(nx, z), np.ones_like(nx)], axis=1)
        p = c @ Minv.T
        return p[:, :3] / p[:, 3:4]

    A, B = unproject(-1.0), unproject(1.0)
    dz = B[:, 2] - A[:, 2]
    t = np.where(np.abs(dz) > 1e-12, (z0 - A[:, 2]) / np.where(np.abs(dz) > 1e-12, dz, 1.0), -1.0)
    hit = (t > 0.0) & (t < 1.0)
    P = A + t[:, None] * (B - A)
    pts = tris.reshape(-1, 3)
    centre = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
    size = max(float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))), 1e-6)
    hit &= np.linalg.norm(P[:, :2] - centre[:2], axis=1) < reach * size
    if not hit.any():
        return out
    M, texel, smap = pack if pack is not None else shadow_map(tris, L)
    P = P[hit] + np.array([0.0, 0.0, 2.0 * texel]) + L * texel
    out[rows[hit], cols[hit]] = _blocked(P, M, smap)
    return out


def cast_shadow(view, normals: np.ndarray, light: np.ndarray, pack=None,
                at=(0.5, 0.5)) -> np.ndarray:
    """(H, W) bools of the view: the model's pixels the light does not reach
    because something stands between them and it. ``normals``: per
    triangle, turned toward the eye."""
    index, tris = view.index, view.tris
    shadow = np.zeros(index.shape, dtype=bool)
    if not len(tris):
        return shadow
    L = light / max(np.linalg.norm(light), 1e-12)
    M, texel, smap = pack if pack is not None else shadow_map(tris, L)
    P, rows, cols = pixel_points(view, index, normals, tris, at)
    if not len(P):
        return shadow
    # Only what faces the light can be shadowed by something else; the
    # rest is in its own shade already.
    n = normals[index[rows, cols]]
    facing = n @ L
    n = np.where((facing < 0)[:, None], -n, n)
    # Lifted off its surface by a couple of texels, so a face does not
    # shadow itself.
    P = P + n * (2.0 * texel) + L * (1.0 * texel)
    shadow[rows, cols] = _blocked(P, M, smap) & (facing > 0.02)
    return shadow


#: Where in a pixel the shadow is looked at: four points, not the centre
#: alone (see :func:`settled`).
SAMPLES = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))


def settled(shade, region: np.ndarray) -> np.ndarray:
    """A shadow that a hand would draw, from ``shade(at)`` (the (H, W)
    bools of a shadow looked at the point ``at`` of every pixel): looked
    at four points of each pixel, the share in shadow averaged with the
    pixels around within ``region`` (the model, or the ground), and shadow
    where half or more is. A railing's bars cast stripes finer than the
    pixels: looked at once per pixel they came out as a grid of dots (a
    moiré); averaged they give the band one shade. A shadow wider than a
    pixel or two keeps its edge where it was."""
    from .marker import _box_blur
    cover = sum(shade(at).astype(np.float64) for at in SAMPLES) / len(SAMPLES)
    reg = region.astype(np.float64)
    share = _box_blur(cover * reg, 1) / np.maximum(_box_blur(reg, 1), 1e-9)
    return region & (share >= 0.5)

