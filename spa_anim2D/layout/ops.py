# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import bpy

from spa_anim2D.layout.core import (
    camera_view_depth_get,
    deselect_all,
    get_pixel_size_at_object_location,
    set_depth_from_camera,
)

from spa_anim2D.utils import register_classes, unregister_classes


class OBJECT_OT_camera_view_push_pull(bpy.types.Operator):
    bl_idname = "object.camera_view_push_pull"
    bl_label = "Pull/Push Object from Camera"
    bl_description = "Push/Pull object from active camera view with auto-scaling"
    bl_options = {"UNDO", "BLOCKING", "GRAB_CURSOR"}

    bl_keymaps = [
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "F",
            "shift": True,
        }
    ]

    offset: bpy.props.FloatProperty(
        name="Offset",
        description="Depth offset to apply",
    )

    adjust_scale: bpy.props.BoolProperty(
        name="Adjust Scale",
        description="Whether to scale the object to compensate for the translation",
        default=True,
        options=set(),
    )

    precision_mode: bpy.props.BoolProperty(
        name="Precision Mode",
        description="Use precision mode",
        default=False,
        options={"HIDDEN"},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.area.type == "VIEW_3D"
            and context.scene.camera
            and context.active_object
            and context.active_object != context.scene.camera
        )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.matrix_orig = context.active_object.matrix_world.copy()
        self.mouse_y_orig = event.mouse_region_y
        self.depth_orig = camera_view_depth_get(context.active_object)
        # Get pixel size at object location.
        self.pixel_size = get_pixel_size_at_object_location(
            context, context.active_object
        )

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        context.window.cursor_modal_set("SCROLL_Y")
        if event.type in {"RIGHTMOUSE", "ESC"}:
            context.active_object.matrix_world = self.matrix_orig
            context.window.cursor_modal_restore()
            return {"CANCELLED"}

        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"} and event.value in {
            "RELEASE"
        }:
            context.window.cursor_modal_restore()
            return {"FINISHED"}

        # Disable scaling if ctrl is pressed.
        self.adjust_scale = not event.ctrl

        if self.precision_mode != event.shift:
            # Reset offset when switching between precision/default mode to
            # avoid having the object jump.
            self.depth_orig = camera_view_depth_get(context.active_object)
            self.mouse_y_orig = event.mouse_region_y
            self.precision_mode = event.shift

        # Compute the depth offset by applying 3D pixel size to mouse vertical offset
        mouse_offset = event.mouse_region_y - self.mouse_y_orig
        self.offset = mouse_offset * self.pixel_size
        # Apply precision mode to offset if enabled.
        if self.precision_mode:
            self.offset *= 0.1

        self.execute(context)

        return {"RUNNING_MODAL"}

    def execute(self, context: bpy.types.Context):
        # Start back from initial transformation matrix.
        # Useful to go back to initial scale if scale compensation has been deactivated.
        context.active_object.matrix_world = self.matrix_orig

        # Apply depth offset.
        set_depth_from_camera(
            context.scene.camera.matrix_world,
            context.active_object,
            self.depth_orig + self.offset,
            self.adjust_scale,
        )

        return {"FINISHED"}


class SCENE_OT_camera_select(bpy.types.Operator):
    bl_idname = "scene.camera_select"
    bl_label = "Select Active Camera"
    bl_description = "Select scene active camera"

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.scene.camera is not None

    def execute(self, context: bpy.types.Context):
        camera = context.scene.camera
        # Select only active camera and make it active.
        deselect_all(context)
        camera.hide_set(False)
        try:
            camera.select_set(True)
        except RuntimeError:
            self.report(
                {"ERROR"},
                "Active camera not selectable. Parent collection may be disabled.",
            )
            return {"FINISHED"}

        context.view_layer.objects.active = camera

        if not camera.visible_get():
            self.report(
                {"ERROR"},
                "Active camera selected but not visible. "
                "Parent collection may be hidden.",
            )

        return {"FINISHED"}


class OBJECT_OT_camera_background_add(bpy.types.Operator):
    bl_idname = "camera.background_add"
    bl_label = "Add Camera Background"
    bl_description = "Add a Background Image to the active Camera"
    bl_options = {"UNDO"}

    def execute(self, context: bpy.types.Context):
        camera_data = context.scene.camera.data
        camera_data.background_images.new()
        return {"FINISHED"}


class OBJECT_OT_camera_background_remove(bpy.types.Operator):
    bl_idname = "camera.background_remove"
    bl_label = "Remove Camera Background"
    bl_description = "Remove a Background Image from the active Camera"
    bl_options = {"UNDO"}

    index: bpy.props.IntProperty(
        name="index",
        description="Index of Camera Background Image",
        default=0,
        options={"SKIP_SAVE"},
    )

    def execute(
        self,
        context: bpy.types.Context,
    ):
        camera_data = context.scene.camera.data
        bg_img = camera_data.background_images[self.index]
        camera_data.background_images.remove(bg_img)
        return {"FINISHED"}


classes = (
    OBJECT_OT_camera_view_push_pull,
    OBJECT_OT_camera_background_add,
    OBJECT_OT_camera_background_remove,
    SCENE_OT_camera_select,
)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
