"""NONSHIPPING invented pixels/cache hashes; never real rendered/native evidence."""
from hashlib import sha256
from types import SimpleNamespace
import struct
import json

from fixtures.body_sprite_contract import request
from ucc.core.body_sprites import BodySpriteWindow, POLICY, worker_bindings
from ucc.core.target_action_format import CLOCK
from ucc.jobs.private_render_evidence import png_measurements


def image_evidence(root, value=None):
    from PIL import Image
    value = value or request(window=BodySpriteWindow(149,150)); names = []
    def frame(index):
        return struct.pack('<9f',0.,0.,0.,1.,0.,0.,0.,1.,index/1000),struct.pack('<3I',0,1,2)
    cache = SimpleNamespace(frame_count=300,source_first_frame=2,fps=30.,vertex_count=3,triangle_count=1,frame=frame)
    world = [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]
    objects = {'UNIT_HUMAN':{'type':'MESH','world':world},'UNIT_RIG':{'type':'ARMATURE','world':world}}
    for i in range(4): objects[f'UNIT_CAMERA{i}']={'type':'CAMERA','world':world,'camera':{'type':'ORTHO','ortho_scale':2.5,'clip_start':.01,'clip_end':100.},'dof':False}
    for i in range(3): objects[f'UNIT_LIGHT{i}']={'type':'LIGHT','world':world,'light':{'type':'AREA','energy':300.,'shape':'DISK','size':2.},'color':[1.,1.,1.]}
    configuration = {'objects':objects,'frame':value.window.target_first_frame,'engine':'CYCLES','device':'CPU','samples':32,
        'denoising':False,'adaptive_sampling':False,'seed':0,'animated_seed':False,'threads':['FIXED',2],
        'resolution':[128,128,100],'pixel_aspect':[1.,1.],'transparent':True,'format':['PNG','RGBA','8',15],
        'dither':0.,'compositor':False,'sequencer':False,'view':['Standard','None',0.,1.,False],
        'world_nodes':[[1.,1.,1.,1.],0.15000000596046448],'world_node_types':['ShaderNodeBackground','ShaderNodeOutputWorld'],'units':['METRIC',1.]}
    options = worker_bindings(value,'a'*64); options['scene_sha256']='b'*64
    report = {'schema_version':1,'policy':POLICY,'bindings':{k:v for k,v in options.items() if k!='scene_sha256'},
        'scene_sha256':'b'*64,'source_state_sha256':'c'*64,'saved_action_state_sha256':'d'*64,
        'shader_sha256':'e'*64,'temporary_matte_sha256':value.temporary_matte.sha256,'source_material_slots':0,
        'configuration':configuration,'original_scene':'UNIT_NOT_REAL_SCENE','pivot':[.5,.9],
        'full_clock':dict(CLOCK),'window':value.window.to_dict(),'frames':[],
        'blender_version':'5.3.0','blender_build_hash':'UNIT_NOT_BUILD_PROOF','visual_quality_approved':False,'material_adopted':False}
    for direction,yaw in enumerate(value.settings.angles()):
        for target in value.window.target_frames:
            name=f'body-{direction:02d}-{target:04d}.png'; names.append(name)
            image=Image.new('RGBA',(128,128),(0,0,0,0)); pixels=image.load()
            for y in range(24,104):
                for x in range(32,96): pixels[x,y]=((x*2+direction*7)%255,(y+target)%255,100,255)
            image.save(root/name); image.close(); payload=(root/name).read_bytes()
            positions,triangles=frame(target-1)
            geometry={'evaluated_sha256':'f'*64,'positions_sha256':sha256(positions).hexdigest(),
                'triangles_sha256':sha256(triangles).hexdigest(),'pose_sha256':'1'*64,'raw_skin_sha256':'2'*64,
                'vertex_count':3,'triangle_count':1}
            report['frames'].append({'file':name,'direction_index':direction,'yaw_deg':yaw,'target_frame':target,
                'source_frame':target+1,'geometry':geometry,'normals_sha256':'3'*64,'sha256':sha256(payload).hexdigest(),
                **png_measurements(payload,include_pixel_hash=True,expected_size=(128,128))})
    def write():
        (root/'body_sprite_stage.json').write_text(json.dumps(report))
        options['stage_sha256']=sha256((root/'body_sprite_stage.json').read_bytes()).hexdigest()
        proof={'schema_version':1,'policy':POLICY,'bindings':dict(options),'verified_reopen':True,
            'saved_scene_rebuilt_or_repaired':False,'source_state_sha256':report['source_state_sha256'],
            'saved_action_state_sha256':report['saved_action_state_sha256'],'shader_sha256':report['shader_sha256'],
            'temporary_matte_sha256':value.temporary_matte.sha256,'reference_frames':value.image_count,
            'saved_frames':value.image_count,'full_source_frames_verified':300,'full_saved_frames_verified':300,
            'exact_selected_pose_match':True,'exact_rerender_pixels':True,'material_adopted':False,'visual_quality_approved':False}
        (root/'body_sprite_verification.json').write_text(json.dumps(proof)); return proof
    proof=write()
    return value,cache,options,report,proof,write
