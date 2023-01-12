# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import bpy

from spa_anim2D.animation.core import get_active_gp_keyframe, keyframe_types
from spa_anim2D.drawing.core import get_active_gp_object
from spa_anim2D.utils import register_classes, unregister_classes


class DOPESHEET_PT_KeyframeTools(bpy.types.Panel):
    bl_label = "Keyframe Tools"
    bl_space_type = "DOPESHEET_EDITOR"
    bl_region_type = "UI"
    bl_category = "SPA.Anim2D"

    def draw(self, context: bpy.types.Context):
        self.layout.label(text="Shift Keyframes", icon="PREV_KEYFRAME")
        box = self.layout.box()
        col = box.column()

        keyframes_shift_options = {
            "All Layers": {},
            "Selected": {
                "only_selected_layers": True,
            },
            "Active": {
                "only_active_layer": True,
            },
        }
        # Populate panel with variations for  frame-by-frame keyframe shifting
        for name, options in keyframes_shift_options.items():
            row = col.row(align=True)
            row.label(text=name)
            row.operator_context = "EXEC_DEFAULT"
            for offset, icon in ((-1, "REW"), (+1, "FF")):
                props = row.operator("transform.keyframes_shift", icon=icon, text="")
                props.offset = offset
                for k, v in options.items():
                    setattr(props, k, v)


