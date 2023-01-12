# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import itertools
import bpy


from spa_anim2D.animation.core import (
    frame_options_to_traits,
    get_active_gp_keyframe,
    get_gp_keyframes,
    keyframe_types,
    layer_options_to_traits,
    shift_keyframes,
    shift_gp_keyframes,
)
from spa_anim2D.utils import register_classes, unregister_classes
from spa_anim2D.preferences import get_addon_prefs


class TRANSFORM_OT_keyframes_shift(bpy.types.Operator):
    bl_idname = "transform.keyframes_shift"
    bl_label = "Shift Grease Pencil Keyframes"
    bl_description = "Shift active Grease Pencil's Keyframes after current Frame"
    bl_options = {"BLOCKING", "GRAB_CURSOR", "UNDO", "REGISTER"}

    offset: bpy.props.IntProperty(
        name="Offset",
        description="Frame offset to apply",
        default=0,
        options={"SKIP_SAVE"},
    )

    only_active_layer: bpy.props.BoolProperty(
        name="Only Active Layer",
        description="Only affect active Layer",
        default=False,
        options={"SKIP_SAVE"},
    )

    only_selected_layers: bpy.props.BoolProperty(
        name="Only Selected Layers",
        description="Only affect selected Layers",
        default=False,
        options={"SKIP_SAVE"},
    )

    interactive: bpy.props.BoolProperty(
        name="Interactive",
        description="Use interactive mode to offset keyframes",
        default=False,
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            context.area.type == "DOPESHEET_EDITOR"
            and context.active_object
            and isinstance(context.active_object.data, bpy.types.GreasePencil)
        )

    def setup(self, context):
        # Get all GP keyframes after current frame
        self.keyframes = get_gp_keyframes(
            context.active_object.data,
            layer_options_to_traits(
                self.only_active_layer,
                True,
                self.only_selected_layers,
            ),
            frame_min=context.scene.frame_current + 1,
        )

        if not self.keyframes:
            return

        # Store the first keyframe initial value
        self.first_keyframe_init_value = self.keyframes[0].frame_number

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.setup(context)

        if not self.keyframes:
            return {"CANCELLED"}

        if self.interactive:
            context.window.cursor_modal_set("SCROLL_X")
            self.start_mouse_coords = context.region.view2d.region_to_view(
                x=event.mouse_region_x, y=event.mouse_region_y
            )
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        else:
            return self.execute(context)

    def update_header_text(self, context, event):
        context.area.header_text_set(f"Offset: {self.offset}")

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        self.update_header_text(context, event)
        # Cancel
        if event.type in {"RIGHTMOUSE", "ESC"}:
            self.cancel(context)
            return {"CANCELLED"}
        # Validate
        elif (
            event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"}
            and event.value == "PRESS"
        ):
            if self.offset == 0:
                self.cancel(context)
                return {"CANCELLED"}
            self.restore_ui(context)
            return {"FINISHED"}
        # Update
        elif event.type in {"MOUSEMOVE"}:
            mouse_coords = context.region.view2d.region_to_view(
                x=event.mouse_region_x, y=event.mouse_region_y
            )
            offset = int(mouse_coords[0] - self.start_mouse_coords[0])
            if offset != self.offset:
                self.offset = offset
                self.execute(context)

        return {"RUNNING_MODAL"}

    def restore_ui(self, context: bpy.types.Context):
        context.area.header_text_set(None)
        context.window.cursor_modal_restore()

    def cancel(self, context: bpy.types.Context):
        if self.offset:
            self.offset = 0
            self.execute(context)
        self.restore_ui(context)

    def execute(self, context: bpy.types.Context):
        # Setup operator if invoke was not called
        if not self.options.is_invoke:
            self.setup(context)
            if not self.keyframes:
                return {"CANCELLED"}

        # Compute absolute offset from original position
        current_delta = self.keyframes[0].frame_number - self.first_keyframe_init_value
        offset = self.offset - current_delta

        res = shift_keyframes(
            self.keyframes, offset, context.scene.frame_current + 1, adjust_offset=True
        )

        if not res:
            return {"CANCELLED"}

        # Select all the keyframes that have been moved
        # Note: moving GP keyframes in Python does not invalidate the depsgraph,
        #       leading to potentially incorrect results in the viewport.
        #       Here, calling `select_all` operator fixes the issue.
        bpy.ops.action.select_all(action="DESELECT")
        for keyframe in self.keyframes:
            keyframe.select = True

        return {"FINISHED"}


