"""Read actual saved hand bounds for a complete static character preview."""
import math

from blender_bridge.face_geometry import intake,evaluated
from blender_bridge.hand_geometry import skin_region
from blender_bridge.hand_policy import POLICY,TARGETS,METADATA_SHA,is_sha,digest


def inspect_bounds(bpy,root,options):
    fields={'master_sha256','metadata_sha256','shorter_target_sha256','longer_target_sha256'}
    if type(options) is not dict or set(options)!=fields or not all(is_sha(v) for v in options.values()):
        raise ValueError('Hand bounds require complete pinned source identities')
    names={'candidate.blend':'master_sha256','basemesh_vertex_groups.json':'metadata_sha256',
           **{filename:variant+'_target_sha256' for variant,filename,_ in TARGETS}}
    def unchanged():
        if options['metadata_sha256']!=METADATA_SHA or any(options[v+'_target_sha256']!=s for v,_,s in TARGETS):
            raise ValueError('Hand bounds require pinned topology/target data')
        for filename,role in names.items():
            path=root/filename
            if path.is_symlink() or not path.is_file() or digest(path)!=options[role]:
                raise ValueError('Hand bounds input changed: '+filename)
    unchanged();bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'),load_ui=False)
    human,rig,_,_=intake(bpy);region=skin_region(human,rig,root);points=evaluated(bpy,human,full=True)
    hand=[points[i] for i in region['ids']]
    low=[min(p[i] for p in hand) for i in range(3)];high=[max(p[i] for p in hand) for i in range(3)]
    if (not all(math.isfinite(v) for row in (low,high) for v in row)
            or any(a>=b for a,b in zip(low,high)) or not .01<max(b-a for a,b in zip(low,high))<.5):
        raise ValueError('Saved hand has unsupported units or degenerate bounds')
    unchanged()
    return {'schema_version':1,'policy':POLICY,'master_sha256':options['master_sha256'],
            'slot':'hand.L','bounds':[low,high],'hand_vertices':1747,'visual_quality_approved':False}
