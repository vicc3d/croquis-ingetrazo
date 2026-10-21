# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""A Blender scene seen as Croquis sees IngeTrazo's viewport.

Croquis draws from a few things only: the camera (its two matrices, where
it stands and looks), the model's triangles with each one's colour, the
edges to draw (hard ones always, soft ones where the surface turns away),
and the sun. :class:`BlenderView` gathers them from the scene once, on the
main thread, with NumPy over each mesh's arrays; the drawing then runs on
it exactly as in IngeTrazo.

Which edges: an edge between two faces is drawn when they meet at a real
angle (more than :data:`HARD_ANGLE`), when it is marked sharp, at the
border of a surface, or loose; between faces that turn a little (a
cylinder's sides) it is soft, drawn where it is the silhouette; between
flat neighbours (a triangulated face) it is not drawn at all.
"""
from __future__ import annotations

import math

import numpy as np

#: Faces meeting at more than this (degrees) make an edge a hand draws.
HARD_ANGLE = 30.0
#: Less than this, the faces are one flat surface.
FLAT_ANGLE = 0.5
#: Croquis's default face: no paint of its own.
DEFAULT_FACE_COLOR = (0.96, 0.95, 0.925)


class _V:
    """What Croquis asks of a point or a direction: x(), y(), z()."""

    __slots__ = ("v",)

    def __init__(self, v) -> None:
        self.v = (float(v[0]), float(v[1]), float(v[2]))

    def x(self) -> float:
        return self.v[0]

    def y(self) -> float:
        return self.v[1]

    def z(self) -> float:
        return self.v[2]


class _M:
    """A 4×4 matrix as Croquis multiplies and reads it (``data()`` in
    columns, as Qt gives it)."""

    def __init__(self, m) -> None:
        self.m = np.array(m, dtype=np.float64).reshape(4, 4)

    def __mul__(self, other: "_M") -> "_M":
        return _M(self.m @ other.m)

    def data(self) -> list:
        return list(self.m.T.reshape(-1))


class Camera:
    """A camera Croquis can draw from: the projection (OpenGL's, which is
    Blender's too) and the view, where it stands, where it looks, which
    way is up, and the width over the height of the picture."""

    def __init__(self, projection, view, perspective: bool, aspect: float) -> None:
        self._p = _M(projection)
        self._v = _M(view)
        self.perspective = perspective
        self.aspect = aspect
        inv = np.linalg.inv(self._v.m)
        self._eye = inv[:3, 3]
        self._fwd = -inv[:3, 2] / max(np.linalg.norm(inv[:3, 2]), 1e-12)
        self._up = inv[:3, 1] / max(np.linalg.norm(inv[:3, 1]), 1e-12)
        self.target = _V(self._eye + self._fwd * 10.0)

    def projection_matrix(self) -> _M:
        return self._p

    def view_matrix(self) -> _M:
        return self._v

    def eye(self) -> _V:
        return _V(self._eye)

    def forward(self) -> _V:
        return _V(self._fwd)

    def up_vector(self) -> _V:
        return _V(self._up)

    def aim_at(self, points: np.ndarray) -> None:
        """The target at the depth of ``points`` (the model): where the
        strokes' directions are measured."""
        if not len(points):
            return
        d = float(np.median((points - self._eye) @ self._fwd))
        self.target = _V(self._eye + self._fwd * max(d, 1e-3))


def camera_from_object(cam_obj, depsgraph, scene) -> Camera:
    """The scene's camera, at the render's size and pixel shape."""
    r = scene.render
    x = max(1, int(r.resolution_x * r.resolution_percentage / 100))
    y = max(1, int(r.resolution_y * r.resolution_percentage / 100))
    proj = cam_obj.calc_matrix_camera(depsgraph, x=x, y=y,
                                      scale_x=r.pixel_aspect_x,
                                      scale_y=r.pixel_aspect_y)
    view = cam_obj.matrix_world.inverted()
    return Camera(proj, view, cam_obj.data.type != "ORTHO",
                  (x * r.pixel_aspect_x) / (y * r.pixel_aspect_y))


def camera_from_view(region, rv3d) -> Camera:
    """What a 3D viewport shows, at its own shape."""
    return Camera(rv3d.window_matrix, rv3d.view_matrix, rv3d.is_perspective,
                  region.width / max(1, region.height))


# ---- Colour --------------------------------------------------------------

def _to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_image_avg: dict = {}


def _image_colour(image):
    """An image texture's average colour (sRGB), read once."""
    key = (image.name, image.size[0], image.size[1])
    if key not in _image_avg:
        try:
            px = np.empty(image.size[0] * image.size[1] * image.channels, np.float32)
            image.pixels.foreach_get(px)
            px = px.reshape(-1, image.channels)[:, :3]
            avg = px.mean(axis=0) if len(px) else np.array(DEFAULT_FACE_COLOR)
            # Float images hold linear light; byte ones are already sRGB.
            _image_avg[key] = (_to_srgb(avg) if image.is_float else avg)
        except Exception:                # noqa: BLE001 (an image not loaded)
            _image_avg[key] = None
    return _image_avg[key]


def material_colour(mat):
    """The colour a sketcher would read on a material, sRGB 0..1: its
    Principled BSDF's base colour (or the average of the image there), else
    its viewport colour. ``None`` for no material."""
    if mat is None:
        return None
    if mat.use_nodes and mat.node_tree is not None:
        for node in mat.node_tree.nodes:
            base = node.inputs.get("Base Color") if hasattr(node, "inputs") else None
            if base is None:
                continue
            if base.is_linked:
                src = base.links[0].from_node
                img = getattr(src, "image", None)
                if img is not None:
                    c = _image_colour(img)
                    if c is not None:
                        return tuple(float(v) for v in c)
                break
            return tuple(float(v) for v in _to_srgb(np.array(base.default_value[:3])))
    return tuple(float(v) for v in _to_srgb(np.array(mat.diffuse_color[:3])))


# ---- Geometry ------------------------------------------------------------

def _arr(coll, attr, n, width, dtype):
    out = np.empty(n * width, dtype=dtype)
    if n:
        coll.foreach_get(attr, out)
    return out.reshape(n, width) if width > 1 else out


def mesh_parts(mesh, matrix, cutouts=()):
    """One mesh in world space: ``(tris (T,3,3), tri_mat (T,), hard (E,2,3),
    soft (S,2,3), soft_n (S,2,3))``. The faces of the material slots in
    ``cutouts`` (pictures on a sheet) are left out, and the edges that
    bound only them."""
    m = np.array(matrix, dtype=np.float64).reshape(4, 4)
    L, t = m[:3, :3], m[:3, 3]
    nv = len(mesh.vertices)
    co = _arr(mesh.vertices, "co", nv, 3, np.float32).astype(np.float64) @ L.T + t
    mesh.calc_loop_triangles()
    nt = len(mesh.loop_triangles)
    tv = _arr(mesh.loop_triangles, "vertices", nt, 3, np.int32)
    tmat = _arr(mesh.loop_triangles, "material_index", nt, 1, np.int32)
    pmat = _arr(mesh.polygons, "material_index", len(mesh.polygons), 1, np.int32)
    gone = np.isin(pmat, list(cutouts)) if len(cutouts) else np.zeros(len(pmat), bool)
    if gone.any() and nt:
        tpoly = _arr(mesh.loop_triangles, "polygon_index", nt, 1, np.int32)
        keep_t = ~gone[tpoly]
        tv, tmat = tv[keep_t], tmat[keep_t]
        nt = len(tv)
    tris = co[tv] if nt else np.zeros((0, 3, 3))
    # Each edge's faces, from the loops.
    ne, npoly, nl = len(mesh.edges), len(mesh.polygons), len(mesh.loops)
    ev = _arr(mesh.edges, "vertices", ne, 2, np.int32)
    loop_edge = _arr(mesh.loops, "edge_index", nl, 1, np.int32)
    start = _arr(mesh.polygons, "loop_start", npoly, 1, np.int32)
    total = _arr(mesh.polygons, "loop_total", npoly, 1, np.int32)
    pnorm = _arr(mesh.polygons, "normal", npoly, 3, np.float32).astype(np.float64)
    # Normals to world: by the inverse transpose.
    try:
        N = np.linalg.inv(L).T
    except np.linalg.LinAlgError:
        N = L
    pnorm = pnorm @ N.T
    pnorm /= np.maximum(np.linalg.norm(pnorm, axis=1), 1e-12)[:, None]
    loop_poly = np.repeat(np.arange(npoly), total) if npoly else np.zeros(0, np.int64)
    order = np.argsort(loop_edge, kind="stable")
    le, lp = loop_edge[order], loop_poly[order]
    count = np.bincount(le, minlength=ne) if ne else np.zeros(0, np.int64)
    first = np.full(ne, -1, np.int64)
    second = np.full(ne, -1, np.int64)
    if len(le):
        starts = np.r_[0, np.cumsum(count)[:-1]]
        has1 = count >= 1
        first[has1] = lp[starts[has1]]
        has2 = count >= 2
        second[has2] = lp[starts[has2] + 1]
    sharp = np.zeros(ne, bool)
    attr = mesh.attributes.get("sharp_edge")
    if attr is not None and attr.domain == "EDGE" and ne:
        attr.data.foreach_get("value", sharp)
    cos_hard = math.cos(math.radians(HARD_ANGLE))
    cos_flat = math.cos(math.radians(FLAT_ANGLE))
    dot = np.ones(ne)
    two = count == 2
    dot[two] = np.einsum("ij,ij->i", pnorm[first[two]], pnorm[second[two]])
    hard_e = (count != 2) | sharp | (dot < cos_hard)
    soft_e = ~hard_e & (dot < cos_flat)
    if gone.any():
        # An edge of a picture's sheet only: not drawn.
        kept = np.bincount(le, weights=(~gone[lp]).astype(np.float64),
                           minlength=ne) if len(le) else np.zeros(ne)
        only_gone = (count > 0) & (kept == 0)
        hard_e &= ~only_gone
        soft_e &= ~only_gone
    seg = co[ev] if ne else np.zeros((0, 2, 3))
    soft_n = np.stack([pnorm[first[soft_e]], pnorm[second[soft_e]]], axis=1) \
        if soft_e.any() else np.zeros((0, 2, 3))
    return tris, tmat, seg[hard_e], seg[soft_e], soft_n


def _alpha_from_image(mat) -> bool:
    """Whether the material's transparency comes from an image (a cut-out:
    a figure, a tree drawn on a plane)."""
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return False
    for node in mat.node_tree.nodes:
        alpha = node.inputs.get("Alpha") if hasattr(node, "inputs") else None
        if alpha is not None and alpha.is_linked:
            return True
    return False


def see_through(obj) -> bool:
    """A face-me figure IngeTrazo Sync marked as such: left out whole, as
    IngeTrazo's Croquis does."""
    own = getattr(obj, "original", obj)
    return bool(own.get("ingetrazo_billboard"))


#: A material on more faces than this is not a picture on a sheet.
CUTOUT_FACES = 16


def cutout_slots(obj, mesh) -> set:
    """The material slots that are pictures on a sheet (a figure, a tree
    on a plane): their transparency from an image, on a few faces in one
    plane. Drawn, such a sheet was a solid black rectangle; IngeTrazo's
    Croquis leaves its figures out, and so does this."""
    mats = [ms.material for ms in obj.material_slots] or list(mesh.materials)
    out = set()
    np_ = len(mesh.polygons)
    if not np_:
        return out
    pmat = _arr(mesh.polygons, "material_index", np_, 1, np.int32)
    normals = None
    for i, m in enumerate(mats):
        if not _alpha_from_image(m):
            continue
        sel = np.nonzero(pmat == i)[0]
        if not len(sel) or len(sel) > CUTOUT_FACES:
            continue
        if normals is None:
            normals = _arr(mesh.polygons, "normal", np_, 3, np.float32)
        n = normals[sel]
        if np.all(np.abs(n @ n[0]) > 0.999):
            out.add(i)
    return out


class BlenderView:
    """The scene as Croquis's drawing reads a viewport: ``camera``,
    ``scene`` (with the sun), ``hlr_geometry()`` and ``croquis_colours``."""

    DEFAULT_FACE_COLOR = DEFAULT_FACE_COLOR

    def __init__(self, context, depsgraph, camera: Camera) -> None:
        from .core import palette as pal
        self.camera = camera
        self.scene = _Sun(context.scene)
        tris, hard, soft, soft_n, marker, tone = [], [], [], [], [], []
        cache: dict = {}

        def colour_of(rgb):
            if rgb not in cache:
                cache[rgb] = (pal.nearest_marker(rgb), pal._lightness(rgb))
            return cache[rgb]

        for inst in depsgraph.object_instances:
            obj = inst.object
            if obj.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
                continue
            try:
                mesh = obj.data if obj.type == "MESH" else obj.to_mesh()
            except RuntimeError:
                continue
            if mesh is None:
                continue
            if see_through(obj):
                if obj.type != "MESH":
                    obj.to_mesh_clear()
                continue
            try:
                t, tm, h, s, sn = mesh_parts(mesh, inst.matrix_world,
                                             cutout_slots(obj, mesh))
                slots = [ms.material for ms in obj.material_slots] or list(mesh.materials)
                cols = [material_colour(mt) for mt in slots] or [None]
                per = np.array([colour_of(tuple(round(v, 3) for v in (c or DEFAULT_FACE_COLOR)))
                                for c in cols], dtype=np.float64)
                idx = np.clip(tm, 0, len(per) - 1)
                tris.append(t)
                marker.append(per[idx, 0].astype(np.int64))
                tone.append(per[idx, 1])
                hard.append(h)
                soft.append(s)
                soft_n.append(sn)
            finally:
                if obj.type != "MESH":
                    obj.to_mesh_clear()
        cat = lambda xs, shape: np.concatenate(xs) if xs else np.zeros(shape)  # noqa: E731
        self._tris = cat(tris, (0, 3, 3))
        self._geom = (self._tris, cat(hard, (0, 2, 3)), cat(soft, (0, 2, 3)),
                      cat(soft_n, (0, 2, 3)))
        self.croquis_colours = (self._tris, cat(marker, (0,)).astype(np.int64),
                                cat(tone, (0,)))
        camera.aim_at(self._tris.reshape(-1, 3)[::7])

    def hlr_geometry(self):
        return self._geom

    def __len__(self) -> int:
        return len(self._tris)


class _Sun:
    """The scene, as far as Croquis asks: where its sun is."""

    def __init__(self, scene) -> None:
        self._scene = scene

    def croquis_sun(self):
        """Toward the first visible Sun lamp, or ``None`` (then the classic
        light)."""
        for obj in self._scene.objects:
            if obj.type == "LIGHT" and obj.data.type == "SUN" and obj.visible_get():
                z = np.array(obj.matrix_world.to_3x3().col[2], dtype=np.float64)
                n = np.linalg.norm(z)
                if n > 1e-9:
                    return tuple(z / n)
        return None
