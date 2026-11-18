#[compute]
#version 450

layout(local_size_x = 64) in;
layout(std430, set = 0, binding = 0) readonly buffer Input { vec4 before[]; };
layout(std430, set = 0, binding = 1) readonly buffer Ranges { uvec2 neighbors_of[]; };
layout(std430, set = 0, binding = 2) readonly buffer Adjacency { uint neighbor[]; };
layout(std430, set = 0, binding = 3) writeonly buffer Output { vec4 after[]; };
layout(push_constant, std430) uniform Count { uvec4 counts; } extent;

void main() {
    uint vertex = gl_GlobalInvocationID.x;
    if (vertex >= extent.counts.x) return;
    uvec2 range = neighbors_of[vertex];
    vec3 center = before[vertex].xyz;
    precise vec3 sum = vec3(0);
    for (uint i = 0; i < range.y; ++i)
        sum += before[neighbor[range.x + i]].xyz - center;
    precise vec3 point = center + sum * (0.5 / float(max(range.y, 1u)));
    after[vertex] = vec4(point, 0);
}
