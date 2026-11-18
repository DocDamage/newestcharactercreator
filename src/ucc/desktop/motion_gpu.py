"""Fixed local clay or owned dielectric PBR shader; no asset shader execution."""
from __future__ import annotations
import ctypes
from hashlib import sha256
import math
import os
import struct

from PySide6.QtGui import QMatrix4x4, QVector3D
from PySide6.QtOpenGL import (QOpenGLFunctions_3_3_Core, QOpenGLShaderProgram,
    QOpenGLShader, QOpenGLBuffer, QOpenGLVertexArrayObject)

from ucc.preview.idle_loop_clock import LoopSample
from ucc.preview.motion_cache import MotionCache

VERTEX="""#version 330 core
layout(location=0) in vec3 position;
uniform mat4 mvp; uniform mat4 model;
out vec3 point_world;
void main(){ vec4 p=model*vec4(position,1.0); point_world=p.xyz; gl_Position=mvp*p; }
"""
IDLE_LOOP_VERTEX="""#version 330 core
layout(location=0) in vec3 position;
layout(location=2) in vec3 next_position;
uniform mat4 mvp; uniform mat4 model;
uniform float pose_blend;
out vec3 point_world;
void main(){ vec4 p=model*vec4(mix(position,next_position,pose_blend),1.0);
 point_world=p.xyz; gl_Position=mvp*p; }
"""
FRAGMENT="""#version 330 core
in vec3 point_world; out vec4 color; uniform vec3 tint;
void main(){
 vec3 n=normalize(cross(dFdx(point_world),dFdy(point_world)));
 float light=0.25+0.75*abs(dot(n,normalize(vec3(0.5,-0.7,0.8))));
 color=vec4(tint*light,1.0);
}
"""


