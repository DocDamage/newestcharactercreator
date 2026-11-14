"""Fixed local clay shader for validated cached skin; no asset shader execution."""
from __future__ import annotations
import ctypes
import math
import os

from PySide6.QtGui import QMatrix4x4, QVector3D
from PySide6.QtOpenGL import (QOpenGLFunctions_3_3_Core, QOpenGLShaderProgram,
    QOpenGLShader, QOpenGLBuffer, QOpenGLVertexArrayObject)

from ucc.preview.motion_cache import MotionCache

VERTEX="""#version 330 core
layout(location=0) in vec3 position;
uniform mat4 mvp; uniform mat4 model;
out vec3 point_world;
void main(){ vec4 p=model*vec4(position,1.0); point_world=p.xyz; gl_Position=mvp*p; }
"""
FRAGMENT="""#version 330 core
in vec3 point_world; out vec4 color;
void main(){
 vec3 n=normalize(cross(dFdx(point_world),dFdy(point_world)));
 float light=0.25+0.75*abs(dot(n,normalize(vec3(0.5,-0.7,0.8))));
 color=vec4(vec3(0.56,0.60,0.67)*light,1.0);
}
"""


class SkinRenderer:
    """Owned GL resources. Construct/draw/close only with this context current."""
    def __init__(self,context):
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
        if (not self.program.addShaderFromSourceCode(QOpenGLShader.Vertex,VERTEX) or
                not self.program.addShaderFromSourceCode(QOpenGLShader.Fragment,FRAGMENT) or not self.program.link()):
            raise RuntimeError("Animation shader could not initialize: "+self.program.log())
        self.vao=QOpenGLVertexArrayObject()
        self.vertices=QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self.indices=QOpenGLBuffer(QOpenGLBuffer.IndexBuffer)
        if not all(o.create() for o in (self.vao,self.vertices,self.indices)):
            raise RuntimeError("Animation GPU buffers could not initialize")
        self.vertices.setUsagePattern(QOpenGLBuffer.DynamicDraw)
        self.indices.setUsagePattern(QOpenGLBuffer.DynamicDraw)
        self.loaded=None

    def draw(self,cache: MotionCache,index: int,width: int,height: int,*,yaw=-.45,pitch=.15,zoom=1.,pan=(0.,0.)):
        gl=self.gl
        gl.glViewport(0,0,max(1,width),max(1,height));gl.glEnable(0x0b71);gl.glDisable(0x0b44)
        gl.glClearColor(.07,.09,.13,1.);gl.glClear(0x4000|0x100)
        self.vao.bind()
        if not self.program.bind():raise RuntimeError("Animation GPU shader binding failed")
        identity=(id(cache),index)
        if self.loaded!=identity:
            vertices,indices=cache.frame(index)
            self.vertices.bind();self.vertices.allocate(vertices,len(vertices))
            self.program.enableAttributeArray(0);self.program.setAttributeBuffer(0,0x1406,0,3,12)
            self.indices.bind();self.indices.allocate(indices,len(indices))
            self.loaded=identity
        center=QVector3D(*cache.hips[index])
        right=QVector3D(math.cos(yaw),math.sin(yaw),0)
        center+=right*pan[0]*cache.radius+QVector3D(0,0,pan[1]*cache.radius)
        direction=QVector3D(math.sin(yaw)*math.cos(pitch),-math.cos(yaw)*math.cos(pitch),math.sin(pitch))
        view=QMatrix4x4();view.lookAt(center+direction*(cache.radius*3.5*zoom),center,QVector3D(0,0,1))
        projection=QMatrix4x4();projection.perspective(45.,max(1,width)/max(1,height),cache.radius*.01,cache.radius*100)
        self.program.setUniformValue("mvp",projection*view)
        self.program.setUniformValue("model",QMatrix4x4(*cache.world_matrix))
        self._draw(0x0004,cache.triangle_count*3,0x1405,None)
        error=gl.glGetError()
        if error:raise RuntimeError(f"Animation GPU drawing failed (OpenGL {error:#x})")
        self.program.release();self.vao.release()

    def close(self):
        self.indices.destroy();self.vertices.destroy();self.vao.destroy()
        self.program.removeAllShaders();self.loaded=None
