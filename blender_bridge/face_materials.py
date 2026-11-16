"""Read-only material/node/texture signatures for facial-copy preservation."""
from hashlib import sha256
import math


def properties(owner) -> dict:
    result = {}
    for prop in owner.bl_rna.properties:
        name = prop.identifier
        if name == 'rna_type' or prop.is_readonly:
            continue
        if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
            value = getattr(owner, name)
            if getattr(prop, 'is_array', False):
                value = list(value)
            if isinstance(value, set):
                value = sorted(value)
            values = value if isinstance(value, list) else [value]
            if any(isinstance(v, float) and not math.isfinite(v) for v in values):
                raise ValueError('Nonfinite facial material data')
            result[name] = value
        elif prop.type == 'POINTER':
            value = getattr(owner, name)
            if value is not None and hasattr(value, 'name_full'):
                result[name] = value.name_full
    return result


def signature(bpy) -> dict:
    result = {}
    for material in bpy.data.materials:
        tree = material.node_tree
        nodes = []
        if tree:
            for node in tree.nodes:
                if getattr(node, 'node_tree', None) is not None:
                    # A nested arbitrary group needs a separate preservation
                    # contract rather than silently omitting its contents.
                    raise ValueError('Facial operation does not support nested material node groups')
                nodes.append({'type': node.bl_idname, 'properties': properties(node),
                              'inputs': [properties(socket) for socket in node.inputs],
                              'outputs': [properties(socket) for socket in node.outputs]})
        result[material.name] = {'properties': properties(material), 'nodes': nodes,
                                'links': [(link.from_node.name, link.from_socket.identifier,
                                           link.to_node.name, link.to_socket.identifier)
                                          for link in tree.links] if tree else []}
    images = {image.name: {'filepath': image.filepath, 'source': image.source,
                          'colorspace': image.colorspace_settings.name,
                          'packed_sha256': sha256(image.packed_file.data).hexdigest() if image.packed_file else None}
              for image in bpy.data.images}
    return {'materials': result, 'images': images}
