# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

from typing import Union

import bpy

from spa_anim2D.utils import (
    register_classes,
    remove_auto_numbering_suffix,
    unregister_classes,
)

# Default material palette identifier
DEFAULT_PALETTE_ID = "-"
# Character used to split material name into palette and basename components
PALETTE_NAME_SEPARATOR: str = "/"

MaterialPalettesRegistry = dict[str, list[bpy.types.Material]]
# Global material palettes registry
material_palettes: MaterialPalettesRegistry = {}

# Material names for vertex color painting
VERTEXCOLOR_PALETTE = "VertexColor"
VERTEXCOLOR_MAT_LINE = f"{VERTEXCOLOR_PALETTE}/Line"
VERTEXCOLOR_MAT_FILL = f"{VERTEXCOLOR_PALETTE}/Fill"


# The list of attributes to evaluate whether 2 grease pencil materials are similar
gp_material_comparison_attributes = (
    "show_stroke",
    "mode",
    "stroke_style",
    "color",
    "use_stroke_holdout",
    "use_overlap_strokes",
    "show_fill",
    "fill_style",
    "fill_color",
    "use_fill_holdout",
)


def clear_material_palettes():
    """Clear the global material palettes registry."""
    material_palettes.clear()


def split_material_name(name: str) -> list[str]:
    """
    Split a material name into palette and basename components using
    PALETTE_NAME_SEPARATOR.

    :return: A list with palette name and basename, or basename only if no palette info was found.
    """
    return name.split(PALETTE_NAME_SEPARATOR, 1)


def get_palette_name(material: bpy.types.Material) -> Union[str, None]:
    """Get a palette name from `material`'s name.

    :param material: The material to consider.
    :return: The name of the palette if found, None otherwise.
    """
    split = split_material_name(material.name)
    return split[0] if len(split) > 1 else None


def get_material_basename(material: bpy.types.Material) -> str:
    """Get `material`'s name without the palette component (if any).

    :param material: The material to consider.
    :return: The basename of the material.
    """
    return split_material_name(material.name)[-1]


def has_valid_palette_name(material: bpy.types.Material) -> bool:
    """
    Returns whether `material`'s name contain a valid material palette component, i.e
    a palette that is registered in the global material palettes dictionnary.

    :param material: The material to consider.
    :return: Whether the palette component of material's name is valid.
    """
    return get_palette_name(material) in material_palettes


def get_grease_pencil_materials(only_local: bool = False) -> list[bpy.types.Material]:
    """Returns the list of grease pencil materials.

    :param only_local: Whether to include only materials local to this file.
    """
    return [
        mat
        for mat in bpy.data.materials
        if mat.is_grease_pencil and (not mat.library or not only_local)
    ]


def are_similar_gp_materials(
    materialA: bpy.types.Material, materialB: bpy.types.Material
) -> bool:
    """Return whether the two grease pencil materials have identical parameters and can
    therefore be considered as similar.

    :param materialA: The first grease pencil material.
    :param materialB: The second grease pencil material.
    :return: Whether the two materials have strictly identical values.
    """
    if not materialA.is_grease_pencil or not materialB.is_grease_pencil:
        raise ValueError("This method only works on grease pencil materials")

    for attr in gp_material_comparison_attributes:
        attrA = getattr(materialA.grease_pencil, attr)
        attrB = getattr(materialB.grease_pencil, attr)
        # Turn bpy_prop_array into lists for equality test to work on values
        if isinstance(attrA, bpy.types.bpy_prop_array):
            attrA = attrA[:]
            attrB = attrB[:]

        if attrA != attrB:
            return False

    return True


def cleanup_duplicated_materials():
    """Remove duplicated grease pencil materials to keep only unique instances."""
    similar_material_candidates: dict[str, list[bpy.types.Material]] = {}

    # First pass: create groups of potientially similar materials by name.
    # Group materials with the same "short name" (name without any auto-numbering suffix).
    # NOTE: Cleanup can only affect local materials.
    for mat in get_grease_pencil_materials(only_local=True):
        short_name = remove_auto_numbering_suffix(mat.name)
        if not get_palette_name(mat):
            continue
        if short_name not in similar_material_candidates:
            similar_material_candidates[short_name] = []
        similar_material_candidates[short_name].append(mat)

    # Second pass: find similar materials within those groups.
    orphan_mats = set()
    # Iterate over material groups
    for materials in similar_material_candidates.values():
        # If only one material in this group, nothing to do (no duplicates)
        if len(materials) == 1:
            continue
        # Iterate over each material in this group
        for i, matA in enumerate(materials):
            # If a material has already been considered as a duplicate, skip it.
            if matA in orphan_mats:
                continue
            # Compare this material "A" to all the next ones in the list
            for matB in materials[i + 1 :]:
                # If another material "B" is similar to "A", remap users of "B" to "A".
                # Mark "B" as orphaned by this process.
                if are_similar_gp_materials(matA, matB):
                    matB.user_remap(matA)
                    orphan_mats.add(matB)

    # Finally, remove all materials orphaned by the cleanup process.
    bpy.data.batch_remove(orphan_mats)


