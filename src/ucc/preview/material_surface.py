"""Closed static owned-material GLB profile; no external/asset shaders execute."""
from dataclasses import replace
import math
from pathlib import Path
from ucc.core.errors import ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_skin_evidence import _DenseSkin
from .glb_mesh import PreviewMesh,load_glb_preview,_instances,_transform


def load_material_surface(path: Path,spec: SkinMaterialSpec) -> PreviewMesh:
    reader=_DenseSkin(path);doc=reader.document
    try:
        meshes=doc['meshes'];materials=doc['materials']
        if (len(meshes)!=1 or len(meshes[0]['primitives'])!=1 or len(materials)!=1
                or doc.get('skins') or doc.get('animations') or doc.get('images') or doc.get('textures')):
            raise ValidationError('Material preview needs one static source mesh/material without textures')
        primitive=meshes[0]['primitives'][0];mat=materials[0];pbr=mat['pbrMetallicRoughness']
        allowed={'name','pbrMetallicRoughness','extensions','doubleSided','alphaMode'}
        extensions={'KHR_materials_ior':{'ior':1.5},'KHR_materials_specular':{'specularFactor':1.,'specularColorFactor':[1.,1.,1.]}}
        if (primitive.get('material')!=0 or primitive.get('targets') or primitive.get('mode',4)!=4
                or set(mat)-allowed or set(pbr)-{'baseColorFactor','roughnessFactor','metallicFactor'}
                or any(k not in extensions or v!=extensions[k] for k,v in mat.get('extensions',{}).items())
                or mat.get('alphaMode','OPAQUE')!='OPAQUE' or mat.get('doubleSided',False) is not False):
            raise ValidationError('Unsupported shader/primitive in owned static material preview')
        color=pbr['baseColorFactor'];rough=pbr['roughnessFactor'];metal=pbr.get('metallicFactor',1.)
        if (type(color) is not list or len(color)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in [*color,rough,metal])
                or max(abs(a-b) for a,b in zip(color,spec.linear_rgba))>1e-6 or abs(rough-spec.roughness)>1e-6 or metal!=0.):
            raise ValidationError('Exported preview PBR differs from the saved owned material')
        instances=_instances(doc,meshes)
        if len(instances)!=1:raise ValidationError('Owned preview must have one mesh instance')
        _,matrix=instances[0]
        # Normal inverse transpose, including nonuniform positive scale. Reject
        # mirrored/singular transforms instead of silently flipping winding.
        a,d,g=matrix[0:3];b,e,h=matrix[4:7];c,f,i=matrix[8:11]
        det=a*(e*i-f*h)-d*(b*i-c*h)+g*(b*f-c*e)
        if not math.isfinite(det) or det<=1e-12:raise ValidationError('Mirrored or singular material preview transform')
        cofactor=((e*i-f*h,f*g-d*i,d*h-e*g),(c*h-b*i,a*i-c*g,b*g-a*h),(b*f-c*e,c*d-a*f,a*e-b*d))
        def normal(n):
            if abs(math.sqrt(sum(v*v for v in n))-1.)>1e-4:raise ValidationError('Saved preview normals must be unit length')
            result=tuple(sum(row[j]*n[j] for j in range(3)) for row in cofactor)
            length=math.sqrt(sum(v*v for v in result))
            if not math.isfinite(length) or length<1e-12:raise ValidationError('Invalid transformed material normal')
            return tuple(v/length for v in result)
        attrs=primitive['attributes'];positions=reader.rows(attrs['POSITION'],'VEC3',(5126,))
        normals=reader.rows(attrs['NORMAL'],'VEC3',(5126,));indices=reader.rows(primitive['indices'],'SCALAR',(5121,5123,5125))
        if len(normals)!=len(positions) or len(indices)%3:raise ValidationError('Incomplete saved preview normals/triangles')
        mesh=load_glb_preview(path,full_surface=True);faces=[]
        for at in range(0,len(indices),3):
            ids=[indices[at+j][0] for j in range(3)]
            points=tuple(_transform(matrix,positions[k]) for k in ids)
            if points!=mesh.triangles[at//3]:raise ValidationError('Material normals do not match complete preview triangle order')
            faces.append(tuple(normal(normals[k]) for k in ids))
        return replace(mesh,normals=tuple(faces),material=spec)
    except (KeyError,IndexError,TypeError,AttributeError,ZeroDivisionError) as error:
        raise ValidationError('Malformed owned material preview') from error
