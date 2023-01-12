# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import math
from typing import Optional

import bpy
import mathutils


# Object for handling msgbus subscribers ownership
msgbus_owner = object()


def is_parented_to(obj: bpy.types.Object, other: bpy.types.Object) -> bool:
    """
    Returns whether `obj` is parented to `other`. This includes direct
    hierarchy parenting and "CHILD_OF" constraints.

    :param obj: The object to consider.
    :param other: The object to test for parent
    :return: Whether `obj` is parented to `other`.
    """
    if not obj:
        return False
    # Test direct parent
    if obj.parent == other:
        return True
    # Look for a CHILD_OF constraint with a matching target
    constraint = next(
        (c for c in obj.constraints if c.type == "CHILD_OF" and c.target == other),
        None,
    )

    return constraint is not None


def set_parent(
    obj: bpy.types.Object, parent: bpy.types.Object, use_contraint: bool = False
):
    """Parent `obj` to `parent` by direct hierarchy parenting or by using a constraint
    if `use_contraint` is True.

    :param obj: The object to consider.
    :param parent: The parent object.
    :param use_contraint: Whether to use a "CHILD_OF" contraint.
    """
    if use_contraint:
        constraint = obj.constraints.new(type="CHILD_OF")
        constraint.target = parent
    else:
        obj.parent = parent
        obj.matrix_parent_inverse = obj.parent.matrix_world.inverted()


def clear_parent(obj: bpy.types.Object, parent: bpy.types.Object):
    """
    Unparent `obj` from `parent`, considering direct hierarchy parenting and
    CHILD_OF constraint.

    :param obj: The object to consider.
    :param parent: The object to unparent from.
    """
    if obj.parent == parent:
        matrix = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = matrix
    else:
        for c in (
            c for c in obj.constraints if c.type == "CHILD_OF" and c.target == parent
        ):
            matrix = obj.matrix_world.copy()
            obj.constraints.remove(c)
            obj.matrix_world = matrix


def create_gpencil_object(
    context: bpy.types.Context,
    name: str,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """
    Add a new grease pencil object with default layers.

    :param context: The current context.
    :param name: The grease pencil object's name.
    :param collection: The collection to link the object into (scene collection if None).
    :return: The newly created grease pencil object.
    """
    # Store active mode and whether to restore it
    active_mode = context.mode
    # Use getattr to handle active_object being None
    restore_mode = getattr(context.active_object, "type", "") == "GPENCIL"

    # Create new GP object
    gpd = bpy.data.grease_pencils.new(name=name)
    gp = bpy.data.objects.new(name=gpd.name, object_data=gpd)
    # Link object into collection
    (collection or context.scene.collection).objects.link(gp)
    context.view_layer.objects.active = gp

    # Create default layers and initial empty keyframes
    layers = ("Fill", "Lines")
    for layer_name in layers:
        layer = gp.data.layers.new(name=layer_name)
        layer.frames.new(frame_number=context.scene.frame_start)

    # Restore previously active GP mode
    if restore_mode:
        bpy.ops.object.mode_set(mode=active_mode)

    return gp


def orient_to_view(
    obj: bpy.types.Object,
    view_matrix: mathutils.Matrix,
    axis: tuple[bool, bool, bool] = (True, True, True),
):
    """Orient `obj` to face the view defined by `view_matrix` on specified axis.

    :param obj: The object to orient.
    :param view_matrix: The view matrix.
    :param axis: Object axis that should be impacted (X, Y, Z).
    """
    quat = mathutils.Quaternion(mathutils.Vector((1.0, 0.0, 0.0)), math.radians(-90.0))
    quat.rotate(view_matrix.inverted().to_quaternion())
    euler = quat.to_euler()

    if axis[0]:
        obj.rotation_euler.x = euler.x
    if axis[1]:
        obj.rotation_euler.y = euler.y
    if axis[2]:
        obj.rotation_euler.z = euler.z

    # Update matrix parent inverse if object is parented to preserve location
    if obj.parent:
        loc = obj.matrix_world.translation.copy()
        obj.matrix_parent_inverse = obj.parent.matrix_world.inverted()
        obj.location = loc


def get_active_gp_object() -> Optional[bpy.types.Object]:
    """Get the active grease pencil object if any, None otherwise."""
    active_obj = bpy.context.active_object
    if not active_obj or not isinstance(active_obj.data, bpy.types.GreasePencil):
        return None
    return active_obj


# Active GP object change selection behavior flag.
# See `active_object_changed` and `active_gp_index_update_callback` for usage.
gp_select_only_active_on_change = True


def active_object_changed():
    """Active object changed callback."""
    if not (gp_object := get_active_gp_object()):
        bpy.context.scene.active_gp_index = -1
        return
    idx = bpy.context.scene.objects.values().index(gp_object)
    if idx != bpy.context.scene.active_gp_index:
        # When coming from an external event (e.g: from the outliner), we should not
        # take care of updating object selection in `active_gp_index_update_callback`,
        # as it could be part of a multi-selection operation.
        # Use the selection flag to indicate that.
        global gp_select_only_active_on_change
        gp_select_only_active_on_change = False
        bpy.context.scene.active_gp_index = idx


def select_only(
    context: bpy.types.Context, obj: bpy.types.Object, children: bool = False
):
    """
    Ensure `obj` is the only selected object (optionnaly with its children) in the
    given `context`.

    :param context: The active context.
    :param obj: The object to select.
    :param children: Whether to also select object's children.
    """
    if not children and len(context.selected_objects) == 1 and obj.select_get():
        return

    # Deselect currently selected objects.
    for item in context.selected_objects:
        item.select_set(False)

    # Select target object - and its children if the option is enabled.
    obj.select_set(True)
    if children:
        for item in obj.children:
            item.select_set(True)


@bpy.app.handlers.persistent
def msgbus_subscribe(*args):
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.LayerObjects, "active"),
        owner=msgbus_owner,
        args=(),
        notify=active_object_changed,
    )


