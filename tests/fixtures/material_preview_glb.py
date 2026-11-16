"""Non-shipping triangle/normal fixture; never Blender/MPFB acceptance evidence."""
import json,struct


def write_material_triangle(path,spec,mutate=lambda doc:None):
    positions=struct.pack('<9f',0.,0.,0.,1.,0.,0.,.5,2.,1.)
    normals=struct.pack('<9f',*([0.,-.4472135955,.894427191]*3))
    indices=struct.pack('<3I',0,1,2);binary=positions+normals+indices
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
        'bufferViews':[{'buffer':0,'byteOffset':offset,'byteLength':length} for offset,length in [(0,36),(36,36),(72,12)]],
        'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'},
            {'bufferView':1,'componentType':5126,'count':3,'type':'VEC3'},
            {'bufferView':2,'componentType':5125,'count':3,'type':'SCALAR'}],
        'materials':[{'pbrMetallicRoughness':{'baseColorFactor':list(spec.linear_rgba),'roughnessFactor':spec.roughness,'metallicFactor':0.}}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1},'indices':2,'material':0}]}],
        'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    mutate(doc);raw=json.dumps(doc,separators=(',',':')).encode();raw+=b' '*(-len(raw)%4)
    payload=struct.pack('<I4s',len(raw),b'JSON')+raw+struct.pack('<I4s',len(binary),b'BIN\0')+binary
    path.write_bytes(struct.pack('<4sII',b'glTF',2,len(payload)+12)+payload)
