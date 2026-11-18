#[compute]
#version 450
layout(local_size_x = 64) in;
layout(std430,set=0,binding=0) readonly buffer Positions { vec4 position[]; };
layout(std430,set=0,binding=1) readonly buffer Ranges { uvec2 range_of[]; };
layout(std430,set=0,binding=2) readonly buffer Vertices { uint vertex[]; };
layout(std430,set=0,binding=3) writeonly buffer Output { vec4 normal[]; };
layout(push_constant,std430) uniform Extent { uvec4 count; } extent;
void main() {
    uint face=gl_GlobalInvocationID.x;
    if (face>=extent.count.x) return;
    uvec2 r=range_of[face];
    vec3 origin=position[vertex[r.x]].xyz;
    precise vec3 area=vec3(0);
    for (uint i=1u;i+1u<r.y;++i)
        area+=cross(position[vertex[r.x+i]].xyz-origin,position[vertex[r.x+i+1u]].xyz-origin);
    float size=length(area);
    normal[face]=size>0.0 ? vec4(area/size,1) : vec4(0);
}
