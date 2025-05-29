'''
Copyright (C) 2025 Israel Andrew Brown

Created by Israel Andrew Brown

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

bl_info = {
    "name": "Save/Import Selection as .blend",
    "author": "Israel-Andrew-Brown_Jamaica",
    "version": (1, 0, 0),
    "blender": (3, 2, 0),
    "location": "File > Export/Import > Save/Import Selection",
    "description": "Saves and imports selected objects to/from .blend files.",
    "category": "Import-Export",
}

import bpy
import os

# ============================================================================
# SAVE SELECTION FUNCTIONALITY
# ============================================================================

def get_selected_collections(context):
    """
    Uses a temporary override to obtain selected collections from the Outliner.
    Returns a list of bpy.types.Collection that are both selected and visible.
    """
    selected = []
    outliner_area = next((area for area in context.window.screen.areas if area.type == 'OUTLINER'), None)
    if outliner_area:
        region = next((r for r in outliner_area.regions if r.type == 'WINDOW'), None)
        with context.temp_override(window=context.window, screen=context.screen, area=outliner_area, region=region):
            if hasattr(bpy.context, "selected_ids"):
                for id_item in bpy.context.selected_ids:
                    if isinstance(id_item, bpy.types.Collection) and not id_item.hide_viewport:
                        selected.append(id_item)
    return selected

def find_parent_collection(target, current):
    """
    Recursively search for the parent of 'target' starting from 'current'.
    Returns the parent collection if found, or None otherwise.
    """
    for child in current.children:
        if child == target:
            return current
        result = find_parent_collection(target, child)
        if result is not None:
            return result
    return None

def save_selected_mesh(filepath):
    """Save selected objects and collections to a .blend file"""
    # Automatically add .blend extension if it's missing.
    if not filepath.lower().endswith('.blend'):
        filepath += '.blend'
    
    # 1. Gather selected objects and collections.
    sel_objs = list(bpy.context.selected_objects)
    sel_colls = get_selected_collections(bpy.context)
    # Filter: keep only collections that contain at least one selected object.
    valid_colls = [coll for coll in sel_colls if any(coll.objects.get(obj.name) is not None for obj in sel_objs)]
    
    if not sel_objs and not valid_colls:
        print("No valid objects or collections selected!")
        return {'CANCELLED'}
    
    # 2. Record original names for valid collections.
    orig_names = {coll: coll.name for coll in valid_colls}
    
    # 3. Create a temporary scene.
    temp_scene = bpy.data.scenes.new("TempExportScene")
    temp_root = temp_scene.collection  # Root collection of the temporary scene.
    
    # 4. In the original file, rename each valid collection by appending "_temp".
    for coll in valid_colls:
        coll.name = coll.name + "_temp"
    
    # 5. In the temporary scene, duplicate each valid collection.
    # First pass: create duplicate for each valid collection and link to temp_root.
    dup_coll_mapping = {}
    for coll in valid_colls:
        desired_name = orig_names[coll]
        dup_coll = bpy.data.collections.new("")
        dup_coll.name = desired_name  # Force its name to the original name.
        dup_coll_mapping[coll] = dup_coll
        temp_root.children.link(dup_coll)
        # Link selected objects from the original collection.
        for obj in coll.objects:
            if obj in sel_objs:
                try:
                    dup_coll.objects.link(obj)
                except RuntimeError:
                    pass
                        
    # 6. Re-establish hierarchy in the temporary scene.
    # Use the working file's root as the starting point.
    original_root = bpy.context.scene.collection
    for coll in valid_colls:
        # Find parent in the working file hierarchy.
        parent = find_parent_collection(coll, original_root)
        if parent and parent in valid_colls:
            # If the parent is valid, reassign duplicate's parent.
            child_dup = dup_coll_mapping[coll]
            parent_dup = dup_coll_mapping[parent]
            # Unlink child from temp_root if necessary.
            try:
                temp_root.children.unlink(child_dup)
            except Exception:
                pass
            parent_dup.children.link(child_dup)
    
    # 7. For any selected object not already in a duplicate, link it directly to temp_root.
    for obj in sel_objs:
        in_dup = any(dup.objects.get(obj.name) is not None for dup in dup_coll_mapping.values())
        if not in_dup:
            try:
                temp_root.objects.link(obj)
            except RuntimeError:
                pass
                    
    # 8. Build the set of datablocks to export.
    datablocks = {temp_scene, temp_root} | set(dup_coll_mapping.values())
    
    bpy.data.libraries.write(filepath, datablocks=datablocks, path_remap='RELATIVE')
    
    # 9. Cleanup: Remove the temporary scene.
    bpy.data.scenes.remove(temp_scene)
    
    # Optionally, remove any duplicate collections that linger (should be removed with the scene).
    for dup in dup_coll_mapping.values():
        try:
            bpy.data.collections.remove(dup)
        except Exception as e:
            print(f"Couldn't remove duplicate collection {dup.name}: {e}")
    
    # 10. Restore original collection names in the working file.
    for coll, orig_name in orig_names.items():
        if coll.name.endswith("_temp"):
            coll.name = orig_name
        else:
            coll.name = orig_name
                
    print(f"Exported selection to {filepath}")
    return {'FINISHED'}

# ============================================================================
# IMPORT SELECTION FUNCTIONALITY
# ============================================================================

def import_selected_blend(filepath, link_collections=False, link_objects=False):
    """
    Import collections and objects from a .blend file.
    
    Args:
        filepath: Path to the .blend file to import
        link_collections: If True, link collections instead of appending
        link_objects: If True, link objects instead of appending
    """
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return {'CANCELLED'}
    
    if not filepath.lower().endswith('.blend'):
        print("File must be a .blend file")
        return {'CANCELLED'}
    
    # Store original selection to restore later
    original_selection = list(bpy.context.selected_objects)
    
    try:
        # Import collections and objects from the blend file
        with bpy.data.libraries.load(filepath, link=link_collections or link_objects) as (data_from, data_to):
            # Import all collections
            data_to.collections = data_from.collections
            # Import all objects
            data_to.objects = data_from.objects
            # Import materials, meshes, etc. that might be needed
            data_to.materials = data_from.materials
            data_to.meshes = data_from.meshes
            data_to.curves = data_from.curves
            data_to.lights = data_from.lights
            data_to.cameras = data_from.cameras
            data_to.armatures = data_from.armatures
        
        # Link imported collections to the current scene
        scene = bpy.context.scene
        imported_objects = []
        
        # Link collections to scene
        for coll in data_to.collections:
            if coll and coll.name not in scene.collection.children:
                try:
                    scene.collection.children.link(coll)
                    # Collect objects from imported collections
                    for obj in coll.objects:
                        imported_objects.append(obj)
                except RuntimeError as e:
                    print(f"Could not link collection {coll.name}: {e}")
        
        # Link standalone objects (not in collections) to scene
        for obj in data_to.objects:
            if obj and obj.name not in scene.objects:
                try:
                    scene.collection.objects.link(obj)
                    imported_objects.append(obj)
                except RuntimeError as e:
                    print(f"Could not link object {obj.name}: {e}")
        
        # Select imported objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in imported_objects:
            if obj:
                try:
                    obj.select_set(True)
                except Exception:
                    pass
        
        # Set active object to first imported object
        if imported_objects:
            bpy.context.view_layer.objects.active = imported_objects[0]
        
        print(f"Successfully imported {len(imported_objects)} objects from {filepath}")
        return {'FINISHED'}
        
    except Exception as e:
        print(f"Error importing from {filepath}: {e}")
        # Restore original selection on error
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            try:
                obj.select_set(True)
            except Exception:
                pass
        return {'CANCELLED'}

# ============================================================================
# BLENDER OPERATORS
# ============================================================================

class EXPORT_OT_save_selection(bpy.types.Operator):
    """Save only selected objects as a .blend file"""
    bl_idname = "export.save_selection"
    bl_label = "Save Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Filepath for the .blend file",
        subtype="FILE_PATH"
    )
    
    def execute(self, context):
        result = save_selected_mesh(self.filepath)
        if result == {'FINISHED'}:
            self.report({'INFO'}, f"Selection saved to {self.filepath}")
        else:
            self.report({'ERROR'}, "Failed to save selection")
        return result
    
    def invoke(self, context, event):
        self.filepath = "untitled_selection.blend"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class IMPORT_OT_selection_blend(bpy.types.Operator):
    """Import objects and collections from a .blend file"""
    bl_idname = "import.selection_blend"
    bl_label = "Import Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Filepath for the .blend file to import",
        subtype="FILE_PATH"
    )
    
    link_collections: bpy.props.BoolProperty(
        name="Link Collections",
        description="Link collections instead of appending them",
        default=False
    )
    
    link_objects: bpy.props.BoolProperty(
        name="Link Objects",
        description="Link objects instead of appending them",
        default=False
    )
    
    def execute(self, context):
        result = import_selected_blend(self.filepath, self.link_collections, self.link_objects)
        if result == {'FINISHED'}:
            self.report({'INFO'}, f"Successfully imported from {self.filepath}")
        else:
            self.report({'ERROR'}, f"Failed to import from {self.filepath}")
        return result
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "link_collections")
        layout.prop(self, "link_objects")

# ============================================================================
# MENU INTEGRATION
# ============================================================================

def export_menu_func(self, context):
    self.layout.operator(EXPORT_OT_save_selection.bl_idname, text="Save Selection (.blend)")

def import_menu_func(self, context):
    self.layout.operator(IMPORT_OT_selection_blend.bl_idname, text="Import Selection (.blend)")

# ============================================================================
# REGISTRATION
# ============================================================================

classes = [
    EXPORT_OT_save_selection,
    IMPORT_OT_selection_blend,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.TOPBAR_MT_file_export.append(export_menu_func)
    bpy.types.TOPBAR_MT_file_import.append(import_menu_func)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    bpy.types.TOPBAR_MT_file_export.remove(export_menu_func)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu_func)

if __name__ == "__main__":
    register()