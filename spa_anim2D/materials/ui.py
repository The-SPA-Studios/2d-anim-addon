# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import bpy

from spa_anim2D.materials.core import (
    DEFAULT_PALETTE_ID,
    get_material_basename,
    get_palette_name,
    has_valid_palette_name,
)

from spa_anim2D.utils import register_classes, unregister_classes


class MATERIAL_UL_palette_materials(bpy.types.UIList):
    """
    Template to display the materials of a grease pencil's active material_palette.
    """

    bl_idname = "MATERIAL_UL_palette_materials"

    def draw_item(
        self,
        context,
        layout,
        data,
        item: bpy.types.MaterialSlot,
        icon,
        active_data,
        active_propname,
    ):

        mat = item.material
        # Discard empty material slots
        if not mat:
            return
        short_name = get_material_basename(mat)
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.label(text=short_name, icon_value=icon)
            subrow = layout.row(align=True)
            subrow.prop(
                mat.grease_pencil,
                "ghost",
                icon_only=True,
                emboss=False,
                icon="ONIONSKIN_OFF" if mat.grease_pencil.ghost else "ONIONSKIN_ON",
            )

            subrow.prop(mat.grease_pencil, "hide", icon_only=True, emboss=False)
            subrow.prop(mat.grease_pencil, "lock", icon_only=True, emboss=False)

        elif self.layout_type in {"GRID"}:
            layout.prop(mat, "name", text="", emboss=False, icon_value=icon)

    def filter_items(self, context: bpy.types.Context, obj, propname):
        mat_slots = getattr(obj, propname)
        materials = [slot.material for slot in mat_slots]

        flt_flags = []
        flt_neworder = []

        active_palette = getattr(obj.data, "material_palette")
        flt_flags = [0] * len(materials)

        for i, mat in enumerate(materials):
            # Discard slots without materials
            if not mat:
                continue
            # Discard slot if one with the same material is already displayed
            if mat in materials[:i]:
                continue
            # Display materials from either:
            # - the active material_palette
            # - all materials without a valid palette if material_palette is the default placeholder
            if (get_palette_name(mat) == active_palette) or (
                active_palette == DEFAULT_PALETTE_ID and not has_valid_palette_name(mat)
            ):
                flt_flags[i] = self.bitflag_filter_item

        return flt_flags, flt_neworder


class VIEW3D_PT_MaterialPalettePanel(bpy.types.Panel):
    """
    Panel that displays material palette controls for the active grease pencil object.
    """

    bl_label = "Colors"
    bl_category = "SPA.Anim2D"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context: bpy.types.Context):
        self.layout.use_property_decorate = False
        # Display a placeholder text if active object is not a grease pencil
        if not isinstance(
            getattr(context.active_object, "data", None), bpy.types.GreasePencil
        ):
            self.layout.label(text="No active Grease Pencil object")
            return

        settings = context.tool_settings.gpencil_paint
        self.layout.prop(context.scene.gp_paint_color, "mode", expand=True)

        if settings.color_mode == "MATERIAL":
            self.draw_material_settings(context)
        else:
            self.draw_vertex_color_settings(context)

    def draw_material_settings(self, context: bpy.types.Context):
        """Display material palettes settings"""
        active_object = context.active_object
        gpencil = active_object.data
        row = self.layout.row()
        row.prop(gpencil, "material_palette", icon="COLOR", text="")
        row.operator("material.palettes_refresh", text="", icon="FILE_REFRESH")

        self.layout.template_list(
            MATERIAL_UL_palette_materials.bl_idname,
            "",
            active_object,
            "material_slots",
            active_object,
            "active_material_index",
            type="DEFAULT",
            columns=2,
            rows=3,
        )

    def draw_vertex_color_settings(self, context: bpy.types.Context):
        """Display vertex color settings."""
        ts = context.tool_settings
        settings = ts.gpencil_paint
        brush = settings.brush

        if context.space_data.shading.type not in (
            "RENDERED",
            "MATERIAL",
        ):
            row = self.layout.row()
            row.alert = True
            row.label(
                text="Material Preview or Rendered shading required",
                icon="ERROR",
            )
            row.prop(context.space_data.shading, "type", text="", expand=True)

        # Color picker
        col = self.layout.column()
        row = col.row()
        col.template_color_picker(brush, "color", value_slider=True)
        col.prop(brush, "color", text="")

        # Draw style (line/fill)
        row = col.row(align=True)
        row.prop(context.scene.gp_paint_color, "vertex_color_style", expand=True)

        # Color palette
        col.template_ID(settings, "palette", new="palette.new")
        if settings.palette:
            col.template_palette(settings, "palette", color=True)


classes = (
    MATERIAL_UL_palette_materials,
    VIEW3D_PT_MaterialPalettePanel,
)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
