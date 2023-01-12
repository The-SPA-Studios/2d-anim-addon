# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

from datetime import datetime
import os
from pathlib import Path
import tempfile

import bpy

try:
    from PIL import ImageGrab, Image

    PILLOW_AVAILABLE = True
except ModuleNotFoundError:
    PILLOW_AVAILABLE = False

from bpy_extras.io_utils import ImportHelper
from spa_anim2D.gpencil_references.core import import_image_as_gp_reference
from spa_anim2D.utils import register_classes, unregister_classes


class IMPORT_OT_gpencil_reference_from_clipboard(bpy.types.Operator):
    bl_idname = "import.gpencil_reference_from_clipboard"
    bl_label = "Paste Reference from Clipboard"
    bl_description = "Paste the image in the clipboard as a grease pencil reference"
    bl_options = {"UNDO"}

    bl_keymaps = [
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "V",
            "ctrl": True,
            "shift": True,
        }
    ]

    @classmethod
    def poll(cls, context: bpy.types.Context):
        if not getattr(context.active_object, "type", None) == "GPENCIL":
            return False
        if not isinstance(context.region.data, bpy.types.RegionView3D):
            return False
        return True

    def execute(self, context: bpy.types.Context):
        obj = context.active_object
        gpd = obj.data

        img_filepaths = []
        pack_image = True
        try:
            img_clip = ImageGrab.grabclipboard()
            # If clipboard contains filepaths, keep only supported images.
            if isinstance(img_clip, list):
                img_filepaths = [
                    filepath
                    for filepath in img_clip
                    if Path(filepath).suffix in bpy.path.extensions_image
                ]
                # Don't pack external images by default.
                # User can chose to pack those references afterwards.
                pack_image = False
            # If clipboard contains an image buffer, save it on disk.
            elif isinstance(img_clip, Image.Image):
                name = f"clipboard-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.png"
                img_path = os.path.join(tempfile.gettempdir(), name)
                img_clip.save(img_path)
                img_filepaths = [img_path]

        except NotImplementedError:
            self.report({"ERROR"}, "Import from clipboard not supported")
            return {"CANCELLED"}

        if not img_filepaths:
            self.report({"ERROR"}, "No image in clipboard")
            return {"CANCELLED"}

        gpl = gpd.layers.active if gpd.layers.active else gpd.layers.new("References")
        gpd.layers.active = gpl

        for filepath in img_filepaths:
            import_image_as_gp_reference(
                context,
                obj,
                filepath,
                pack_image,
                add_new_layer=False,
                add_new_keyframe=False,
            )

        return {"FINISHED"}


class IMPORT_OT_gpencil_references_from_file(bpy.types.Operator, ImportHelper):
    bl_idname = "import.gpencil_references_from_file"
    bl_label = "Import Reference(s) From File"
    bl_description = "Import grease pencil reference(s) from image file(s)"
    bl_options = {"UNDO"}

    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg;*.exr;*.tiff;*bmp;*.gif;", options={"HIDDEN"}
    )

    files: bpy.props.CollectionProperty(
        name="Images",
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    directory: bpy.props.StringProperty()

    pack_image: bpy.props.BoolProperty(
        name="Pack Image(s)",
        description="Pack the imported image(s) into the .blend file",
        default=False,
    )

    create_layer: bpy.props.BoolProperty(
        name="Create New Layer(s)",
        description="Create new layer(s) for the reference image(s)",
        default=False,
    )

    as_sequence: bpy.props.BoolProperty(
        name="Frame Sequence",
        description="Insert the images on a sequence of frames",
        default=False,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        if not getattr(context.active_object, "type", None) == "GPENCIL":
            return False
        if not isinstance(context.region.data, bpy.types.RegionView3D):
            return False
        return True

    def execute(self, context: bpy.types.Context):

        bpy.ops.gpencil.select_all(action="DESELECT")

        gpd = context.active_object.data

        create_layer = self.create_layer

        frame_current = context.scene.frame_current

        # Only create one new layer when importing images as sequence.
        if self.create_layer and self.as_sequence:
            gpd.layers.new(self.files[0].name)
            create_layer = False

        for elem in sorted(self.files, key=lambda f: f.name):
            import_image_as_gp_reference(
                context,
                context.active_object,
                os.path.join(self.directory, elem.name),
                self.pack_image,
                create_layer,
                self.as_sequence,
            )

            # Advance to the next frame
            if self.as_sequence:
                context.scene.frame_current += 1

        context.scene.frame_current = frame_current

        return {"FINISHED"}


classes = (IMPORT_OT_gpencil_references_from_file,)

extra_classes = (IMPORT_OT_gpencil_reference_from_clipboard,)


def register():
    register_classes(classes)
    if PILLOW_AVAILABLE:
        register_classes(extra_classes)


def unregister():
    unregister_classes(classes)
    if PILLOW_AVAILABLE:
        unregister_classes(extra_classes)
