#[compute]
#version 450
layout(local_size_x = 64) in;
layout(std430,set=0,binding=0) readonly buffer Positions { vec4 position[]; };
layout(std430,set=0,binding=1) readonly buffer Corners { uvec4 corner[]; };
layout(std430,set=0,binding=2) readonly buffer Ranges { uvec2 range_of[]; };
layout(std430,set=0,binding=3) readonly buffer CornersByVertex { uint corner_index[]; };
layout(std430,set=0,binding=4) readonly buffer FaceNormals { vec4 face_normal[]; };
layout(std430,set=0,binding=5) readonly buffer OriginalFaces { uint face_id[]; };
layout(std430,set=0,binding=6) writeonly buffer Output { vec4 normal[]; };
layout(push_constant,std430) uniform Extent { uvec4 count; } extent;
void main() {
    uint vertex=gl_GlobalInvocationID.x;
    if(vertex>=extent.count.x) return;
    vec3 center=position[vertex].xyz;
    uvec2 r=range_of[vertex];
    precise vec3 weighted=vec3(0);
    for(uint i=0u;i<r.y;++i) {
        uint index = corner_index[r.x+i];
        uvec4 c = corner[index];
        vec3 a=position[c.x].xyz-center;
        vec3 b=position[c.z].xyz-center;
        vec4 n=face_normal[face_id[index]];
        if (dot(a,a)<=0.0||dot(b,b)<=0.0||n.w!=1.0) {
            normal[vertex]=vec4(0);
            return;
        }
        a=normalize(a);
        b=normalize(b);
        float angle=atan(length(cross(a,b)),dot(a,b));
        weighted+=n.xyz*angle;
    }
    float size=length(weighted);
    normal[vertex]=size>0.0 ? vec4(weighted/size,0) : vec4(0);
}
