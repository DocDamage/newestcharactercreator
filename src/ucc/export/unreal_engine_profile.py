"""Declared static Unreal settings, verified against installed 5.9 import/reopen.

Only first-party option declarations live here. No engine code, SDK fixture,
private source data, local paths or observed per-character values are bundled.
"""
from .unreal_contract import ENGINE_VERSION, PROFILE

TRIANGLE_ORDER_OPTIMIZATION = 2

FBX_IMPORT_UI = {'automated_import_should_detect_type': False,
 'create_physics_asset': False,
 'import_animations': False,
 'import_as_skeletal': True,
 'import_materials': False,
 'import_mesh': True,
 'import_rigid_mesh': False,
 'import_textures': False,
 'mesh_type_to_import': 'FBXImportType.FBXIT_SKELETAL_MESH',
 'original_import_type': 'FBXImportType.FBXIT_SKELETAL_MESH',
 'override_full_name': True,
 'skeleton': None}

FBX_IMPORT = {'bake_pivot_in_vertex': False,
 'compute_weighted_normals': False,
 'convert_scene': True,
 'convert_scene_unit': True,
 'coordinate_system_policy': 'CoordinateSystemPolicy.MATCH_UP_FORWARD_AXES',
 'force_front_x_axis': True,
 'import_content_type': 'FBXImportContentType.FBXICT_ALL',
 'import_mesh_lods': False,
 'import_meshes_in_bone_hierarchy': False,
 'import_morph_targets': True,
 'import_rotation': [0, 0, 0],
 'import_translation': [0, 0, 0],
 'import_uniform_scale': 1,
 'import_vertex_attributes': False,
 'keep_sections_separate': False,
 'morph_threshold_position': 0,
 'normal_generation_method': 'FBXNormalGenerationMethod.MIKK_T_SPACE',
 'normal_import_method': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS',
 'preserve_smoothing_groups': False,
 'threshold_position': 0,
 'threshold_tangent_normal': 0,
 'threshold_uv': 0,
 'transform_vertex_to_absolute': True,
 'update_skeleton_reference_pose': False,
 'use_t0_as_ref_pose': False,
 'vertex_color_import_option': 'VertexColorImportOption.IGNORE'}

LOD_BUILD = {'bone_influence_limit': 0,
 'compute_weighted_normals': False,
 'morph_threshold_position': 0,
 'optimize_for_instancing': False,
 'recompute_normals': False,
 'recompute_tangents': True,
 'remove_degenerates': False,
 'threshold_position': 0,
 'threshold_tangent_normal': 0,
 'threshold_uv': 0,
 'use_backwards_compatible_f16_trunc_u_vs': False,
 'use_full_precision_u_vs': True,
 'use_high_precision_skin_weights': True,
 'use_high_precision_tangent_basis': True,
 'use_mikk_t_space': True}

MESH_SETTINGS = {'nanite_settings.enabled': False,
 'negative_bounds_extension': [0, 0, 0],
 'positive_bounds_extension': [0, 0, 0]}