def refresh_palettes(cleanup_materials: bool = False):
    """
    Clear and rebuild material palettes registry based on existing material datablocks.
    """
    clear_material_palettes()

    # Ensure bpy.data is fully initialized before accessing materials datablocks
    if not isinstance(bpy.data, bpy.types.BlendData):
        return

    # Clean duplicated materials
    if cleanup_materials:
        cleanup_duplicated_materials()

    # Initialize default palette
    material_palettes[DEFAULT_PALETTE_ID] = []

    # Iterate over grease pencil materials and fill the material palettes registry
    for mat in get_grease_pencil_materials():
        palette = get_palette_name(mat)
        # Discard material without palette info in their names
        if not palette:
            continue
        # Discard material using the placeholder DEFAULT_PALETTE_ID
        if palette == DEFAULT_PALETTE_ID:
            # NOTE: this should probably raise or log an error
            continue
        if palette not in material_palettes:
            material_palettes[palette] = []
        material_palettes[palette].append(mat)

    if cleanup_materials:
        # Re-assign palette materials to grease pencil objects
        for gp in bpy.data.grease_pencils:
            assign_active_palette_materials(gp)


def assign_active_palette_materials(gpencil: bpy.types.GreasePencil):
    """Assign to `gpencil` its active palette's materials.

    :param gpencil: The grease pencil data to assign materials to.
    """
    # Switch back to default palette if active palette is not valid anymore.
    # This could happen if all materials from a palette have been deleted after
    # the previous palettes registry refresh.
    if gpencil.material_palette not in material_palettes:
        gpencil.material_palette = DEFAULT_PALETTE_ID
        return

    # Assign new materials
    for mat in material_palettes[gpencil.material_palette]:
        if mat not in gpencil.materials.values():
            gpencil.materials.append(mat)


@bpy.app.handlers.persistent
def on_load_pre(*args):
    """File load_pre callback."""
    # Clear the material palettes registry to avoid keeping refs to material datablocks
    clear_material_palettes()


@bpy.app.handlers.persistent
def on_load_post(*args):
    """File load_post callback."""
    # Initialize the material palettes registry after opening a file
    refresh_palettes()


@bpy.app.handlers.persistent
def on_undo_redo(*args):
    """Undo-redo callback."""
    refresh_palettes()


def set_material_palette_value(self, index: int):
    """GreasePencil.material_palette set function."""
    # Store the enum value for current palette as its string value (instead of int).
    # This is to avoid the enum index value getting out of sync with the content
    # of the material palettes registry.
    self["material_palette_str"] = list(material_palettes)[index]


def get_material_palette_value(self):
    """GreasePencil.material_palette get function."""
    if "material_palette_str" in self:
        try:
            # Compute enum index using palette name index in material palettes registry
            return list(material_palettes).index(self["material_palette_str"])
        except ValueError:
            # Fallback to default palette if the stored one is not found
            self["material_palette_str"] = DEFAULT_PALETTE_ID
    return 0


def update_gpencil_palette(gpencil: bpy.types.GreasePencil, context):
    """React to `GreasePencil.material_palette` property updates and assign
    corresponding materials to the `gpencil` datablock.
    """
    assign_active_palette_materials(gpencil)


def get_material_palettes_enum_items(self, context):
    """Build the items for `GreasePencil.material_palette` EnumProperty."""
    # To get proper enum values, we need to make sure material palettes are initialized
    if not material_palettes:
        refresh_palettes()

    # Return currently registered palettes except for the internal ones
    # (e.g: palette used for vertex color mode)
    return (
        (palette, palette, "", i)
        for i, palette in enumerate(material_palettes)
        if palette != VERTEXCOLOR_PALETTE
    )


def initialize_palettes():
    """Refresh material palettes if not initialized yet."""
    if not material_palettes:
        refresh_palettes()


