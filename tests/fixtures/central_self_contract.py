"""Metadata-only BVH interface double, never physical intersection evidence."""


def tree_contract(pairs):
    class Tree:
        def __init__(self,labels):self.labels=labels

        @classmethod
        def FromPolygons(cls,points,faces,**kwargs):
            # Each original nonshipping triangle has one coordinate label.
            return cls([int(points[face[0]][0]) for face in faces])

        def overlap(self,other):
            return [(i,j) for i,a in enumerate(self.labels) for j,b in enumerate(other.labels) if (a,b) in pairs]
    return Tree


def disjoint_triangles():
    points=[(float(i),float(j),0.) for i in range(4) for j in range(3)]
    return points,[(i*3,i*3+1,i*3+2) for i in range(4)]
