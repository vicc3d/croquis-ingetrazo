# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The Croquis tab in the 3D viewport's sidebar: the same boxes as in
IngeTrazo, one decision each, and the button that draws."""
from __future__ import annotations

import bpy


class _Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Croquis"


class CROQUIS_PT_main(_Base, bpy.types.Panel):
    bl_label = "Croquis"

    def draw(self, context):
        s = context.scene.croquis
        col = self.layout.column()
        col.prop(s, "preset")
        row = col.row(align=True)
        row.prop(s, "source", expand=True)
        row = col.row(align=True)
        row.prop(s, "size", expand=True)
        if s.size == "0":
            col.prop(s, "custom_width")
        col.separator()
        big = col.row()
        big.scale_y = 1.6
        big.operator("croquis.draw", icon="GREASEPENCIL")
        col.operator("croquis.save", icon="FILE_TICK")


class CROQUIS_PT_line(_Base, bpy.types.Panel):
    bl_label = "Line"
    bl_parent_id = "CROQUIS_PT_main"

    def draw(self, context):
        s = context.scene.croquis
        col = self.layout.column()
        col.prop(s, "hand", slider=True)
        row = col.row(align=True)
        row.prop(s, "outlines", toggle=True)
        row.prop(s, "twice", toggle=True)
        row.prop(s, "breaks", toggle=True)


class CROQUIS_PT_colour(_Base, bpy.types.Panel):
    bl_label = "Technique and light"
    bl_parent_id = "CROQUIS_PT_main"

    def draw(self, context):
        s = context.scene.croquis
        col = self.layout.column()
        col.row(align=True).prop(s, "technique", expand=True)
        row = col.row(align=True)
        row.prop(s, "light", expand=True)
        row.prop(s, "shadows", toggle=True)
        col.row(align=True).prop(s, "materials", expand=True)
        if s.materials == "contrast":
            col.prop(s, "ink_texture")


class CROQUIS_PT_hatching(_Base, bpy.types.Panel):
    bl_label = "Hatching in the shade"
    bl_parent_id = "CROQUIS_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.croquis, "hatching", text="")

    def draw(self, context):
        s = context.scene.croquis
        col = self.layout.column()
        col.active = s.hatching
        col.prop(s, "hatch_along")
        col.prop(s, "hatch_turn", slider=True)


class CROQUIS_PT_composition(_Base, bpy.types.Panel):
    bl_label = "Composition and paper"
    bl_parent_id = "CROQUIS_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.croquis
        col = self.layout.column()
        row = col.row(align=True)
        row.prop(s, "unfinished", toggle=True)
        row.prop(s, "construction", toggle=True)
        row.prop(s, "ground", toggle=True)
        col.prop(s, "paper")
        if s.paper == "custom":
            col.prop(s, "paper_image")


class CROQUIS_PT_fine(_Base, bpy.types.Panel):
    bl_label = "Fine settings"
    bl_parent_id = "CROQUIS_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.croquis
        col = self.layout.column()
        for k in ("weight", "overshoot", "offset", "nib", "strength"):
            col.prop(s, k, slider=True)
        col.prop(s, "natural")


classes = (CROQUIS_PT_main, CROQUIS_PT_line, CROQUIS_PT_colour,
           CROQUIS_PT_hatching, CROQUIS_PT_composition, CROQUIS_PT_fine)


def register() -> None:
    for c in classes:
        bpy.utils.register_class(c)


def unregister() -> None:
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