@bpy.app.handlers.persistent
def msgbus_unsubscribe(*args):
    bpy.msgbus.clear_by_owner(msgbus_owner)


def set_gpencil_mode_safe(
    context: bpy.types.Context, gpencil: bpy.types.Object, mode: str
):
    """
    Safely set the interaction `mode` on `gpencil` by handling inconsistencies
    between object mode and internal gpencil data flags that could lead to errors.

    :param context: The current context
    :param gpencil: The grease pencil object to set the mode of
    :param mode: The mode to activate
    """
    # Override context: "object.mode_set" uses view_layer's active object
    with context.temp_override(
        scene=context.window.scene,
        view_layer=context.window.scene.view_layers[0],
        active_object=gpencil,
    ):
        # There might be inconsistencies between the object interaction mode and
        # the mode flag on the gp data itself (is_stroke_{modename}_mode).
        # When that happens, switching to the mode fails.
        # If data flag for this mode is already activated, switch to the safe
        # 'EDIT_GPENCIL' mode first as a workaround to sync back the flags.
        if mode not in ("OBJECT", "EDIT_GPENCIL"):
            # Get short name for this mode to build data flag
            # e.g: PAINT_GPENCIL => paint
            mode_short = mode.split("_")[0].lower()
            # Switch to edit mode first if data flags is activated
            if getattr(gpencil.data, f"is_stroke_{mode_short}_mode", False):
                bpy.ops.object.mode_set(mode="EDIT_GPENCIL")
        # Switch the object interaction mode
        bpy.ops.object.mode_set(mode=mode)


def active_gp_index_update_callback(scene: bpy.types.Scene, context: bpy.types.Context):
    """Callback on active scene.active_gp_index value change."""
    # Discard invalid values
    if context.scene.active_gp_index < 0 or context.scene.active_gp_index >= len(
        context.scene.objects
    ):
        return
    # Retrieve matching object by index.
    target_obj = scene.objects[context.scene.active_gp_index]

    global gp_select_only_active_on_change
    # Make sure target object is the only selected object.
    if gp_select_only_active_on_change:
        select_only(context, target_obj)
    else:
        # Don't update selection and reset selection flag to default behavior.
        gp_select_only_active_on_change = True

    # If it's already the active one, early return.
    if target_obj == context.active_object:
        return

    # Store mode of the active object if it is a grease pencil
    mode = ""
    if active_gp := get_active_gp_object():
        mode = active_gp.mode

    # Make the target object active.
    context.view_layer.objects.active = target_obj
    # Restore mode if applicable
    if mode and mode != target_obj.mode and target_obj.visible_get():
        set_gpencil_mode_safe(context, target_obj, mode)


def refresh_quick_edit_gizmo(context: bpy.types.Context):
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if (
        tool is not None
        and tool.mode == "PAINT_GPENCIL"
        and tool.widget == "VIEW3D_GGT_gpencil_xform_box"
    ):
        bpy.ops.wm.tool_set_by_id(name="builtin.select_lasso")


def register():
    bpy.types.Scene.active_gp_index = bpy.props.IntProperty(
        name="Active GP Index", update=active_gp_index_update_callback
    )

    # Subscribe to msgbug at register time
    msgbus_subscribe()

    # Also subscribe on load_post event to keep receiving messages
    # after a file is loaded
    bpy.app.handlers.load_post.append(msgbus_subscribe)
    # (and unsubscribe on load_pre beforehands)
    bpy.app.handlers.load_pre.append(msgbus_unsubscribe)


def unregister():
    del bpy.types.Scene.active_gp_index

    # Unsubscribe to msgbus and remove related handlers
    msgbus_unsubscribe()
    bpy.app.handlers.load_post.remove(msgbus_subscribe)
    bpy.app.handlers.load_pre.remove(msgbus_unsubscribe)