class VIEW3D_PT_animation_box(bpy.types.Panel):
    bl_label = "Animation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SPA.Anim2D"

    def draw(self, context: bpy.types.Context):
        obj = get_active_gp_object()
        if not obj:
            self.layout.label(text="No active Grease Pencil object")
            return

        gpd = obj.data

        # Current Keyframe
        gpf = get_active_gp_keyframe(gpd)

        keyframe_box = self.layout.box()
        row = keyframe_box.row(align=True)

        row.label(text="Current Keyframe", icon="DECORATE_KEYFRAME")
        subrow = row.row()

        row = keyframe_box.row(align=True)
        row.enabled = gpf is not None and (gpd.layers.active.lock is False)
        row.prop(
            gpd.current_keyframe_settings,
            "keyframe_type",
            text="",
            expand=True,
            icon_only=True,
        )
        row.separator()
        subrow = row.row()
        subrow.enabled = (
            (gpf is not None)
            and (gpd.current_keyframe_settings.duration > 0)
            and (gpd.layers.active.lock is False)
        )
        subrow.use_property_split = True
        subrow.use_property_decorate = False
        subrow.prop(gpd.current_keyframe_settings, "duration", text="Duration")

        # Flipping
        flipping_box = self.layout.box()
        row = flipping_box.row(align=True)
        row.label(text="Flipping", icon="STRANDS")

        row.separator()
        row.prop(gpd.flipping_settings, "layer_mode", expand=True, icon_only=True)
        row.separator()
        row.prop(gpd.flipping_settings, "use_filter", icon="FILTER", icon_only=True)
        subrow = row.row(align=True)
        subrow.enabled = gpd.flipping_settings.use_filter
        for i, icon in enumerate(keyframe_types.values()):
            subrow.prop(
                gpd.flipping_settings,
                "keyframe_types",
                icon=icon,
                icon_only=True,
                text="",
                index=i,
            )

        subrow = flipping_box.row(align=True)

        subrow.operator(
            "anim.keyframes_flip", icon="TRIA_LEFT", text="Previous"
        ).direction = "LEFT"
        subrow.operator(
            "anim.keyframes_flip",
            icon="TRIA_RIGHT",
            text="Next",
        ).direction = "RIGHT"

        subrow.separator()
        subrow.prop(gpd.flipping_settings, "loop", icon="FILE_REFRESH", icon_only=True)
        subrow.separator()
        subrow.prop(
            gpd.flipping_settings,
            "use_preview_range",
            icon_only=True,
            expand=True,
            icon="PREVIEW_RANGE",
        )

        # Onion Skinning.
        onion_skin_box = self.layout.box()
        onion_skin_enabled = context.area.spaces.active.overlay.use_gpencil_onion_skin

        row = onion_skin_box.row()
        row.prop(
            context.area.spaces.active.overlay,
            "use_gpencil_onion_skin",
            text="",
            icon="ONIONSKIN_ON",
        )
        row.label(text="Onion Skinning")

        if context.space_data.shading.type not in (
            "SOLID",
            "MATERIAL",
        ):
            warning_row = onion_skin_box.row()
            warning_row.alert = True
            warning_row.label(
                text="Solid or Material Preview shading required",
                icon="ERROR",
            )
            warning_row.prop(context.space_data.shading, "type", text="", expand=True)

        subrow = row.row(align=True)
        subrow.enabled = onion_skin_enabled

        for i, icon in enumerate(keyframe_types.values()):
            subrow.prop(
                gpd,
                "onion_keyframe_type",
                icon=icon,
                icon_only=True,
                text="",
                index=i,
            )

        col = onion_skin_box.column()
        col.enabled = onion_skin_enabled

        if hasattr(gpd, "onion_space"):
            row = col.row(align=True)
            row.prop(gpd, "onion_space", expand=True)

            row = row.row(align=True)
            row.enabled = gpd.onion_space == "WORLD"

            row.operator(
                "gpencil.cache_ghost_frame_transformations",
                text="",
                icon="FILE_REFRESH",
            )
            row.prop(
                context.window_manager,
                "gp_onion_skinning_worldspace_auto_update",
                text="",
                icon="RECOVER_LAST",
            )

            col.separator()

        row = col.row(align=True)
        row.prop(gpd, "onion_factor", text="Opacity", slider=True)
        row.prop(gpd, "use_onion_fade", icon_only=True, icon="PARTICLE_PATH")

        row = col.row(align=True)
        row.prop(gpd, "before_color", text="")
        row.prop(gpd, "after_color", text="")

        col.prop(gpd, "onion_mode", text="", icon="KEYFRAME_HLT")
        col = col.column()
        if gpd.onion_mode == "TAGGED":
            col.operator("anim.lightbox_edit", text="Untag All").action = "CLEAR"
        elif gpd.onion_mode == "RELATIVE" or gpd.onion_mode == "ABSOLUTE":
            row = col.row(align=True)
            row.prop(gpd, "ghost_before_range", text="Before")
            row.prop(gpd, "ghost_after_range", text="After")

        if hasattr(context.scene.tool_settings, "use_gpencil_offset_frames"):
            ts = context.scene.tool_settings
            box = self.layout.box()

            # Title.
            row = box.row()
            row.prop(ts, "use_gpencil_offset_frames", text="", icon="OBJECT_HIDDEN")
            row.label(text="Shift & Trace")

            # Pin to frame control.
            subrow = row.row()
            subrow.alignment = "RIGHT"
            snt_settings = context.window_manager.shift_and_trace_settings

            icon = "UNPINNED"
            text = "Pin"

            if snt_settings.pin_to_frame:
                text = str(snt_settings.pinned_frame_number)
                if snt_settings.pinned_frame_number == context.scene.frame_current:
                    icon = "PINNED"

            subrow.prop(snt_settings, "pin_to_frame", icon=icon, text=text)

            # Reset operators.
            row = box.row(align=True)
            row.enabled = ts.use_gpencil_offset_frames
            row.label(text="Reset", icon="LOOP_BACK")
            row.operator(
                "gpencil.reset_frame_transforms", text="Active"
            ).type = "ACTIVE"
            row.operator(
                "gpencil.reset_frame_transforms", text="Selected"
            ).type = "SELECTED"
            row.operator("gpencil.reset_frame_transforms", text="All").type = "ALL"


classes = (
    DOPESHEET_PT_KeyframeTools,
    VIEW3D_PT_animation_box,
)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
