"""Nonshipping native-recipe/export-call doubles; never Blender/Godot evidence."""
from pathlib import Path
from types import SimpleNamespace


def export_double(root: Path):
    calls=[]
    class Object:
        def select_set(self,value):pass
    human=Object();rig=Object()
    def export(**kwargs):
        calls.append(kwargs)
        Path(kwargs['filepath']).write_bytes(b'UNIT_EXPORT_CALL_ONLY_NOT_A_GLB')
        return {'FINISHED'}
    bpy=SimpleNamespace(context=SimpleNamespace(scene=SimpleNamespace(objects=[human,rig]),
        view_layer=SimpleNamespace(objects=SimpleNamespace(active=None))),
        ops=SimpleNamespace(export_scene=SimpleNamespace(gltf=export)))
    return bpy,human,rig,calls


def stage_report(recipe_sha: str) -> dict:
    return {'schema_version':1,'policy':'MPFB_NATIVE_RUNTIME_SOURCE_V1',
        'status':'REAL_NATIVE_RUNTIME_SOURCE_STAGED_NOT_ENGINE_VERIFIED',
        'recipe_sha256':recipe_sha,'master_state_sha256':'e'*64,'native_reopen':{},
        'source_names':{'human':'UNIT_ONLY','rig':'UNIT_ONLY_RIG','converted':'UNIT_ONLY_COPY'},
        'frames':[{'frame':i,'raw_error_m':0.,'reconstruction_error_m':0.} for i in range(1,301)],
        'fps':30,'frame_count':300,'morphs':{'canonical_morphs_verified':12,'maximum_morph_position_error_m':0.},
        'blender_version':'UNIT_DOUBLE','numpy_version':'UNIT_DOUBLE','files':{},
        'export_optimize_animation_size':False,'raw_copy_weight_policy':'EXACT_ORIGINAL_SOURCE_WEIGHTS_V1',
        'max_serialized_weight_error':0.,'engine_import_verified':False,'visual_quality_approved':False,
        'distribution_license_review_complete':False}
