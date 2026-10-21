# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Drawing the view, and saving the drawing."""

import time

import bpy
import numpy as np
from bpy.props import EnumProperty, StringProperty

from . import i18n, props
from . import scene_view as sv

IMAGE_NAME = "Croquis"
#: The last drawing's layers, to save as SVG or PDF without drawing again.
_last = {"layers": None}
FORMATS = [("PNG", "PNG", "The drawing as a picture"),
           ("SVG", "SVG in layers", "Paper, colour and the ink as vector paths"),
           ("PDF", "PDF", "One page at 300 dpi, the ink as vector paths")]


def _read_image(path: str):
    """An image of your own for the paper, through Blender."""
    try:
        img = bpy.data.images.load(path, check_existing=True)
    except RuntimeError:
        return None
    w, h = img.size
    px = np.empty(w * h * img.channels, np.float32)
    img.pixels.foreach_get(px)
    rgb = px.reshape(h, w, img.channels)[::-1, :, :3]
    if img.is_float:
        rgb = sv._to_srgb(rgb)
    return rgb * 255.0


def camera_for(context, source: str):
    """``(camera, None)`` or ``(None, why)``."""
    depsgraph = context.evaluated_depsgraph_get()
    scene = context.scene
    if source == "camera":
        if scene.camera is None:
            return None, "The scene has no camera: add one, or draw from this view"
        return sv.camera_from_object(scene.camera.evaluated_get(depsgraph),
                                     depsgraph, scene), None
    area = context.area if context.area and context.area.type == "VIEW_3D" else None
    if area is None:
        for a in context.screen.areas if context.screen else ():
            if a.type == "VIEW_3D":
                area = a
                break
    if area is None:
        return None, "No 3D viewport to draw from"
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    return sv.camera_from_view(region, area.spaces.active.region_3d), None


def draw(context, settings=None, width: int | None = None):
    """The drawing of the view as Croquis's layers, and how long it took.
    Raises ``ValueError`` when there is nothing to draw from."""
    from .core import drawing
    from .core import paper as pp
    from .core import presets as ps
    s = props.settings_dict(settings or context.scene.croquis)
    camera, why = camera_for(context, (settings or context.scene.croquis).source)
    if camera is None:
        raise ValueError(why)
    t = time.perf_counter()
    view_src = sv.BlenderView(context, context.evaluated_depsgraph_get(), camera)
    if not len(view_src):
        raise ValueError("Nothing to draw: the scene has no visible mesh")
    pp.IMAGE_READER = _read_image
    if width is None:
        width = s["size"] or s["custom_width"]
    layers = drawing.render(
        view_src, ps.line_style(s), width, marker=ps.marker_style(s),
        composition=ps.composition(s), paper_kind=s["paper"],
        paper_image=bpy.path.abspath(s["paper_image"]) if s["paper_image"] else "")
    return layers, time.perf_counter() - t


def blender_encode(rgb, fmt: str, quality: int = 90) -> bytes:
    """A picture encoded by Blender (JPEG or PNG), for the SVG and PDF."""
    import os
    import tempfile
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("croquis-encode", w, h, alpha=False)
    try:
        px = np.ones((h, w, 4), np.float32)
        px[:, :, :3] = np.asarray(rgb, np.float32)[::-1] / 255.0
        img.pixels.foreach_set(px.reshape(-1))
        ext = ".jpg" if fmt == "JPG" else ".png"
        fd, path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        try:
            img.filepath_raw = path
            img.file_format = "JPEG" if fmt == "JPG" else "PNG"
            if fmt == "JPG" and quality > 0:
                img.save(filepath=path, quality=quality)
            else:
                img.save(filepath=path)
            with open(path, "rb") as fh:
                return fh.read()
        finally:
            os.remove(path)
    finally:
        bpy.data.images.remove(img)


def save_drawing(layers, path: str, fmt: str) -> bool:
    """``layers`` saved at ``path`` as PNG, SVG or PDF."""
    from .core import vector
    if fmt == "PNG":
        img = to_image(layers)
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        return True
    return vector.save(layers, path, encode=blender_encode, dpi=300)


def to_image(layers, name: str = IMAGE_NAME):
    """The drawing in Blender's image ``name`` (made or replaced)."""
    rgb = layers.pixels()
    h, w = rgb.shape[:2]
    img = bpy.data.images.get(name)
    if img is None or tuple(img.size) != (w, h):
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, w, h, alpha=False)
    px = np.ones((h, w, 4), np.float32)
    px[:, :, :3] = rgb[::-1] / 255.0              # Blender's rows go up
    img.pixels.foreach_set(px.reshape(-1))
    img.update()
    return img


def show(context, img) -> None:
    """In an image editor: one already open, else a window of its own."""
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.spaces.active.image = img
                return
    with context.temp_override():
        bpy.ops.wm.window_new()
    win = context.window_manager.windows[-1]
    area = win.screen.areas[0]
    area.type = "IMAGE_EDITOR"
    area.spaces.active.image = img


class CROQUIS_OT_draw(bpy.types.Operator):
    """Draw the view as a freehand sketch"""
    bl_idname = "croquis.draw"
    bl_label = "Draw the view"
    bl_options = {"REGISTER"}

    def execute(self, context):
        wm = context.window_manager
        wm.progress_begin(0, 1)
        try:
            layers, secs = draw(context)
        except ValueError as exc:
            self.report({"WARNING"}, i18n.tr(str(exc)))
            return {"CANCELLED"}
        finally:
            wm.progress_end()
        img = to_image(layers)
        _last["layers"] = layers
        context.scene.croquis_last = img.name
        show(context, img)
        self.report({"INFO"}, i18n.tr("Croquis: {w}×{h} in {s} s", w=img.size[0],
                                      h=img.size[1], s=f"{secs:.1f}"))
        return {"FINISHED"}


class CROQUIS_OT_save(bpy.types.Operator):
    """Save the last drawing as PNG, SVG in layers or PDF"""
    bl_idname = "croquis.save"
    bl_label = "Save the drawing…"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.png;*.svg;*.pdf", options={"HIDDEN"})
    format: EnumProperty(name="Format", items=FORMATS, default="PNG")

    @classmethod
    def poll(cls, context):
        return _last["layers"] is not None

    def _ext(self) -> str:
        return "." + self.format.lower()

    def check(self, _context) -> bool:
        """The file name follows the format chosen."""
        new = bpy.path.ensure_ext(self.filepath.rsplit(".", 1)[0]
                                  if self.filepath.lower().endswith((".png", ".svg", ".pdf"))
                                  else self.filepath, self._ext())
        if new != self.filepath:
            self.filepath = new
            return True
        return False

    def invoke(self, context, _event):
        if not self.filepath:
            self.filepath = (bpy.path.display_name_from_filepath(bpy.data.filepath)
                             or "croquis") + self._ext()
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = bpy.path.ensure_ext(self.filepath, self._ext())
        if not save_drawing(_last["layers"], path, self.format):
            self.report({"ERROR"}, i18n.tr("Could not save {path}", path=path))
            return {"CANCELLED"}
        self.report({"INFO"}, i18n.tr("Saved {path}", path=path))
        return {"FINISHED"}


classes = (CROQUIS_OT_draw, CROQUIS_OT_save)


def register() -> None:
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.croquis_last = StringProperty(options={"HIDDEN", "SKIP_SAVE"})


def unregister() -> None:
    del bpy.types.Scene.croquis_last
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
