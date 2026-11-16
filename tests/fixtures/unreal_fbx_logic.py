"""Generated degenerate FBX tree for parser faults; NEVER character/engine evidence."""
from types import SimpleNamespace
from array import array


def node(kind, props=(), elems=()):
    return SimpleNamespace(id=kind, props=list(props), elems=list(elems),
        props_type=bytearray(ord('S') if isinstance(v,bytes) else ord('I') for v in props))


def fixture():
    # Large fixed-profile counts intentionally contain repeated zero/degenerate
    # values. Only closure checking is tested, never geometry or native quality.
    matrix = [1.,0.,0.,0., 0.,1.,0.,0., 0.,0.,1.,0., 0.,0.,0.,1.]
    names = ['UNIT_Bone'+str(i) for i in range(163)]
    models = [node(b'Model', [1,b'UNIT_Mesh',b'Mesh']), node(b'Model',[2,b'Armature',b'Null'])]
    models += [node(b'Model',[100+i,name.encode(),b'LimbNode']) for i,name in enumerate(names)]
    vertices = node(b'Vertices',[array('d',[0.])*(13380*3)])
    indices = node(b'PolygonVertexIndex',[array('i',[0,1,-3])*26756])
    uv = node(b'UV',[array('d',[0.,0.,1.,0.,0.,1.])])
    uv_indices = node(b'UVIndex',[array('i',[0,1,2])*26756])
    mesh = node(b'Geometry',[3,b'UNIT_Mesh',b'Mesh'],[vertices,indices,node(b'LayerElementUV',[],[uv,uv_indices])])
    material = node(b'Material',[4,b'UNIT_MATERIAL',b''])
    shapes = [node(b'Geometry',[1000+i,b'UNIT_SHAPE',b'Shape']) for i in range(12)]
    blend = node(b'Deformer',[2000,b'UNIT_BLEND',b'BlendShape'])
    channels = [node(b'Deformer',[2100+i,('UNIT_Morph'+str(i)).encode(),b'BlendShapeChannel']) for i in range(12)]
    clusters = [node(b'Deformer',[3000+i,b'UNIT_CLUSTER',b'Cluster'],[node(b'TransformLink',[array('d',matrix)])]) for i in range(163)]
    clusters[0].elems += [node(b'Indexes',[array('i',range(13380))]),node(b'Weights',[array('d',[1.])*13380])]
    def pose(ids, uid):
        return node(b'Pose',[uid,b'UNIT_POSE',b'BindPose'],[node(b'NbPoseNodes',[len(ids)])]+
            [node(b'PoseNode',[],[node(b'Node',[key]),node(b'Matrix',[array('d',matrix)])]) for key in ids])
    partial = pose([1],4000); full = pose([m.props[0] for m in models],4001)
    objects = node(b'Objects',[],models+[mesh,material]+shapes+[blend]+channels+clusters+[partial,full])
    links = [node(b'C',[b'OO',4,1])]
    for i in range(163):
        links.append(node(b'C',[b'OO',100+i,2 if i==0 else 99+i]))
        links.append(node(b'C',[b'OO',100+i,3000+i]))
    connections = node(b'Connections',[],links)
    settings = {'UpAxis':2,'UpAxisSign':1,'FrontAxis':0,'FrontAxisSign':1,'CoordAxis':1,'CoordAxisSign':1,
                'UnitScaleFactor':100.,'OriginalUnitScaleFactor':100.}
    globals_node = node(b'GlobalSettings',[],[node(b'Properties70',[],[node(b'P',[k.encode(),v]) for k,v in settings.items()])])
    from blender_bridge.unreal_fbx_metadata import PORTABLE_HEADER_VALUES
    header = node(b'FBXHeaderExtension',[],[node(b'SceneInfo',[],[node(b'Properties70',[],
        [node(b'P',[key,b'KString',b'',b'',value]) for key,value in PORTABLE_HEADER_VALUES.items()])])])
    tree = node(b'',[],[header,globals_node,objects,connections])
    reference = {'source_bind_local_vertices':[[0.,0.,0.]]*13380,'triangles':[[0,1,2]]*26756,
        'corners':[{'uv':[[0.,0.],[1.,0.],[0.,1.]]}]*26756,'source_material_name':'UNIT_MATERIAL',
        'bones':[{'name':name,'parent':None if i==0 else names[i-1]} for i,name in enumerate(names)],
        'morphs':{'UNIT_Morph'+str(i):[] for i in range(12)},'weights':[[[names[0],1.]]]*13380}
    return SimpleNamespace(tree=tree, reference=reference, objects=objects, connections=connections,
        full=full, partial=partial, clusters=clusters, indices=indices, uv=uv,
        vertices=vertices, material=material, channels=channels)


class EncodedHeaderNode:
    """Tiny authored serialization marker, not an actual exporter or FBX file."""
    def __init__(self, kind, values=(), elems=()):
        self.id = kind; self.props = []; self.props_type = bytearray(); self.elems = list(elems)
        for value in values:self.add_string(value)

    def add_string(self, value):
        import struct
        self.props.append(struct.pack('<I',len(value))+value); self.props_type.append(ord('S'))


def encoded_header(native_file, fault=None):
    from blender_bridge.unreal_fbx_metadata import PORTABLE_HEADER_VALUES
    fields=[]
    for key in PORTABLE_HEADER_VALUES:
        value=native_file.encode() if key==b'Original|ApplicationNativeFile' else b'/foobar.fbx'
        fields.append(EncodedHeaderNode(b'P',[key,b'KString',b'',b'',value]))
    if fault=='wrong_old_value':
        fields[0].props.pop(); fields[0].props_type.pop(); fields[0].add_string(b'UNEXPECTED_OLD_VALUE')
    elif fault=='wrong_native':
        fields[-1].props.pop(); fields[-1].props_type.pop(); fields[-1].add_string(b'C:/UNIT_DIFFERENT_SOURCE/candidate.blend')
    elif fault=='duplicate':fields.append(EncodedHeaderNode(b'P',[b'DocumentUrl',b'KString',b'',b'',b'/foobar.fbx']))
    elif fault=='wrong_type':fields[0].props_type[-1]=ord('R')
    elif fault=='missing':fields.pop()
    root=EncodedHeaderNode(b'',elems=[EncodedHeaderNode(b'FBXHeaderExtension',elems=[
        EncodedHeaderNode(b'SceneInfo',elems=[EncodedHeaderNode(b'Properties70',elems=fields)])])])
    return root,fields


def decoded_header(encoded):
    import struct
    values=[value[4:] for value in encoded.props]
    result=node(encoded.id,values,[decoded_header(child) for child in encoded.elems])
    result.props_type=encoded.props_type.copy()
    return result
