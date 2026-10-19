# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Cast shadows: which of the pixels the view shows the light cannot reach.

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


def pixel_points(view, index: np.ndarray, normals: np.ndarray, tris: np.ndarray):
    """World point of every model pixel of the view (where ``index`` ≥ 0),
    as (K, 3), plus the pixels' (row, col): the sight ray through the pixel
    centre, met with the plane of the triangle seen there."""
    rows, cols = np.nonzero(index >= 0)
    if not len(rows):
        return np.empty((0, 3)), rows, cols
    h, w = index.shape
    Minv = np.linalg.inv(view.M)
    nx = (cols + 0.5) / w * 2.0 - 1.0
    ny = 1.0 - (rows + 0.5) / h * 2.0

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


def cast_shadow(view, normals: np.ndarray, light: np.ndarray) -> np.ndarray:
    """(H, W) bools of the view: the model's pixels the light does not reach
    because something stands between them and it. ``normals``: per
    triangle, turned toward the eye."""
    index, tris = view.index, view.tris
    shadow = np.zeros(index.shape, dtype=bool)
    if not len(tris):
        return shadow
    L = light / max(np.linalg.norm(light), 1e-12)
    M, texel = light_matrix(tris, L)
    smap, _sidx = vis.depth_buffer(tris, M, MAP_SIZE, MAP_SIZE, persp=False)
    P, rows, cols = pixel_points(view, index, normals, tris)
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
    c = P @ M[:, :3].T + M[:, 3]
    x = ((c[:, 0] * 0.5 + 0.5) * MAP_SIZE).astype(np.int64)
    y = ((0.5 - c[:, 1] * 0.5) * MAP_SIZE).astype(np.int64)
    q = -c[:, 2]
    inside = (x >= 0) & (x < MAP_SIZE) & (y >= 0) & (y < MAP_SIZE)
    blocked = np.zeros(len(P), dtype=bool)
    xi, yi = np.clip(x, 0, MAP_SIZE - 1), np.clip(y, 0, MAP_SIZE - 1)
    blocked[inside] = smap[yi[inside], xi[inside]] > q[inside] + 1e-6
    shadow[rows, cols] = blocked & (facing > 0.02)
    return shadow
