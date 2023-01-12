# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import pytest

import bpy

from spa_anim2D.materials.core import (
    DEFAULT_PALETTE_ID,
    clear_material_palettes,
    material_palettes,
    refresh_palettes,
)


def create_gp_material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    bpy.data.materials.create_gpencil_data(mat)
    return mat


def test_material_palettes_initialization():
    clear_material_palettes()
    assert len(material_palettes) == 0
    refresh_palettes()
    # Default palette should be available after initialization
    assert len(material_palettes) == 1
    assert DEFAULT_PALETTE_ID in material_palettes


def test_new_material_palette():
    # Create a new non GP material with palette info
    matA = bpy.data.materials.new("Palette/MatA")
    refresh_palettes()
    # This should not create a new palette since this is not a GP material
    assert len(material_palettes) == 1
    # Create GP data for this material
    bpy.data.materials.create_gpencil_data(matA)
    refresh_palettes()
    # This should now create a new palette
    assert len(material_palettes) == 2
    assert "Palette" in material_palettes

    # Add a second GP material with the same palette name
    create_gp_material("Palette/MatB")
    refresh_palettes()
    assert len(material_palettes) == 2
    # There should now be 2 materials in this palette
    assert len(material_palettes["Palette"]) == 2


def test_gp_material_without_palette_info():
    # Create a GP material without palette info
    create_gp_material("Mat")
    refresh_palettes()
    # This should not create a palette
    assert len(material_palettes) == 1


def test_multiple_material_palettes():
    # Create 4 material definining 3 palettes
    create_gp_material("A/MatA")
    create_gp_material("A/MatB")
    create_gp_material("B/Mat")
    create_gp_material("C/Mat")

    refresh_palettes()
    # This should have created 3 palettes
    assert len(material_palettes) == 4
    assert "A" in material_palettes
    assert "B" in material_palettes
    assert "C" in material_palettes

    # Ensure material count for each palette
    assert len(material_palettes["A"]) == 2
    assert len(material_palettes["B"]) == 1
    assert len(material_palettes["C"]) == 1


def test_remove_unique_material_from_palette():
    # Create a GP material with palette info
    mat = create_gp_material("Palette/Mat")
    refresh_palettes()
    assert len(material_palettes) == 2
    # Delete this material
    bpy.data.materials.remove(mat)
    refresh_palettes()
    # Palette should not exist anymore
    assert len(material_palettes) == 1


def test_assign_valid_palette():
    # Create a new palette with 2 materials
    matA = create_gp_material("Palette/MatA")
    matB = create_gp_material("Palette/MatB")
    refresh_palettes()
    # Assign this palette to a GP datablock
    gp = bpy.data.grease_pencils.new("GP")
    gp.material_palette = "Palette"
    # Ensure materials are properly assigned
    assert matA.name in gp.materials
    assert matB.name in gp.materials


def test_assign_invalid_palette():
    gp = bpy.data.grease_pencils.new("GP")
    # Assigning an invalid palette should raise
    with pytest.raises(TypeError):
        gp.material_palette = "FakePalette"


def test_fallback_to_default_palette():
    mat = create_gp_material("Palette/Mat")
    refresh_palettes()
    assert len(material_palettes) == 2

    gp = bpy.data.grease_pencils.new("GP")
    gp.material_palette = "Palette"
    assert mat.name in gp.materials

    bpy.data.materials.remove(mat)
    refresh_palettes()
    assert len(material_palettes) == 1
    # GP should be reset to default palette when accessed
    assert gp.material_palette == DEFAULT_PALETTE_ID


def test_undo_redo_material_palette_cache():
    palette_name = "Palette"
    material_name = f"{palette_name}/Mat"
    # [UndoStack] Initialize
    bpy.ops.ed.undo_push()
    mat = create_gp_material(material_name)
    gp_name = "GP"
    gp = bpy.data.grease_pencils.new(gp_name)
    refresh_palettes()
    # [UndoStack] Before palette assignment
    bpy.ops.ed.undo_push()
    gp.material_palette = palette_name
    # [UndoStack] After palette assignment
    bpy.ops.ed.undo_push()
    # [UndoStack] Undo palette assignment
    bpy.ops.ed.undo()

    # Retrieve object by name (previous reference is invalid after undo)
    gp = bpy.data.grease_pencils[gp_name]
    # Make sure cached values were properly updated after undo
    assert len(material_palettes[palette_name]) == 1
    assert material_palettes[palette_name][0].name == material_name
    # Reassign palette without refreshing shoud work
    gp.material_palette = palette_name
    assert len(gp.materials) == 1
    assert gp.materials[0].name == material_name


