"""Owned OpenGL 3.3 dielectric GGX preview, linear lighting and sRGB output.

One fixed white directional light plus diffuse ambient. No textures, asset
programs, environment map, shadows or claim of Blender render parity.
"""
VERTEX='''#version 330 core
layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;
uniform mat4 mvp; uniform mat4 model;
out vec3 point_world; out vec3 normal_world;
void main(){vec4 p=model*vec4(position,1.0);point_world=p.xyz;
 normal_world=transpose(inverse(mat3(model)))*normal;gl_Position=mvp*p;}
'''
FRAGMENT='''#version 330 core
in vec3 point_world; in vec3 normal_world; out vec4 color;
uniform vec3 base_color_linear; uniform float roughness; uniform vec3 camera_world;
const float PI=3.141592653589793;
vec3 srgb(vec3 v){v=max(v,vec3(0.0));return mix(12.92*v,1.055*pow(v,vec3(1.0/2.4))-0.055,step(vec3(0.0031308),v));}
float smith(float n,float a2){return 2.0*n/(n+sqrt(a2+(1.0-a2)*n*n));}
void main(){
 vec3 N=normalize(normal_world);vec3 V=normalize(camera_world-point_world);
 vec3 L=normalize(vec3(0.5,-0.7,0.8));vec3 H=(V+L)/max(length(V+L),0.000001);
 float nl=max(dot(N,L),0.0),nv=max(dot(N,V),0.0),nh=max(dot(N,H),0.0),vh=max(dot(V,H),0.0);
 // A finite sampling floor approximates the zero-roughness delta lobe.
 float a=pow(max(roughness,0.045),2.0),a2=a*a;
 float denominator=nh*nh*(a2-1.0)+1.0;
 float D=a2/(PI*denominator*denominator);
 vec3 F=vec3(0.04)+(vec3(1.0)-vec3(0.04))*pow(1.0-vh,5.0);
 float G=smith(nl,a2)*smith(nv,a2);
 vec3 specular=D*G*F/max(4.0*nl*nv,0.00001);
 vec3 diffuse=(vec3(1.0)-F)*base_color_linear/PI;
 vec3 linear=base_color_linear*0.03+(diffuse+specular)*nl*2.5;
 color=vec4(srgb(clamp(linear,0.0,1.0)),1.0);
}
'''
