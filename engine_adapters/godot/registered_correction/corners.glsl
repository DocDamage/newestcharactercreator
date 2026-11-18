#[compute]
#version 450

layout(local_size_x = 64) in;
layout(std430, set = 0, binding = 0) readonly buffer Positions { vec4 point[]; };
layout(std430, set = 0, binding = 1) readonly buffer PolygonCorners { uvec4 corner[]; };
layout(std430, set = 0, binding = 2) readonly buffer BindOffsets { vec4 bound_delta[]; };
layout(std430, set = 0, binding = 3) writeonly buffer Contributions { vec4 contribution[]; };
layout(push_constant, std430) uniform Count { uvec4 counts; } extent;

float sum3(vec3 v) {
    precise float sum = (v.x + v.y) + v.z;
    return sum;
}
vec3 unit(vec3 value) {
    float length = sqrt(sum3(value * value));
    return length > 0.0 ? value / length : vec3(0);
}

void main() {
    uint id = gl_GlobalInvocationID.x;
    if (id >= extent.counts.x) return;
    uvec3 ids = corner[id].xyz;
    vec3 left = unit(point[ids.x].xyz - point[ids.y].xyz);
    vec3 right = unit(point[ids.y].xyz - point[ids.z].xyz);
    if (!any(greaterThan(abs(left - right), vec3(1.1920928955078125e-6)))) {
        contribution[id] = vec4(0);
        return;
    }
    float d = clamp(sum3(left * right), -1.0, 1.0);
    float weight = acos(d);
    vec3 normal = unit(cross(left, right));
    vec3 axis = unit(left + right);
    vec3 other = cross(normal, axis);
    vec3 offset = bound_delta[id].xyz;
    precise vec3 displacement = (axis * offset.x + other * offset.y) + normal * offset.z;
    contribution[id] = vec4(displacement, weight);
}
