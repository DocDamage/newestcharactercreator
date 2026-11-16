"""Non-shipping repeated triangle fixture. NOT Blender/MPFB/character evidence."""
from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import json,math,struct,zlib
from ucc.core.expression_material import BASE_FIELDS,POLICY
from ucc.core.expressions import TARGETS
from ucc.core.skin_material import SkinMaterialSpec


class SyntheticExpressionMaterialFixture:
    def __init__(self,root: Path):
        self.root=root;self.spec=SkinMaterialSpec((.3,.2,.1),.6)
        self.ib=struct.pack('<3I',2,0,1)*26756
        self.vertices=[];self.raw_normals=[]
        for frame in range(25):
            weight=min(frame,24-frame)/12.;vb=bytearray(13380*12)
            struct.pack_into('<9f',vb,0,weight*.01,0.,0.,1.,0.,0.,0.,2.,1.)
            self.vertices.append(bytes(vb));self.raw_normals.append(struct.pack('<3f',math.sin(weight*.1),0.,math.cos(weight*.1))*80268)
        self.geometry=SimpleNamespace(frame_count=25,vertex_count=13380,triangle_count=26756,
            hips=((0.,0.,0.),)*25,world_matrix=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.),radius=1.,fps=24.,source_first_frame=1,
            frame=lambda i:(self.vertices[i],self.ib))
        self.base={k:'e'*64 for k in BASE_FIELDS};self.base.update({t.role+'_'+t.family+'_sha256':t.sha256 for t in TARGETS})
        self.report={'frames':[{'local_vertices_sha256':sha256(v).hexdigest(),'triangles_sha256':sha256(self.ib).hexdigest()} for v in self.vertices]}
        self.flush()

    def flush(self,mutate=lambda manifest:None):
        packed=bytearray(b'UCCNRM1\0');frames=[]
        for index,raw in enumerate(self.raw_normals):
            chunk=zlib.compress(raw,1);frames.append({'frame':index+1,'offset':len(packed),'compressed_bytes':len(chunk),
                'normal_sha256':sha256(raw).hexdigest(),**self.report['frames'][index]});packed.extend(chunk)
        self.binary=self.root/'expression_normals.bin';self.binary.write_bytes(packed)
        self.manifest={'schema_version':1,'policy':POLICY,'bindings':self.base,'material_spec':self.spec.to_dict(),
            'coordinate_space':'BLENDER_LOCAL_Z_UP','frame_count':25,'normals_per_frame':80268,'frames':frames,
            'geometry':{'name':self.binary.name,'sha256':sha256(packed).hexdigest(),'bytes':len(packed)},
            'visual_quality_approved':False,'engine_import_verified':False}
        mutate(self.manifest);self.manifest_path=self.root/'expression_normals.json';self.manifest_path.write_text(json.dumps(self.manifest))
        self.options={**self.base,'owned_material_spec':self.spec.to_dict(),'normals_sha256':sha256(packed).hexdigest(),
            'normals_manifest_sha256':sha256(self.manifest_path.read_bytes()).hexdigest()}
        self.proof={'schema_version':1,'policy':POLICY,'bindings':self.options,'verified_reopen':True,
            'reference_frames':25,'saved_frames':25,'normal_frames':25,'exact_neutral_endpoints':True,
            'visual_quality_approved':False,'engine_import_verified':False}
