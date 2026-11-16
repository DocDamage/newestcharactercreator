"""Nonshipping metadata/vector logic only; no character or engine evidence."""
import struct
from ucc.export.unity_runtime_source import POLICY,CASES,VERTICES,VECTOR_BYTES,BINARY_BYTES
from fixtures.unity_topology_logic import topology


def source_manifest():
    source=topology();names=['neutral',*('bone-'+n for n in source.bone_names),*('shape-'+n for n in sorted(source.shape_names)),'saved-expression','neutral-end']
    cases=[]
    for i,name in enumerate(names):
        cases.append({'name':name,'bone':source.bone_names[i-1] if 1<=i<=163 else None,
            'delta_blender_world':[float(r==c) for r in range(4) for c in range(4)],
            'shapes':[{'name':n,'value':.5 if name=='shape-'+n else 0.} for n in source.shape_names],
            'positions_offset':i*VECTOR_BYTES*2,'normals_offset':(i*2+1)*VECTOR_BYTES,'positions_sha256':'e'*64,'normals_sha256':'f'*64})
    return {'schema_version':1,'policy':POLICY,'request_sha256':'a'*64,'master_sha256':'b'*64,'recipe_sha256':'c'*64,
        'bind_reference_sha256':'d'*64,'blender_version':'5.3.0','blender_build':'02f0899d78e3',
        'expression_parameters':{n:0. for n in ('eye_left_closure','eye_right_closure','mouth_corners','mouth_open')},
        'coordinate_space':'BLENDER_WORLD_METRES_Z_UP','vector_format':'FLOAT32_LE_XYZ','source_vertices':VERTICES,'case_count':CASES,
        'cases':cases,'binary_sha256':'a'*64,'binary_bytes':BINARY_BYTES,'nonmaterial_state_sha256':'b'*64,'shader_sha256':'c'*64,
        'original_state_preserved':True,'animation_clips_created':False,'runtime_verified':False,'visual_quality_approved':False}


def vector_buffers():
    # Repeated single point, not body geometry; only exercises binary guard arithmetic.
    source=struct.pack('<fff',.25,.125,.5)*VERTICES
    normals=struct.pack('<fff',0.,0.,1.)*VERTICES
    native=struct.pack('<fffffffff',-.25,.5,-.125,-.25,.5,-.125,0.,1.,0.)*14517
    matrix={'e'+str(r)+str(c):float(r==c) for r in range(4) for c in range(4)}
    return native,source,normals,(0,)*14517,matrix