def test_undo_redo_material_deletion():
    palette_name = "Palette"
    material_name = f"{palette_name}/Mat"
    # [UndoStack] Initialize
    bpy.ops.ed.undo_push()
    mat = create_gp_material(material_name)
    gp = bpy.data.grease_pencils.new("GP")
    refresh_palettes()
    assert len(material_palettes) == 2
    # [UndoStack] Before material deletion
    bpy.ops.ed.undo_push()
    bpy.data.materials.remove(mat)
    # [UndoStack] After material deletion
    bpy.ops.ed.undo_push()

    # Assignation refresh palettes, therefore this should fallback to the default one.
    refresh_palettes()
    assert gp.material_palette == DEFAULT_PALETTE_ID
    assert len(gp.materials) == 0
    assert len(material_palettes) == 1

    # [UndoStack] Undo material deletion
    bpy.ops.ed.undo()

    # Previous material reference is not valid anymore
    with pytest.raises(ReferenceError):
        getattr(mat, "name")

    # Retrieve restored material by name
    mat = bpy.data.materials.get(material_name, None)
    assert mat is not None
    # Palette should be available again
    refresh_palettes()
    assert material_palettes[palette_name][0] == mat
    # Set palette on GP and ensure material is assigned
    gp.material_palette = palette_name
    assert mat.name in gp.materials


def test_palette_cleanup_identical_materials():
    # Create a GP material and a copy of it
    matA = create_gp_material("A/MatA")
    matA_dup = matA.copy()
    assert matA_dup.name == f"{matA.name}.001"
    # Refresh palettes with cleanup
    refresh_palettes(cleanup_materials=True)
    # The identical copy of the first material should have been removed
    with pytest.raises(ReferenceError):
        getattr(matA_dup, "name")


def test_palette_cleanup_identical_materials_ending_with_non_word_char():
    # Create a GP material ending with a non-word character and a copy of it
    matA = create_gp_material("A/MatA 20%")
    matA_dup = matA.copy()
    assert matA_dup.name == f"{matA.name}.001"
    # Refresh palettes with cleanup
    refresh_palettes(cleanup_materials=True)
    # The identical copy of the first material should have been removed
    with pytest.raises(ReferenceError):
        getattr(matA_dup, "name")


def test_palette_assignation_identical_materials():
    # Create a GP material
    matA = create_gp_material("A/MatA")
    # Initial palettes refresh
    refresh_palettes()

    # Assign palette "A" to a GP datablock
    gp = bpy.data.grease_pencils.new("GP")
    gp.material_palette = "A"

    # Duplicate the GP material
    matA_dup = matA.copy()
    assert matA_dup.name == f"{matA.name}.001"

    # Refresh palettes with cleanup
    refresh_palettes(cleanup_materials=True)

    # The identical copy of the first material should not have been assigned to GP
    assert len(gp.materials) == 1
    # And it should have been removed
    with pytest.raises(ReferenceError):
        getattr(matA_dup, "name")


def test_palette_cleanup_similar_materials_name_different_settings():
    # Create a GP material and a copy of it
    matA = create_gp_material("A/MatA")
    matA_dup = matA.copy()
    assert matA_dup.name == f"{matA.name}.001"

    # Change the color of the material
    matA_dup.grease_pencil.color = 1.0, 0.0, 0.0, 1.0
    # Refresh palettes with cleanup
    refresh_palettes(cleanup_materials=True)
    # The second material should not have been removed, since it has different settings
    assert matA_dup.name in bpy.data.materials


def test_palette_assignation_similar_materials_name_different_settings():
    # Create a GP material and a copy of it
    matA = create_gp_material("A/MatA")
    refresh_palettes(cleanup_materials=True)

    # Assign palette "A" to a GP datablock
    gp = bpy.data.grease_pencils.new("GP")
    gp.material_palette = "A"

    matA_dup = matA.copy()
    assert matA_dup.name == f"{matA.name}.001"
    # Change the color of the material
    matA_dup.grease_pencil.color = 1.0, 0.0, 0.0, 1.0

    # Refresh palettes
    refresh_palettes(cleanup_materials=True)

    # The duplicated material should still be valid and now assigned to the GP
    assert matA_dup.name in bpy.data.materials
    assert len(gp.materials) == 2


def test_palette_cleanup_multiple_identical_materials():
    # Create a GP material and several copy of it
    matA = create_gp_material("A/MatA")
    duplicates = [matA.copy() for i in range(4)]

    # Create a GP and assign it the duplicated materials "manually"
    gp = bpy.data.grease_pencils.new("GP")
    for mat in duplicates:
        gp.materials.append(mat)

    # The original material has no user at this point
    assert matA.users == 0
    # Refresh palettes with cleanup
    refresh_palettes(cleanup_materials=True)

    # GP material slots should now use the original material due to user remapping
    assert matA.users == len(duplicates)

    # The duplicates should also have been deleted
    for mat in duplicates:
        with pytest.raises(ReferenceError):
            getattr(mat, "name")


def test_palette_refresh_several_objects():
    # Create a GP material
    matA = create_gp_material("A/MatA")
    refresh_palettes()

    # Create GP objects and assign palette
    gp = bpy.data.grease_pencils.new("GP")
    gp2 = bpy.data.grease_pencils.new("GP2")

    gp.material_palette = "A"
    gp2.material_palette = "A"

    assert len(gp.materials) == len(gp2.materials) == 1

    # Add a new material to the palette and refresh
    matB = create_gp_material("A/MatB")
    refresh_palettes(cleanup_materials=True)

    # GP objects should now have 2 materials assigned
    assert len(gp.materials) == len(gp2.materials) == 2
