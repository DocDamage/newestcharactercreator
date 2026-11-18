"""NONSHIPPING invented coordinates/bytes for pure logic; never native/asset proof."""
from dataclasses import replace
from hashlib import sha256
import math
from uuid import UUID

from tests.fixtures.authored_idle_contract import saved_project
from ucc.core.authored_idle import AuthoredIdleInspectionRequest, IdleAuthoringPermission
from ucc.core.target_action_format import canonical_bytes

# Public MPFB coordinate convention only: anatomical left +X, anterior -Y, up +Z.
BODY={'pelvis':(0.,0.,0.),'neck':(0.,0.,1.),'left':(1.,0.,1.),'right':(-1.,0.,1.)}
HANDS={
 'L':{'wrist':(0.,0.,0.),'middle':(1.,0.,0.),'index':(1.,-.5,0.),'little':(1.,.5,0.)},
 'R':{'wrist':(0.,0.,0.),'middle':(-1.,0.,0.),'index':(-1.,-.5,0.),'little':(-1.,.5,0.)},
}
METACARPALS=tuple(f'finger{digit}-0.{side}' for side in ('L','R') for digit in range(2,6))
PHALANGES=tuple((f'finger{digit}-{joint}.{side}',8. if digit==1 else (12.,18.,10.)[joint-1])
                for side in ('L','R') for digit in range(1,6) for joint in range(1,4))


def rotated(vector):
    """A proper invented rotation tests roll-independent equivariance."""
    angle=.73;c=math.cos(angle);s=math.sin(angle)
    x,y,z=vector
    return (c*x-s*y,s*x+c*y,z)


def identity():
    return [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]


def staged_inspection(root):
    fake=b'NONSHIPPING_OPAQUE_BYTES_NOT_A_BLEND_OR_ASSET'
    pin=sha256(fake).hexdigest()
    project=replace(saved_project(hand=False,expression=False),master_blend='master/versions/'+pin+'.blend')
    permission=IdleAuthoringPermission('master_and_derived_rig',pin,'f'*64,
        'NONSHIPPING_TEST_ONLY_NOT_ACTUAL_PERMISSION',True)
    request=AuthoredIdleInspectionRequest(str(UUID(int=710)),canonical_bytes(project.to_dict()),
        (permission,),'NONSHIPPING pure worker boundary test',True,True)
    (root/'candidate.blend').write_bytes(fake)
    (root/'idle_inspection_request.json').write_bytes(canonical_bytes(request.to_dict()))
    job={'job_id':request.job_id,'operation':'inspect_authored_idle_target','input_project':'candidate.blend',
         'options':{'request_sha256':request.sha256}}
    return request,job
