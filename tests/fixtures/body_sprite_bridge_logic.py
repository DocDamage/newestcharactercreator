"""NONSHIPPING numeric/control doubles only; never images, geometry or native proof."""
from types import SimpleNamespace as NS


def geometry_record():
    return {'evaluated_sha256':'a'*64,'positions_sha256':'b'*64,'triangles_sha256':'c'*64,
            'pose_sha256':'d'*64,'raw_skin_sha256':'e'*64,'vertex_count':13380,'triangle_count':26756}


def scene():
    value=NS(frame_start=1,frame_end=300,render=NS(fps=30,fps_base=1.),use_preview_range=False,current=1)
    value.frame_set=lambda frame:setattr(value,'current',frame)
    return value


def action_pair():
    points=[NS(co=[float(i),0.],handle_left=[float(i)-.333,0.],handle_right=[float(i)+.333,0.],
        handle_left_type='AUTO_CLAMPED',handle_right_type='AUTO_CLAMPED',interpolation='LINEAR',
        easing='AUTO',type='KEYFRAME',amplitude=0.,back=0.,period=0.) for i in range(1,301)]
    curve=NS(modifiers=[],mute=False,keyframe_points=points,data_path='NONSHIPPING channel',array_index=0,extrapolation='CONSTANT')
    action=NS(name='UNIT_ONLY_NOT_BLENDER_ACTION',frame_range=(1.,300.),slots=[NS(identifier='UNIT',target_id_type='OBJECT')],
              layers=[NS(strips=[NS(channelbags=[NS(fcurves=[curve])])])])
    rig=NS(animation_data=NS(action=action,drivers=[],nla_tracks=[]))
    api=NS(data=NS(actions={action.name:action}))
    return api,rig,curve
