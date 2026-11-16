"""Bounded standard-PBR numeric evidence, not rendered appearance approval."""
import math
from pathlib import Path
from ucc.core.errors import ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from .godot_skin_evidence import _DenseSkin


def verify_material_glb(path: Path,spec: SkinMaterialSpec) -> dict:
    doc=_DenseSkin(path).document
    try:
        materials=doc.get('materials',[]);meshes=doc['meshes'];skins=doc['skins']
        if (len(materials)!=1 or len(meshes)!=1 or len(meshes[0]['primitives'])!=1
                or meshes[0]['primitives'][0].get('material')!=0 or len(skins)!=1 or len(skins[0]['joints'])!=163
                or len(meshes[0]['primitives'][0].get('targets',[]))!=12 or doc.get('animations',[])
                or doc.get('images',[]) or doc.get('textures',[])):
            raise ValidationError('Material GLB must retain the prepared rig/morphs, one source material, no clips or textures')
        material=materials[0];pbr=material.get('pbrMetallicRoughness',{})
        color=pbr.get('baseColorFactor',[1.,1.,1.,1.]);roughness=pbr.get('roughnessFactor',1.);metallic=pbr.get('metallicFactor',1.)
        if (type(color) is not list or len(color)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in color)
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in (roughness,metallic))
                or max(abs(a-b) for a,b in zip(color,spec.linear_rgba))>1e-6 or abs(roughness-spec.roughness)>1e-6
                or metallic!=0. or material.get('alphaMode','OPAQUE')!='OPAQUE'
                or material.get('doubleSided',False) is not False or material.get('emissiveFactor',[0.,0.,0.])!=[0.,0.,0.]):
            raise ValidationError('GLB material differs from explicit opaque color/roughness parameters')
        if any('texture' in name.lower() for obj in (material,pbr) for name in obj):
            raise ValidationError('Color-only material cannot introduce texture references')
        extensions=material.get('extensions',{})
        allowed={'KHR_materials_ior':{'ior':1.5},'KHR_materials_specular':{'specularFactor':1.,'specularColorFactor':[1.,1.,1.]}}
        if type(extensions) is not dict or any(name not in allowed or value!=allowed[name] for name,value in extensions.items()):
            raise ValidationError('Unsupported material extension in color-only export')
        return {'material_count':1,'base_color_linear_rgba':color,'roughness':roughness,'metallic':metallic,
            'alpha_mode':'OPAQUE','texture_count':0,'bones':163,'canonical_morphs':12,'animation_count':0,
            'maximum_color_component_error':max(abs(a-b) for a,b in zip(color,spec.linear_rgba)),
            'maximum_roughness_error':abs(roughness-spec.roughness),'engine_import_verified':False,'rendered_appearance_verified':False}
    except (KeyError,IndexError,TypeError,AttributeError) as error:
        raise ValidationError('Malformed material GLB structure') from error
