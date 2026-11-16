"""Validate dedicated Unreal FBX against freshly collected original source.

Only the installed Blender parser is used; no expected data comes from Unreal.
"""
from hashlib import sha256
from pathlib import Path
import math
import struct
from ucc.export.godot_candidate_contract import canonical_bytes as canonical


PORTABLE_HEADER_VALUES = {b'DocumentUrl':b'character.fbx', b'SrcDocumentUrl':b'character.fbx',
    b'Original|FileName':b'character.fbx', b'Original|ApplicationNativeFile':b''}


def _string_property(element, index, *, encoded=False):
    if (len(element.props_type) != len(element.props) or element.props_type[index] != ord('S')
            or not isinstance(element.props[index], bytes)):
        raise ValueError('Unreal FBX document metadata has an unexpected string type')
    value = element.props[index]
    if encoded:
        if len(value) < 4 or struct.unpack('<I', value[:4])[0] != len(value)-4:
            raise ValueError('Unreal FBX document metadata has invalid encoded string length')
        value = value[4:]
    return value


def _document_properties(root, *, encoded=False):
    def only(parent, kind):
        matches = [node for node in parent.elems if node.id == kind]
        if len(matches) != 1:
            raise ValueError('Unreal FBX document metadata structure is missing or ambiguous')
        return matches[0]
    properties = only(only(only(root, b'FBXHeaderExtension'), b'SceneInfo'), b'Properties70')
    result = {}
    for node in properties.elems:
        if node.id != b'P' or not node.props:
            continue
        key = _string_property(node, 0, encoded=encoded)
        if key not in PORTABLE_HEADER_VALUES:
            continue
        if key in result:
            raise ValueError('Unreal FBX document metadata duplicates a portable field')
        if len(node.props) != 5:
            raise ValueError('Unreal FBX document metadata has an unexpected property layout')
        _string_property(node, -1, encoded=encoded)
        result[key] = node
    if set(result) != set(PORTABLE_HEADER_VALUES):
        raise ValueError('Unreal FBX document metadata is missing a portable field')
    return result


def normalize_export_header(root, native_filepath: str) -> None:
    """Change exactly four pre-encoding document strings, never scene objects.

    The installed exporter's original header writer has already run. Its three
    fixed placeholders and actual staged .blend identity must match this profile.
    """
    fields = _document_properties(root, encoded=True)
    expected = {key:b'/foobar.fbx' for key in PORTABLE_HEADER_VALUES}
    expected[b'Original|ApplicationNativeFile'] = native_filepath.encode('utf-8')
    if any(_string_property(node, -1, encoded=True) != expected[key] for key,node in fields.items()):
        raise ValueError('Unreal FBX exporter document metadata differs from the admitted source profile')
    for key,node in fields.items():
        node.props.pop(); node.props_type.pop()
        node.add_string(PORTABLE_HEADER_VALUES[key])


def validate_portable_header(root) -> None:
    fields = _document_properties(root)
    if any(_string_property(node, -1) != PORTABLE_HEADER_VALUES[key] for key,node in fields.items()):
        raise ValueError('Unreal FBX document metadata is not portable or exposes a source path')


def unreal_name(name):
    value = name.rsplit(':',1)[-1]
    for char in '.,/`%':value = value.replace(char,'_')
    return value


def unreal_bone_name(name):
    return unreal_name(name).strip().replace(' ','-')


