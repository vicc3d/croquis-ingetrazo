# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Drawing the view, and saving the drawing."""

import time

import bpy
import numpy as np
from bpy.props import StringProperty

from . import props
from . import scene_view as sv

IMAGE_NAME = "Croquis"


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
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        finally:
            wm.progress_end()
        img = to_image(layers)
        context.scene.croquis_last = img.name
        show(context, img)
        self.report({"INFO"}, f"Croquis: {img.size[0]}×{img.size[1]} in {secs:.1f} s")
        return {"FINISHED"}


class CROQUIS_OT_save(bpy.types.Operator):
    """Save the last drawing as a PNG"""
    bl_idname = "croquis.save"
    bl_label = "Save the drawing…"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.png", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return bpy.data.images.get(IMAGE_NAME) is not None

    def invoke(self, context, _event):
        if not self.filepath:
            self.filepath = bpy.path.ensure_ext(
                bpy.path.display_name_from_filepath(bpy.data.filepath) or "croquis", ".png")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        img = bpy.data.images.get(IMAGE_NAME)
        path = bpy.path.ensure_ext(self.filepath, ".png")
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        self.report({"INFO"}, f"Saved {path}")
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