def init_vertex_color_materials():
    """Initialize default materials for vertex color painting"""
    # Simple line material
    if not bpy.data.materials.get(VERTEXCOLOR_MAT_LINE):
        line = bpy.data.materials.new(VERTEXCOLOR_MAT_LINE)
        bpy.data.materials.create_gpencil_data(line)
        line.grease_pencil.color = 0.0, 0.0, 0.0, 1.0
        line.grease_pencil.show_stroke = True
        line.grease_pencil.show_fill = False

    # Simple fill material
    if not bpy.data.materials.get(VERTEXCOLOR_MAT_FILL):
        fill = bpy.data.materials.new(VERTEXCOLOR_MAT_FILL)
        bpy.data.materials.create_gpencil_data(fill)
        fill.grease_pencil.fill_color = 0.5, 0.5, 0.5, 1.0
        fill.grease_pencil.show_stroke = False
        fill.grease_pencil.show_fill = True


class PaintColorSettings(bpy.types.PropertyGroup):
    def mode_update_cb(self, context: bpy.types.Context):
        scene = self.id_data
        gpencil_paint = scene.tool_settings.gpencil_paint
        gp_settings = gpencil_paint.brush.gpencil_settings
        # Update matching property in tool settings
        gpencil_paint.color_mode = self.mode

        # Toggle material pin based on current mode:
        # - MATERIAL: OFF - relies on object's already assigned materials
        # - VERTEXCOLOR: ON - uses default materials, assign on use
        use_material_pin = self.mode == "VERTEXCOLOR"
        if gp_settings.use_material_pin != use_material_pin:
            gp_settings.use_material_pin = use_material_pin
        # Update material used for vertex color
        if self.mode == "VERTEXCOLOR":
            self.vertex_color_style_update_cb(context)

    mode: bpy.props.EnumProperty(
        name="Paint Color Mode",
        description="Grease pencil paint color mode",
        items=(
            ("MATERIAL", "Material", "Use object's srease pencil materials"),
            ("VERTEXCOLOR", "Vertex Color", "Use vertex colors"),
        ),
        update=mode_update_cb,
    )

    def vertex_color_style_update_cb(self, context):
        scene = self.id_data
        gp_settings = scene.tool_settings.gpencil_paint.brush.gpencil_settings
        # Initialize vertex color materials if necessary
        if not bpy.data.materials.get(self.vertex_color_style):
            init_vertex_color_materials()
        # Ensure material pin is activated
        if self.mode == "VERTEXCOLOR":
            if not gp_settings.use_material_pin:
                gp_settings.use_material_pin = True
            # Use vertex mode impacts both stroke and fill
            gp_settings.vertex_mode = "BOTH"
        material = bpy.data.materials.get(self.vertex_color_style)
        # Set the pinned material to match the current paint style
        if gp_settings.material != material:
            gp_settings.material = material

    vertex_color_style: bpy.props.EnumProperty(
        name="Vertex Color Style",
        description="Material used for vertex color painting",
        items=(
            (VERTEXCOLOR_MAT_LINE, "Line", "Line style", "ANTIALIASED", 0),
            (VERTEXCOLOR_MAT_FILL, "Fill", "Fill style", "SHADING_SOLID", 1),
        ),
        update=vertex_color_style_update_cb,
    )


classes = (PaintColorSettings,)


def register():
    register_classes(classes)

    # Store active material palette on GreasePencil datablocks.
    # See also: set, get and update functions for additional info.
    bpy.types.GreasePencil.material_palette = bpy.props.EnumProperty(
        name="Material Palette",
        items=get_material_palettes_enum_items,
        update=update_gpencil_palette,
        set=set_material_palette_value,
        get=get_material_palette_value,
        options=set(),
    )

    bpy.types.Scene.gp_paint_color = bpy.props.PointerProperty(type=PaintColorSettings)

    bpy.app.handlers.load_pre.append(on_load_pre)
    bpy.app.handlers.load_post.append(on_load_post)
    bpy.app.handlers.undo_post.append(on_undo_redo)
    bpy.app.handlers.redo_post.append(on_undo_redo)

    # Initialize material palettes in the next event loop, since bpy.data is not fully
    # accessible at addon registration time.
    # NOTE: timer functions are not consumed in background mode and end up leaking memory,
    #       even if unregistered.
    if not bpy.app.background:
        bpy.app.timers.register(initialize_palettes)


def unregister():
    clear_material_palettes()

    unregister_classes(classes)

    del bpy.types.GreasePencil.material_palette
    del bpy.types.Scene.gp_paint_color

    bpy.app.handlers.load_pre.remove(on_load_pre)
    bpy.app.handlers.load_post.remove(on_load_post)
    bpy.app.handlers.undo_post.remove(on_undo_redo)
    bpy.app.handlers.redo_post.remove(on_undo_redo)