class SkinRenderer:
    """Owned GL resources. Construct/draw/close only with this context current."""
    def __init__(self,context,*,material=None):
        self.material=material
        self.gl=QOpenGLFunctions_3_3_Core()
        if not self.gl.initializeOpenGLFunctions():raise RuntimeError("Animation playback needs desktop OpenGL 3.3")
        address=int(context.getProcAddress(b"glDrawElements"))
        if address<=3 or address in (0xffffffff,0xffffffffffffffff):raise RuntimeError("OpenGL indexed drawing is unavailable")
        # PySide6 6.11 rejects its documented integer pointer argument. Resolve
        # this one fixed GL symbol from the current trusted Qt context instead;
        # no user-supplied library/function/path and no PyOpenGL dependency.
        convention=ctypes.WINFUNCTYPE if os.name=="nt" else ctypes.CFUNCTYPE
        self._draw=convention(None,ctypes.c_uint,ctypes.c_int,ctypes.c_uint,ctypes.c_void_p)(address)
        self.program=QOpenGLShaderProgram()
        vertex,fragment=VERTEX,FRAGMENT
        if material is not None:
            from .material_shader import VERTEX as vertex,FRAGMENT as fragment
        if (not self.program.addShaderFromSourceCode(QOpenGLShader.Vertex,vertex) or
                not self.program.addShaderFromSourceCode(QOpenGLShader.Fragment,fragment) or not self.program.link()):
            raise RuntimeError("Animation shader could not initialize: "+self.program.log())
        self.vao=QOpenGLVertexArrayObject()
        self.vertices=QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self.indices=QOpenGLBuffer(QOpenGLBuffer.IndexBuffer)
        self.highlights=QOpenGLBuffer(QOpenGLBuffer.IndexBuffer)
        self.normals=QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        if not all(o.create() for o in (self.vao,self.vertices,self.indices,self.highlights,self.normals)):
            raise RuntimeError("Animation GPU buffers could not initialize")
        self.vertices.setUsagePattern(QOpenGLBuffer.DynamicDraw)
        self.indices.setUsagePattern(QOpenGLBuffer.DynamicDraw)
        self.highlights.setUsagePattern(QOpenGLBuffer.DynamicDraw)
        self.loaded=None
        self._idle_program=None
        self._idle_vertices=None
        self._idle_cache=None
        self._idle_right=None

    def _loop_program(self):
        if self._idle_program is None:
            program=QOpenGLShaderProgram()
            if (not program.addShaderFromSourceCode(QOpenGLShader.Vertex,IDLE_LOOP_VERTEX) or
                    not program.addShaderFromSourceCode(QOpenGLShader.Fragment,FRAGMENT) or not program.link()):
                raise RuntimeError('Idle interpolation shader could not initialize: '+program.log())
            vertices=QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            if not vertices.create():
                raise RuntimeError('Idle interpolation buffer could not initialize')
            vertices.setUsagePattern(QOpenGLBuffer.DynamicDraw)
            self._idle_program=program
            self._idle_vertices=vertices
        return self._idle_program

    def _upload_loop_sample(self, cache, sample, program):
        right=sample.right_index
        if self._idle_cache is not cache or self._idle_right!=right:
            next_positions,next_triangles=cache.frame(right)
            expected=cache.surface_review.triangle_hashes
            if (len(self.coordinates)!=12*cache.vertex_count or len(next_positions)!=len(self.coordinates)
                    or len(next_triangles)!=12*cache.triangle_count or next_triangles!=self.triangles
                    or sha256(next_triangles).hexdigest()!=expected[sample.left_index] or
                    expected[sample.left_index]!=expected[right]):
                raise RuntimeError('Idle interpolation requires matching independently verified topology')
            self._idle_vertices.bind()
            self._idle_vertices.allocate(next_positions,len(next_positions))
            program.setAttributeBuffer(2,0x1406,0,3,12)
            self._idle_cache=cache
            self._idle_right=right
        program.enableAttributeArray(2)
        self.gl.glUniform1f(program.uniformLocation('pose_blend'),float(sample.alpha))

    def draw(self,cache: MotionCache,index: int,width: int,height: int,*,yaw=-.45,pitch=.15,zoom=1.,pan=(0.,0.),
             highlight_intersections=False,focus_intersections=False,idle_sample: LoopSample | None=None):
        gl=self.gl
        if getattr(cache,'material',None)!=self.material:raise RuntimeError('Preview shader does not match the current surface material')
        blend=None
        if idle_sample is not None:
            if (type(idle_sample) is not LoopSample or idle_sample.left_index!=index or type(cache) is not MotionCache
                    or (cache.frame_count,cache.fps,cache.source_first_frame)!=(300,30,2)
                    or cache.surface_review is None or len(cache.surface_review.triangle_hashes)!=cache.frame_count
                    or self.material is not None or highlight_intersections or focus_intersections):
                raise RuntimeError('Idle interpolation requires the complete original clay preview cache')
            if idle_sample.alpha:
                blend=idle_sample
        program=self._loop_program() if blend is not None else self.program
        if self.material is not None:
            gl.glDisable(0x8DB9)  # Shader performs the linear -> sRGB conversion.
        gl.glViewport(0,0,max(1,width),max(1,height));gl.glEnable(0x0b71);gl.glDisable(0x0b44)
        if self.material is not None:gl.glEnable(0x0b44)
        gl.glClearColor(.07,.09,.13,1.);gl.glClear(0x4000|0x100)
        self.vao.bind()
        if not program.bind():raise RuntimeError("Animation GPU shader binding failed")
        identity=(id(cache),index)
        if self.loaded!=identity:
            vertices,indices=cache.frame(index)
            self.vertices.bind();self.vertices.allocate(vertices,len(vertices))
            program.enableAttributeArray(0);program.setAttributeBuffer(0,0x1406,0,3,12)
            if self.material is not None:
                normals=cache.frame_normals(index) if hasattr(cache,'frame_normals') else cache.normals
                if len(normals)!=len(vertices):raise RuntimeError('Material preview lacks complete smooth normals')
                self.normals.bind();self.normals.allocate(normals,len(normals))
                program.enableAttributeArray(1);program.setAttributeBuffer(1,0x1406,0,3,12)
            self.indices.bind();self.indices.allocate(indices,len(indices))
            self.coordinates=vertices;self.triangles=indices
            self.loaded=identity
        if blend is not None:
            try:
                self._upload_loop_sample(cache,blend,program)
            except Exception:
                program.release();self.vao.release()
                raise
        elif self._idle_vertices is not None:
            program.disableAttributeArray(2)
        marked=cache.surface_review.triangles[index] if cache.surface_review is not None else ()
        selection=b"".join(self.triangles[i*12:i*12+12] for i in marked) if highlight_intersections or focus_intersections else b""
        overlay=selection if highlight_intersections else b""
        center=QVector3D(*cache.hips[index])
        if blend is not None:
            center=center*(1-blend.alpha)+QVector3D(*cache.hips[blend.right_index])*blend.alpha
        radius=cache.radius
        if focus_intersections and selection:
            ids={v for row in struct.iter_unpack("<III",selection) for v in row}
            world=QMatrix4x4(*cache.world_matrix)
            points=[world.map(QVector3D(*struct.unpack_from("<fff",self.coordinates,i*12))) for i in ids]
            points=[(p.x(),p.y(),p.z()) for p in points]
            lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
            center=QVector3D(*[(a+b)/2 for a,b in zip(lo,hi)])
            radius=max(.06,min(cache.radius,sum((a-b)**2 for a,b in zip(lo,hi))**.5*.7))
        right=QVector3D(math.cos(yaw),math.sin(yaw),0)
        center+=right*pan[0]*radius+QVector3D(0,0,pan[1]*radius)
        direction=QVector3D(math.sin(yaw)*math.cos(pitch),-math.cos(yaw)*math.cos(pitch),math.sin(pitch))
        camera=center+direction*(radius*3.5*zoom)
        view=QMatrix4x4();view.lookAt(camera,center,QVector3D(0,0,1))
        projection=QMatrix4x4();projection.perspective(45.,max(1,width)/max(1,height),radius*.01,cache.radius*100)
        program.setUniformValue("mvp",projection*view)
        program.setUniformValue("model",QMatrix4x4(*cache.world_matrix))
        if self.material is None:program.setUniformValue("tint",QVector3D(.56,.60,.67))
        else:
            program.setUniformValue('base_color_linear',QVector3D(*self.material.linear_rgba[:3]))
            # PySide6 6.11 resolves the scalar overload to glUniform1i even
            # for Python float. Use the typed core entry point for GLSL float.
            gl.glUniform1f(program.uniformLocation('roughness'),float(self.material.roughness))
            program.setUniformValue('camera_world',camera)
        self.indices.bind()
        self._draw(0x0004,cache.triangle_count*3,0x1405,None)
        if overlay:
            self.highlights.bind();self.highlights.allocate(overlay,len(overlay))
            program.setUniformValue("tint",QVector3D(1.,.18,.04))
            gl.glEnable(0x8037);gl.glPolygonOffset(-1.,-1.)
            self._draw(0x0004,len(overlay)//4,0x1405,None)
            gl.glDisable(0x8037);self.indices.bind()
        error=gl.glGetError()
        if error:raise RuntimeError(f"Animation GPU drawing failed (OpenGL {error:#x})")
        program.release();self.vao.release()

    def close(self):
        if self._idle_vertices is not None:
            self._idle_vertices.destroy()
            self._idle_program.removeAllShaders()
            self._idle_cache=None
            self._idle_right=None
            self._idle_program=None
            self._idle_vertices=None
        self.normals.destroy();self.highlights.destroy();self.indices.destroy();self.vertices.destroy();self.vao.destroy()
        self.program.removeAllShaders();self.loaded=None
