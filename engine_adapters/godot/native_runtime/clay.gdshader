shader_type spatial;
render_mode unshaded, cull_disabled;
varying vec3 world_normal;
void vertex(){world_normal=normalize(MODEL_NORMAL_MATRIX*NORMAL);}
void fragment(){
 vec3 light=normalize(vec3(0.4,0.7,0.6));
 float diffuse=0.15+0.85*max(dot(normalize(world_normal),light),0.0);
 ALBEDO=vec3(0.8)*diffuse;
}
