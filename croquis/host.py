# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""What Croquis takes from IngeTrazo and from Qt.

The drawing core (compose, drawing, hatch, ink, marker, palette, paper,
presets, raster, shadow, strokes, texts, vector, visibility, watercolour)
knows neither: Croquis for Blender copies it as it is. Here IngeTrazo lends
it, through the core's hooks, its language, the sun of its Shadows panel,
the faces and paint of its model, and Qt's smooth scaling and painter.
:func:`install` runs when the extension loads (croquis/__init__.py).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPolygonF

from . import drawing, marker, palette, paper, texts
from .drawing import INK


def install() -> None:
    drawing.RESIZE = qt_resize
    drawing.PAINT = layers_image
    paper.IMAGE_COVER = image_cover
    texts.LANGUAGE = _language
    marker.SUN = _sun
    palette.SOURCES = (from_pick_index, from_scene)
    palette.LOGGER = "ingetrazo.plugins"     # IngeTrazo's extensions log


# ---- IngeTrazo ---------------------------------------------------------------

def _language() -> str:
    from core.i18n import current_language
    return current_language()


def _sun(scene):
    from core.render_blender import sun_toward
    return sun_toward(scene)


def from_pick_index(viewport, colour_of):
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
    marker = np.full(len(idx.entities), -1, dtype=np.int64)
    tone = np.full(len(idx.entities), 1.0)
    paints: dict = {}

    def paint_of(group):
        # A group's paint, once per group, not once per face.
        key = id(group)
        if key not in paints:
            paints[key] = effective_material(group)
        return paints[key]

    wanted = np.unique(ents)
    parts = getattr(idx.entities, "_parts", None)
    starts = getattr(idx.entities, "_starts", None)
    if parts is None or starts is None:
        _one_by_one(idx.entities, wanted, 0, marker, tone, colour_of,
                    paint_of, effective_attrs)
    else:
        bounds = np.r_[np.asarray(starts, dtype=np.int64), len(idx.entities)]
        # ``wanted`` is sorted: each piece's faces are one slice of it.
        cut = np.searchsorted(wanted, bounds)
        for k, part in enumerate(parts):
            lo = bounds[k]
            es = wanted[cut[k]:cut[k + 1]]
            if len(es) and not _from_deferred(part, es - lo, es, marker, tone,
                                              colour_of, paint_of,
                                              effective_attrs):
                _one_by_one(part, es, lo, marker, tone, colour_of, paint_of,
                            effective_attrs)
    return tris, marker[ents], tone[ents]


def _one_by_one(part, es, lo, marker, tone, colour_of, paint_of,
                effective_attrs):
    """The colours of ``part``'s faces ``es`` (``lo`` its first entity),
    face by face."""
    for e in es.tolist():
        face, group = part[e - lo]
        attrs = face.attrs
        if group is not None:
            attrs = effective_attrs(face.attrs, paint_of(group))
        marker[e], tone[e] = colour_of(attrs)


def _from_deferred(part, local, es, marker, tone, colour_of, paint_of,
                   effective_attrs) -> bool:
    """The colours of a piece of the pick index whose faces belong to a
    lazy mesh (IngeTrazo 0.5.9's engine), read from the document's arrays
    as IngeTrazo's own ``core.mesh.face_attrs`` does: each face's paint is
    an entry of a short table, so each entry is worked out once and no
    face is built. ``False`` when the piece is not one (then the faces are
    read one by one)."""
    faces = getattr(part, "faces", None)
    mesh = getattr(faces, "mesh", None)
    index = getattr(faces, "index", None)
    if mesh is None or index is None or type(mesh).__name__ != "DeferredMesh":
        return False
    src = getattr(mesh, "__dict__", {}).get("_deferred_source")
    if not isinstance(src, dict) or "face_attr" not in src:
        return False
    try:
        from formats.igz import _face_attrs_from_json
        table = (src.get("meta") or {}).get("face_attrs") or []
        keys = np.asarray(src["face_attr"], dtype=np.int64)[
            np.asarray(index, dtype=np.int64)[local]]
    except Exception:                    # noqa: BLE001 (another IngeTrazo)
        return False
    group = getattr(part, "owner", None)
    uniq, inv = np.unique(keys, return_inverse=True)
    ms = np.empty(len(uniq), dtype=np.int64)
    ts = np.empty(len(uniq))
    for i, key in enumerate(uniq.tolist()):
        attrs = (_face_attrs_from_json(table[key]) or {}) if key >= 0 else {}
        if group is not None:
            attrs = effective_attrs(attrs, paint_of(group))
        ms[i], ts[i] = colour_of(attrs)
    marker[es], tone[es] = ms[inv], ts[inv]
    return True