def fbx_metadata(path,reference):
    from io_scene_fbx.parse_fbx import parse
    tree,version = parse(str(path))
    validate_portable_header(tree)
    globals_node, = [node for node in tree.elems if node.id==b'GlobalSettings']
    props, = [node for node in globals_node.elems if node.id==b'Properties70']
    wanted = {'UpAxis','UpAxisSign','FrontAxis','FrontAxisSign','CoordAxis','CoordAxisSign',
        'UnitScaleFactor','OriginalUnitScaleFactor'}
    settings = {node.props[0].decode('utf-8'):node.props[-1] for node in props.elems
        if node.id==b'P' and node.props[0].decode('utf-8') in wanted}
    expected = dict(zip(('UpAxis','UpAxisSign','FrontAxis','FrontAxisSign','CoordAxis','CoordAxisSign'),(2,1,0,1,1,1)))
    expected.update(UnitScaleFactor=100.,OriginalUnitScaleFactor=100.)
    if settings!=expected:raise ValueError('Actual FBX axis/unit metadata differs from the dedicated Unreal profile')
    objects, = [node for node in tree.elems if node.id==b'Objects']
    models = [node for node in objects.elems if node.id==b'Model']
    shape_count = sum(node.id==b'Geometry' and node.props[2]==b'Shape' for node in objects.elems)
    mesh_count = sum(node.id==b'Geometry' and node.props[2]==b'Mesh' for node in objects.elems)
    limbs = [node for node in models if node.props[2]==b'LimbNode']
    nulls = [node for node in models if node.props[2]==b'Null']
    if (len(limbs)!=163 or len(nulls)!=1 or nulls[0].props[1].split(b'\x00\x01')[0]!=b'Armature'
            or len(models)!=165 or shape_count!=12 or mesh_count!=1
            or any(node.id.startswith(b'Animation') for node in objects.elems)):
        raise ValueError('FBX model/bone/shape coverage or no-animation source profile differs')
    mesh, = [node for node in objects.elems if node.id==b'Geometry' and node.props[2]==b'Mesh']
    vertices, = [node for node in mesh.elems if node.id==b'Vertices']
    indices, = [node for node in mesh.elems if node.id==b'PolygonVertexIndex']
    if len(vertices.props[0])!=13380*3 or len(indices.props[0])!=26756*3:
        raise ValueError('Actual FBX loses visible source vertices or measured triangle corners')
    expected_local=[value for point in reference['source_bind_local_vertices'] for value in point]
    if list(vertices.props[0])!=expected_local:
        raise ValueError('FBX changed any original admitted local bind coordinate')
    if sum(value<0 for value in indices.props[0])!=26756:
        raise ValueError('Actual FBX does not retain every measured triangle')
    triangles=[];current=[]
    for value in indices.props[0]:
        current.append(-value-1 if value<0 else value)
        if value<0:
            if len(current)!=3:raise ValueError('FBX retained a non-triangular source polygon')
            triangles.append(current);current=[]
    if current or triangles!=reference['triangles']:
        raise ValueError('FBX changes the exact original triangulation, diagonal or corner order')
    uv_layer, = [node for node in mesh.elems if node.id==b'LayerElementUV']
    direct, = [node.props[0] for node in uv_layer.elems if node.id==b'UV']
    uv_indices, = [node.props[0] for node in uv_layer.elems if node.id==b'UVIndex']
    if len(uv_indices)!=26756*3:raise ValueError('FBX UV corner coverage differs')
    for index,uv in enumerate(uv for corner in reference['corners'] for uv in corner['uv']):
        actual=direct[uv_indices[index]*2:uv_indices[index]*2+2]
        if struct.pack('<2f',*actual)!=struct.pack('<2f',*uv):
            raise ValueError('FBX source UV corners differ before the declared Unreal V conversion')
    model_names={node.props[0]:node.props[1].split(b'\x00\x01')[0].decode('utf-8') for node in models}
    limb_ids={node.props[0] for node in limbs};null_id=nulls[0].props[0]
    connections, = [node for node in tree.elems if node.id==b'Connections']
    materials=[node for node in objects.elems if node.id==b'Material']
    mesh_model, = [node for node in models if node.props[2]==b'Mesh']
    if len(materials)!=1:raise ValueError('FBX material slot count differs from the single reviewed skin')
    material_name=materials[0].props[1].split(b'\x00\x01')[0].decode('utf-8')
    if material_name!=reference['source_material_name']:
        raise ValueError('FBX material identity differs from the source owned shader')
    material_links=[node for node in connections.elems if node.id==b'C' and node.props[0]==b'OO'
        and node.props[1]==materials[0].props[0] and node.props[2]==mesh_model.props[0]]
    if len(material_links)!=1:raise ValueError('FBX mesh material binding differs')
    children={key:[] for key in model_names};parents={}
    for connection in connections.elems:
        if connection.id!=b'C' or connection.props[0]!=b'OO':continue
        child,parent=connection.props[1:3]
        if child in limb_ids and parent in model_names:
            if child in parents or parent not in limb_ids|{null_id}:raise ValueError('FBX skeleton parent graph is ambiguous')
            parents[child]=parent;children[parent].append(child)
    by_name={bone['name']:bone['parent'] for bone in reference['bones']}
    if {model_names[key] for key in limb_ids}!=set(by_name) or len(parents)!=163:
        raise ValueError('FBX limb identities differ from the original rig')
    for child,parent in parents.items():
        expected_parent=None if parent==null_id else model_names[parent]
        if by_name[model_names[child]]!=expected_parent:raise ValueError('FBX changed an original bone parent identity')
    if len(children[null_id])!=1:raise ValueError('Unreal profile requires exactly one original skeleton root')
    order=[]
    def visit(node):
        if node in order:raise ValueError('FBX skeleton hierarchy contains a cycle')
        order.append(node)
        for child in children[node]:visit(child)
    visit(children[null_id][0])
    if len(order)!=163:raise ValueError('FBX skeleton DFS does not cover every original bone')
    expected_order=[unreal_bone_name(model_names[node]) for node in order]
    blends=[node for node in objects.elems if node.id==b'Deformer' and node.props[2]==b'BlendShape']
    channels=[node for node in objects.elems if node.id==b'Deformer' and node.props[2]==b'BlendShapeChannel']
    if len(blends)!=1 or len(channels)!=12:raise ValueError('FBX canonical morph channel coverage differs')
    blend_name=unreal_name(blends[0].props[1].split(b'\x00\x01')[0].decode('utf-8'))
    target_morphs=[]
    for channel in channels:
        name=unreal_name(channel.props[1].split(b'\x00\x01')[0].decode('utf-8'))
        if name.startswith(blend_name):name=name[len(blend_name)+1:]
        target_morphs.append(name)
    if len(set(target_morphs))!=12 or set(target_morphs)!=set(reference['morphs']):
        raise ValueError('Declared Unreal morph channel naming differs from the canonical original controls')
    clusters={node.props[0]:node for node in objects.elems if node.id==b'Deformer' and node.props[2]==b'Cluster'}
    links={}
    for node in connections.elems:
        if node.id==b'C' and node.props[0]==b'OO' and node.props[1] in limb_ids and node.props[2] in clusters:
            if node.props[2] in links:raise ValueError('FBX skin cluster has multiple source bone bindings')
            links[node.props[2]]=model_names[node.props[1]]
    actual_weights=[[] for _ in range(13380)]
    for key,node in clusters.items():
        if key not in links:raise ValueError('FBX skin cluster has no original source bone identity')
        index_arrays=[child.props[0] for child in node.elems if child.id==b'Indexes']
        weight_arrays=[child.props[0] for child in node.elems if child.id==b'Weights']
        if len(index_arrays)!=len(weight_arrays) or len(index_arrays)>1:
            raise ValueError('FBX cluster index/weight arrays are incomplete or ambiguous')
        ids=index_arrays[0] if index_arrays else ()
        values=weight_arrays[0] if weight_arrays else ()
        if len(ids)!=len(values):raise ValueError('FBX skin cluster weight coverage differs')
        for index,weight in zip(ids,values):
            if not 0<=index<13380 or not math.isfinite(weight) or weight<=0:
                raise ValueError('FBX skin has an invalid original influence')
            actual_weights[index].append([links[key],weight])
    if canonical([sorted(row) for row in actual_weights])!=canonical(reference['weights']):
        raise ValueError('FBX loses or alters an original positive skin influence')
    poses=[node for node in objects.elems if node.id==b'Pose' and node.props[2]==b'BindPose']
    if len(poses)!=2:raise ValueError('FBX needs the declared mesh-shape and full skeleton bind poses')
    full_poses=[pose for pose in poses if [node.props[0] for node in pose.elems if node.id==b'NbPoseNodes']==[165]]
    if len(full_poses)!=1:raise ValueError('FBX needs exactly one complete original skeleton bind pose')
    pose=full_poses[0]
    declared,=[node.props[0] for node in pose.elems if node.id==b'NbPoseNodes']
    pose_nodes=[node for node in pose.elems if node.id==b'PoseNode']
    pose_matrices={}
    for node in pose_nodes:
        key,=[child.props[0] for child in node.elems if child.id==b'Node']
        matrix,=[child.props[0] for child in node.elems if child.id==b'Matrix']
        if key in pose_matrices or len(matrix)!=16 or any(not math.isfinite(v) for v in matrix):
            raise ValueError('FBX bind pose has duplicate or invalid global matrices')
        pose_matrices[key]=list(matrix)
    if declared!=165 or len(pose_nodes)!=165 or set(pose_matrices)!=set(model_names):
        raise ValueError('FBX bind pose does not cover every bone and required mesh/Armature ancestor')
    mesh_pose,=[item for item in poses if item is not pose]
    mesh_declared=[node.props[0] for node in mesh_pose.elems if node.id==b'NbPoseNodes']
    mesh_nodes=[node for node in mesh_pose.elems if node.id==b'PoseNode']
    if mesh_declared!=[1] or len(mesh_nodes)!=1:raise ValueError('FBX shape bind pose is not mesh-only')
    mesh_key,=[child.props[0] for child in mesh_nodes[0].elems if child.id==b'Node']
    mesh_matrix,=[child.props[0] for child in mesh_nodes[0].elems if child.id==b'Matrix']
    if mesh_key!=mesh_model.props[0] or list(mesh_matrix)!=pose_matrices[mesh_key]:
        raise ValueError('FBX shape bind pose changes its original mesh global matrix')
    for key,node in clusters.items():
        transform_link,=[child.props[0] for child in node.elems if child.id==b'TransformLink']
        limb_id,=[limb for limb in limb_ids if model_names[limb]==links[key]]
        if list(transform_link)!=pose_matrices[limb_id]:
            raise ValueError('FBX cluster original bone global differs from its complete bind pose')
    metadata={'fbx_version':version,'global_settings':settings,'mesh_models':1,'armature_null_models':1,
        'bone_models':163,'morph_shapes':12,'visible_vertices':13380,'triangles':26756,
        'bind_pose_nodes':165,'bind_pose_covers_all_models_and_cluster_links':True,
        'sdk_bind_pose_validity_observed':False,
        'animation_objects':0,'source_to_unreal_position_cm':'100*(-y,-x,z)',
        'source_to_unreal_uv':'float32(u),float32(1-float32(v))','positive_matrix_triangle_order':'UNCHANGED',
        'exact_source_triangles_and_uv_corners_preserved':True,
        'all_original_positive_fbx_influences_preserved':True,
        'source_material_name':material_name,'expected_unreal_material_slot_name':unreal_name(material_name),
        'bone_name_policy':'UE_MakeName_then_FixupBoneName_TrimAndSpaceDash',
        'expected_unreal_morph_names':sorted(target_morphs),
        'expected_unreal_bone_order_sha256':sha256(canonical(expected_order)).hexdigest()}
    return metadata,expected_order
