"""Invented non-shipping weight memberships; never actual Blender/asset evidence."""
from types import SimpleNamespace as NS
import struct
from blender_bridge import native_region_mask as m
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
class Groups(list):
 def __init__(self,human):super().__init__();self.human=human;self.fail=False
 def get(self,name):return next((x for x in self if x.name==name),None)
 def new(self,name):
  group=NS(name=name,index=len(self))
  def add(indices,value,operation):
   if self.fail:raise RuntimeError('Invented add failure')
   for i in indices:self.human.data.vertices[i].groups.append(NS(group=group.index,weight=f32(value)))
  group.add=add;self.append(group);return group
 def remove(self,group):
  assert group is self[-1]
  for vertex in self.human.data.vertices:vertex.groups[:]=[r for r in vertex.groups if r.group!=group.index]
  self.pop()
def scene():
 h=NS(data=NS(vertices=[]));h.vertex_groups=Groups(h)
 names=(*m.SOURCE_GROUPS,'Invented unrelated group')
 for name in names:h.vertex_groups.new(name)
 for n in range(20):h.data.vertices.append(NS(index=n,groups=[NS(group=i,weight=f32(v)) for i,v in enumerate((.4,.3,.2,.1,.1,.37) if n%2 else (.2,.1,.1,.15,.2,.37))]))
 rig=NS(data=NS(bones={name:NS(use_deform=True) for name in m.SOURCE_GROUPS}))
 return h,rig