def from_scene(viewport, colour_of):
    """:func:`from_pick_index` by walking the scene: slower, but on
    IngeTrazo's public model only (the loose faces, and every group in world space)."""
    from core.group import effective_material, world_mesh
    scene = viewport.scene
    tris, marker, tone = [], [], []

    def eat(mesh, paint, visible=lambda _f: True):
        from core.materials import effective_attrs
        for f in mesh.faces:
            if (f.attrs or {}).get("hidden") or not visible(f):
                continue
            m, t = colour_of(effective_attrs(f.attrs, paint) if paint else f.attrs)
            for a, b, c in f.triangulate():
                tris.append(((a.x(), a.y(), a.z()), (b.x(), b.y(), b.z()),
                             (c.x(), c.y(), c.z())))
                marker.append(m)
                tone.append(t)

    eat(scene.loose_mesh, None, scene.entity_visible)
    for g in scene.groups:
        if not scene.entity_visible(g) or getattr(g, "billboard", False):
            continue
        mesh = world_mesh(g) if g.xform is not None or g.children else g.mesh
        eat(mesh, effective_material(g))
    if not tris:
        return None
    return (np.array(tris, dtype=np.float64).reshape(-1, 3, 3),
            np.array(marker, dtype=np.int64), np.array(tone, dtype=np.float64))


# ---- Qt ----------------------------------------------------------------------

def to_qimage(rgb: np.ndarray) -> QImage:
    h, w = rgb.shape[:2]
    a = np.ascontiguousarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8),
                                        np.full((h, w), 255, dtype=np.uint8)]))
    img = QImage(a.tobytes(), w, h, w * 4, QImage.Format_RGBA8888)
    return img.convertToFormat(QImage.Format_ARGB32_Premultiplied)


def qt_resize(rgb: np.ndarray, width: int, height: int) -> np.ndarray:
    """Smoothly scale an (h, w, 3) float image with Qt."""
    img = to_qimage(rgb).scaled(width, height, Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_RGBA8888)
    a = np.frombuffer(img.constBits(), dtype=np.uint8,
                      count=img.bytesPerLine() * height)
    return a.reshape(height, img.bytesPerLine())[:, :width * 4].reshape(
        height, width, 4)[:, :, :3].astype(np.float64)


def draw_strokes(img: QImage, strokes: list, ink=INK) -> None:
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    for s in strokes:
        alpha = int(255 * max(0.0, min(1.0, s.opacity)))
        p.setBrush(QColor(ink[0], ink[1], ink[2], alpha))
        p.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in s.outline]))
    p.end()


def layers_image(layers) -> QImage:
    """A drawing's :class:`~croquis.drawing.Layers` as one QImage."""
    img = to_qimage(layers.coloured_sheet())
    draw_strokes(img, layers.strokes)
    return img


def image_cover(path: str, width: int, height: int):
    """An image of your own as the sheet, laid by Qt: repeated when small,
    else stretched to cover it (cropped to keep its proportions)."""
    src = QImage(path)
    if src.isNull():
        return None
    out = QImage(width, height, QImage.Format_RGB32)
    p = QPainter(out)
    if src.width() < paper.TILE_BELOW:
        p.fillRect(0, 0, width, height, QBrush(src))
    else:
        scaled = src.scaled(width, height, Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation)
        p.drawImage((width - scaled.width()) // 2, (height - scaled.height()) // 2, scaled)
    p.end()
    out = out.convertToFormat(QImage.Format_RGB888)
    a = np.frombuffer(out.constBits(), dtype=np.uint8,
                      count=out.bytesPerLine() * height)
    return a.reshape(height, out.bytesPerLine())[:, :width * 3].reshape(
        height, width, 3).astype(np.float32)
