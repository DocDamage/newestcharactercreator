#[compute]
#version 450

layout(local_size_x = 64) in;
layout(std430, set = 0, binding = 0) readonly buffer Positions { vec4 smoothed[]; };
layout(std430, set = 0, binding = 1) readonly buffer Ranges { uvec2 corners_of[]; };
layout(std430, set = 0, binding = 2) readonly buffer OrderedCorners { uint corner[]; };
layout(std430, set = 0, binding = 3) readonly buffer Contributions { vec4 contribution[]; };
layout(std430, set = 0, binding = 4) writeonly buffer Output { vec4 corrected[]; };
layout(push_constant, std430) uniform Count { uvec4 counts; } extent;

void main() {
    uint vertex = gl_GlobalInvocationID.x;
    if (vertex >= extent.counts.x) return;
    uvec2 range = corners_of[vertex];
    precise float total = 0;
    for (uint i = 0; i < range.y; ++i)
        total += contribution[corner[range.x + i]].w;
    precise vec3 result = smoothed[vertex].xyz;
    if (total > 0.0) {
        for (uint i = 0; i < range.y; ++i) {
            vec4 item = contribution[corner[range.x + i]];
            result += item.xyz * (item.w / total);
        }
    }
    corrected[vertex] = vec4(result, 1);
}