class ANIM_OT_lightbox_edit(bpy.types.Operator):
    bl_idname = "anim.lightbox_edit"
    bl_label = "Edit the lightbox"
    bl_options = {"UNDO", "REGISTER"}

    action: bpy.props.EnumProperty(
        items=[
            ("ADD", "Add selected", ""),
            ("REMOVE", "Remove selected", ""),
            ("CLEAR", "Clear", ""),
        ],
        name="Action",
        description="The action to perform on the lightbox",
        default="ADD",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.active_object and isinstance(
            context.active_object.data, bpy.types.GreasePencil
        )

    @classmethod
    def description(cls, context: bpy.types.Context, properties):
        if properties.action == "ADD":
            return "Add selected keyframes to the lightbox"
        elif properties.action == "REMOVE":
            return "Remove selected keyframes from the lightbox"
        elif properties.action == "CLEAR":
            return "Clear all keyframes from the lightbox"

    def execute(self, context: bpy.types.Context):
        if self.action == "ADD":
            selected_filter = True
            onion_tag_filter = False
        if self.action == "REMOVE":
            selected_filter = True
            onion_tag_filter = True
        if self.action == "CLEAR":
            selected_filter = False
            onion_tag_filter = True

        keyframes = get_gp_keyframes(
            context.active_object.data,
            frame_filter=frame_options_to_traits(
                selected=selected_filter, onion_tag=onion_tag_filter
            ),
        )

        if not keyframes:
            return {"CANCELLED"}

        for key in keyframes:
            key.tag = True if self.action == "ADD" else False

        return {"FINISHED"}


class ANIM_OT_keyframes_flip(bpy.types.Operator):
    bl_idname = "anim.keyframes_flip"
    bl_label = "Keyframes Flipping"
    bl_description = "Flip between keyframes"

    bl_keymaps_defaults = {
        "space_type": "DOPESHEET_EDITOR",
        "category_name": "Dopesheet",
    }
    bl_keymaps = [
        {"key": "COMMA", "properties": {"direction": "LEFT"}},
        {"key": "PERIOD", "properties": {"direction": "RIGHT"}},
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "COMMA",
            "properties": {"direction": "LEFT"},
        },
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "PERIOD",
            "properties": {"direction": "RIGHT"},
        },
    ]

    direction: bpy.props.EnumProperty(
        name="Direction", items=(("LEFT", "Left", ""), ("RIGHT", "Right", ""))
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.active_object and context.active_object.type == "GPENCIL"

    def execute(self, context: bpy.types.Context):
        gpd: bpy.types.GreasePencil = context.active_object.data

        # Select impacted layers.
        if gpd.flipping_settings.layer_mode == "VISIBLE":
            layers = [gpl for gpl in gpd.layers if not gpl.hide]
        else:
            layers = [gpd.layers.active]

        # Build a flat list with keyframes matching to current filter type settings.
        keyframe_types_list = list(keyframe_types.keys())
        keyframe_types_filter = gpd.flipping_settings.keyframe_types
        frames = [
            kf
            for kf in itertools.chain.from_iterable([gpl.frames for gpl in layers])
            if (
                not gpd.flipping_settings.use_filter
                or keyframe_types_filter[keyframe_types_list.index(kf.keyframe_type)]
            )
        ]

        # Remove frames not in preview range if enabled
        preview_start = context.scene.frame_preview_start
        preview_end = context.scene.frame_preview_end
        if gpd.flipping_settings.use_preview_range and context.scene.use_preview_range:
            frames = [
                kf for kf in frames if preview_start <= kf.frame_number <= preview_end
            ]

        # Early return if no keyframes match the filtering.
        if not frames:
            return {"CANCELLED"}

        # Sort those keyframes by frame number.
        sorted_frames = sorted(
            frames, reverse=self.direction == "LEFT", key=lambda x: x.frame_number
        )

        def compare_func(x: int, y: int):
            return x < y if self.direction == "LEFT" else x > y

        # Get prev/next frame relative to scene's current frame.
        actframe = context.scene.frame_current
        # Use first keyframe in list as fallback when looping is enabled.
        fallback = sorted_frames[0] if gpd.flipping_settings.loop else None

        keyframe = next(
            (kf for kf in sorted_frames if compare_func(kf.frame_number, actframe)),
            fallback,
        )

        if not keyframe:
            return {"CANCELLED"}

        # Update scene's current frame.
        context.scene.frame_current = keyframe.frame_number

        return {"FINISHED"}


class GPencilFlippingSettings(bpy.types.PropertyGroup):

    use_filter: bpy.props.BoolProperty(
        name="Use Keyframe Type Filter",
        description="Use keyframe type filtering when flipping",
        default=True,
        options=set(),
    )

    keyframe_types: bpy.props.BoolVectorProperty(
        name="Keyframe Types",
        description="Keyframe types filter for flipping",
        size=5,
        default=[True] * 5,
        options=set(),
    )

    layer_mode: bpy.props.EnumProperty(
        name="Layer Mode",
        items=(
            ("ACTIVE", "Active", "Flip on active layer", "IMAGE_DATA", 0),
            ("VISIBLE", "Visible", "Flip on all visible layers", "RENDERLAYERS", 1),
        ),
        default="ACTIVE",
        options=set(),
    )

    loop: bpy.props.BoolProperty(
        name="Loop",
        description="Loop when reaching first or last keyframe",
        default=True,
        options=set(),
    )

    use_preview_range: bpy.props.BoolProperty(
        name="Use Preview Range",
        description="Flip only within the preview range, if enabled",
        default=True,
        options=set(),
    )


class GPencilCurrentKeyframeSettings(bpy.types.PropertyGroup):
    def get_current_keyframe_type(self):
        key_types = self.rna_type.properties["keyframe_type"].enum_items.keys()
        gpf = get_active_gp_keyframe(self.id_data)
        return key_types.index(gpf.keyframe_type) if gpf else 0

    def set_current_keyframe_type(self, keyframe_type_idx: int):
        key_types = self.rna_type.properties["keyframe_type"].enum_items.keys()
        gpf = get_active_gp_keyframe(self.id_data)
        if gpf:
            gpf.keyframe_type = key_types[keyframe_type_idx]

    keyframe_type: bpy.props.EnumProperty(
        name="Keyframe Type",
        items=(
            ("KEYFRAME", "Normal", "", "HANDLETYPE_FREE_VEC", 0),
            ("EXTREME", "Extreme", "", "KEYTYPE_EXTREME_VEC", 1),
            ("BREAKDOWN", "Breakdown", "", "KEYTYPE_BREAKDOWN_VEC", 2),
            ("JITTER", "Jitter", "", "KEYTYPE_JITTER_VEC", 3),
            ("MOVING_HOLD", "Moving Hold", "", "KEYTYPE_MOVING_HOLD_VEC", 4),
        ),
        default="KEYFRAME",
        options=set(),
        get=get_current_keyframe_type,
        set=set_current_keyframe_type,
    )

    def get_current_keyframe_duration(self):
        gpd = self.id_data
        gpf = get_active_gp_keyframe(gpd)
        if gpf is None:
            return 0
        for kf in gpd.layers.active.frames:
            if kf.frame_number > gpf.frame_number:
                return kf.frame_number - gpf.frame_number
        return 0

    def set_current_keyframe_duration(self, duration: int):
        gpd = self.id_data
        gpf = get_active_gp_keyframe(gpd)
        if gpf is None:
            return
        offset = duration - self.duration
        bpy.context.scene.frame_set(gpf.frame_number)
        shift_gp_keyframes(gpd, gpf.frame_number, offset, False, True, True, False)
        for area in bpy.context.screen.areas:
            if area.type == "DOPESHEET_EDITOR":
                area.tag_redraw()

    duration: bpy.props.IntProperty(
        name="Keyframe Duration",
        default=1,
        get=get_current_keyframe_duration,
        set=set_current_keyframe_duration,
        min=1,
    )


class GPencilShiftAndTraceSettings(bpy.types.PropertyGroup):
    """Shift and Trace extra settings."""

    def pin_to_frame_update_cb(self, context):
        if self.pin_to_frame:
            # Update frame value to current frame.
            self.pinned_frame_number = context.scene.frame_current
            context.scene.frame_current = context.scene.frame_current
        else:
            # When unpinning, activate shifted frames display.
            context.scene.tool_settings.use_gpencil_offset_frames = True

    pin_to_frame: bpy.props.BoolProperty(
        name="Pin to Frame",
        description="Only show shifted drawings at this frame",
        default=False,
        update=pin_to_frame_update_cb,
        options=set(),
    )

    pinned_frame_number: bpy.props.IntProperty(
        name="Pinned Frame",
        description="Pinned frame value",
        default=0,
        options=set(),
    )


@bpy.app.handlers.persistent
def on_frame_changed(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
    snt_settings = bpy.context.window_manager.shift_and_trace_settings
    if not snt_settings.pin_to_frame:
        return

    bpy.context.scene.tool_settings.use_gpencil_offset_frames = (
        snt_settings.pinned_frame_number == scene.frame_current
    )


def update_onion_skinning_worldspace(*args):
    """Trigger world space onion skinning update."""
    if bpy.context.window_manager.gp_onion_skinning_worldspace_auto_update:
        bpy.ops.gpencil.cache_ghost_frame_transformations()


def gp_onion_skinning_worldspace_auto_update_cb(self, context):
    """WindowManager.gp_onion_skinning_worldspace_auto_update update callback."""
    update_onion_skinning_worldspace()


@bpy.app.handlers.persistent
def on_depsgraph_update_post(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
    """Reacts to depsgraph update to update grease pencil world space onion skinning."""

    if not bpy.context.window_manager.gp_onion_skinning_worldspace_auto_update:
        return

    obact = bpy.context.active_object
    if (
        not isinstance((gpd := obact.data), bpy.types.GreasePencil)
        or not gpd.onion_space == "WORLD"
    ):
        return

    gpd_eval = depsgraph.id_eval_get(gpd)

    for update in depsgraph.updates:
        # If the active gpencil data has been tagged update,
        if gpd_eval == update.id:
            if bpy.app.timers.is_registered(update_onion_skinning_worldspace):
                bpy.app.timers.unregister(update_onion_skinning_worldspace)
            bpy.app.timers.register(
                update_onion_skinning_worldspace, first_interval=0.05
            )
            break


class FlippingUndoHandler:
    """
    Helper class to deal with specific undoing behavior when flipping between
    grease pencil keyframes.

    Undoing a gpencil edit step might both:
        - remove a stroke from a frame
        - and change the current time to the previously active frame

    This behavior can be confusing, as one could expect the stroke to be undone,
    but still stay on the same frame.

    To counteract this behavior, this class stores the last edited frame value after a
    depgraph update, and restore it as current frame after an undo.
    """

    gpencil_edit_geo_modes = ("PAINT_GPENCIL", "SCULPT_GPENCIL", "EDIT_GPENCIL")

    @classmethod
    def register(cls):
        bpy.app.handlers.undo_post.append(cls.on_undo_post)
        bpy.app.handlers.depsgraph_update_post.append(cls.on_depsgraph_update_post)

    @classmethod
    def unregister(cls):
        bpy.app.handlers.undo_post.remove(cls.on_undo_post)
        bpy.app.handlers.depsgraph_update_post.remove(cls.on_depsgraph_update_post)

    @staticmethod
    def get_active_gpd(context):
        obact = context.active_object
        if getattr(obact, "mode") not in FlippingUndoHandler.gpencil_edit_geo_modes:
            return None
        return obact.data

    @staticmethod
    def undo_stick_to_frame() -> bool:
        return get_addon_prefs().anim_flipping_undo_mode == "STICK_TO_FRAME"

    @staticmethod
    @bpy.app.handlers.persistent
    def on_depsgraph_update_post(
        scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph
    ):
        """React on depsgraph update to look for grease pencil data changes."""

        if not FlippingUndoHandler.undo_stick_to_frame():
            return

        if not (gpd := FlippingUndoHandler.get_active_gpd(bpy.context)):
            return

        wm = bpy.context.window_manager

        gpd_id = depsgraph.id_eval_get(gpd)
        for update in depsgraph.updates:
            # If the active gpencil data has been tagged for geometry update,
            # store current frame as last edit frame value.
            if gpd_id == update.id and update.is_updated_geometry:
                wm.gp_last_edit_frame = scene.frame_current

    @staticmethod
    @bpy.app.handlers.persistent
    def on_undo_post(scene: bpy.types.Scene, _):
        """React to undo to reset frame value to last edit frame, if applicable."""
        if not FlippingUndoHandler.undo_stick_to_frame():
            return

        if not (gpd := FlippingUndoHandler.get_active_gpd(bpy.context)):
            return

        wm = bpy.context.window_manager
        # If scene frame has changed but does not match last gpencil edit frame:
        scene_frame = scene.frame_current
        if scene_frame != wm.gp_last_edit_frame:
            # Go back to last edit frame to see the impact of undoing.
            scene.frame_current = wm.gp_last_edit_frame
            # Store the frame value the undo went back to as the last edit frame, for
            # potential next undos to use this as the new reference value.
            wm.gp_last_edit_frame = scene_frame


classes = (
    GPencilFlippingSettings,
    GPencilShiftAndTraceSettings,
    GPencilCurrentKeyframeSettings,
    TRANSFORM_OT_keyframes_shift,
    ANIM_OT_lightbox_edit,
    ANIM_OT_keyframes_flip,
)


def register():
    register_classes(classes)

    bpy.types.GreasePencil.flipping_settings = bpy.props.PointerProperty(
        type=GPencilFlippingSettings,
        description="Keyframes flipping settings",
    )

    bpy.types.GreasePencil.current_keyframe_settings = bpy.props.PointerProperty(
        type=GPencilCurrentKeyframeSettings,
        description="Current Keyframe settings",
    )

    bpy.types.WindowManager.shift_and_trace_settings = bpy.props.PointerProperty(
        type=GPencilShiftAndTraceSettings,
        description="Shift & Trace settings",
    )

    bpy.types.WindowManager.gp_last_edit_frame = bpy.props.IntProperty(
        name="GPencil Last Edit Frame",
        default=-1,
        options={"HIDDEN"},
    )

    bpy.types.WindowManager.gp_onion_skinning_worldspace_auto_update = bpy.props.BoolProperty(
        name="GPencil Onion Skinning World Space Auto Update",
        description="Auto-update world space onion skinning for grease pencil objects",
        default=False,
        update=gp_onion_skinning_worldspace_auto_update_cb,
        options=set(),
    )

    bpy.app.handlers.frame_change_post.append(on_frame_changed)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update_post)

    FlippingUndoHandler.register()


def unregister():
    unregister_classes(classes)
    del bpy.types.GreasePencil.flipping_settings
    del bpy.types.WindowManager.shift_and_trace_settings

    bpy.app.handlers.frame_change_post.remove(on_frame_changed)
    bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update_post)
    FlippingUndoHandler.unregister()
