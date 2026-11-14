"""Synthetic control-flow fixtures; actual Blender evidence is separate."""
from copy import deepcopy
from types import SimpleNamespace,MethodType
import struct,unittest
from unittest.mock import patch
from blender_bridge.anatomical_reuse import ExactSourceFrames,ExactInspector,collector_factory
from blender_bridge.complete_anatomical_review import CompleteInspector,CompleteCollector,measure_complete

class Collection:
    def __init__(self,rows):self.rows=rows
    def __len__(self):return len(self.rows)
    def foreach_get(self,_name,target):
        for i,value in enumerate(v for row in self.rows for v in row):target[i]=value

def mesh():return SimpleNamespace(vertices=Collection([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.],[0.,0.,0.]]),
    loop_triangles=Collection([[0,1,2],[0,3,1],[1,3,2],[2,3,0]]),
    polygons=[SimpleNamespace(vertices=t) for t in ((0,1,2),(0,3,1),(1,3,2),(2,3,0))],
    loops=Collection([[0]]*12))

class ExactReuseTests(unittest.TestCase):
    def setUp(self):
        self.memo=ExactSourceFrames();self.computed=[]
        self.base_patch=patch.object(CompleteInspector,'inspect',lambda obj,*args:self.normal(obj,*args))
        self.base_patch.start();self.addCleanup(self.base_patch.stop)
    def normal(self,obj,_mesh,frame,skin,triangles):
        self.computed.append((obj._source,frame));obj.vertices={};obj.volume_vertices={};obj.polygons=[]
        body={'left':{'hand_triangles':[0],'central_triangles':[1]},
              'right':{'hand_triangles':[],'central_triangles':[]}}
        observation={'body_triangle_ids':[1],**deepcopy(body)}
        metadata={'frame':frame,'skin_sha256':skin,'triangle_sha256':triangles}
        obj.rows.append({**metadata,**body});obj.enclosure_rows.append({**metadata,'observation':observation})
        obj._record(frame,skin,triangles,deepcopy(observation))
    def inspector(self,source):
        obj=ExactInspector.__new__(ExactInspector);obj._source=source;obj._memo=self.memo
        obj.vertices={};obj.volume_vertices={};obj.polygons=[];obj.rows=[];obj.enclosure_rows=[];obj.complete_rows=[]
        obj.highlights=obj.complete_highlights=0;obj.status='CHECKED';obj.reason=''
        obj.world=[float(i==j) for i in range(4) for j in range(4)]
        obj.human=SimpleNamespace(matrix_world=[obj.world[i:i+4] for i in range(0,16,4)])
        obj._context=MethodType(lambda _self:b'actual-context',obj)
        return obj
    def pair(self):
        a=self.inspector(True);b=self.inspector(False);a.inspect(mesh(),1,'skin','triangles');return a,b
    def real_context(self,obj):
        obj._context=MethodType(ExactInspector._context,obj);obj._context_bytes=None
        obj._profile={'fixture':'isolated-key-test'};obj.parents={'root':None,'hand':'root'};obj.deform={'hand'}
        obj.hands={'left':'hand','right':'hand'};obj.head='root';obj.area_reason='';obj.polygon_sha='a'*64
        obj.regions={'central_body':{'root'}};obj.vertices={'left_hand':{0},'right_hand':{1},'central_body':{2}}
        obj.counts={k:len(v) for k,v in obj.vertices.items()}
        obj.volume_regions={'central_body':{'root'}};obj.volume_vertices={'central_body':{2}}
        obj.limb_roots={}
    def test_only_exact_matching_fitted_geometry_reuses(self):
        a,b=self.pair();b.inspect(mesh(),1,'skin','triangles')
        self.assertEqual(self.memo.hits,1);self.assertEqual(self.computed,[(True,1)])
        self.assertEqual(a.rows,b.rows)
        b.rows[0]['left']['hand_triangles'].append(99)
        self.assertEqual(a.rows[0]['left']['hand_triangles'],[0])
    def test_submicron_float_change_cannot_hit_quantized_skin_hash(self):
        _,b=self.pair();changed=mesh();v=struct.unpack('<f',struct.pack('<I',0x3f800001))[0]
        self.assertEqual(round(v*1_000_000),round(1.*1_000_000))
        changed.vertices.rows[0][0]=v;b.inspect(changed,1,'skin','triangles')
        self.assertEqual(self.memo.hits,0);self.assertEqual(self.computed[-1],(False,1))
    def test_triangle_order_change_misses(self):
        _,b=self.pair();changed=mesh();changed.loop_triangles.rows[0]=[1,0,2]
        b.inspect(changed,1,'skin','triangles');self.assertEqual(self.memo.hits,0)
    def test_polygon_order_change_misses(self):
        _,b=self.pair();changed=mesh();changed.polygons[0].vertices=(1,0,2)
        b.inspect(changed,1,'skin','triangles');self.assertEqual(self.memo.hits,0)
    def test_changed_context_misses(self):
        _,b=self.pair();b._context=MethodType(lambda _self:b'different-regions-or-budgets',b)
        b.inspect(mesh(),1,'skin','triangles');self.assertEqual(self.memo.hits,0)
    def test_real_context_captures_changed_weighted_region_membership(self):
        a=self.inspector(True);b=self.inspector(False);self.real_context(a);self.real_context(b)
        a.inspect(mesh(),1,'skin','triangles');b.volume_vertices['central_body']={1}
        b.inspect(mesh(),1,'skin','triangles');self.assertEqual(self.memo.hits,0)
    def test_real_context_captures_changed_ray_budget(self):
        a=self.inspector(True);b=self.inspector(False);self.real_context(a);self.real_context(b)
        a.inspect(mesh(),1,'skin','triangles')
        with patch('blender_bridge.central_enclosure.MAX_FRAME_RAY_HITS',1):
            b.inspect(mesh(),1,'skin','triangles')
        self.assertEqual(self.memo.hits,0)
    def test_changed_world_is_rejected(self):
        _,b=self.pair();b.human.matrix_world[0][3]=.001
        with self.assertRaisesRegex(ValueError,'world transform changed'):b.inspect(mesh(),1,'skin','triangles')
    def test_fitted_first_frame_always_establishes_its_own_context(self):
        _,b=self.pair();b.vertices=None;b.inspect(mesh(),1,'skin','triangles')
        self.assertEqual(self.memo.hits,0);self.assertEqual(self.computed[-1],(False,1))
    def test_source_frames_always_compute(self):
        a,_=self.pair();a.inspect(mesh(),1,'skin','triangles')
        self.assertEqual(self.computed,[(True,1),(True,1)]);self.assertEqual(self.memo.dropped,1)
    def test_bounded_memory_falls_back_to_real_computation(self):
        self.memo.bytes=256*1024*1024;a=self.inspector(True);b=self.inspector(False)
        a.inspect(mesh(),1,'skin','triangles');b.inspect(mesh(),1,'skin','triangles')
        self.assertEqual(self.memo.dropped,1);self.assertEqual(self.memo.hits,0)
    def test_reuse_still_enforces_cumulative_body_highlight_budget(self):
        _,b=self.pair()
        with patch('blender_bridge.native_body_contacts.MAX_HIGHLIGHTS',1):
            with self.assertRaisesRegex(ValueError,'COMPLETE_ANATOMICAL_SURFACES_REQUIRED'):
                b.inspect(mesh(),1,'skin','triangles')
    def test_reuse_still_enforces_complete_highlight_budget(self):
        _,b=self.pair()
        with patch('blender_bridge.complete_anatomical_review.MAX_HIGHLIGHTS',1):
            with self.assertRaisesRegex(ValueError,'COMPLETE_TRUNK_SURFACE_HIGHLIGHTS_EXCEEDED'):
                b.inspect(mesh(),1,'skin','triangles')

    def test_context_bytes_are_charged_once_for_identical_context(self):
        memo=ExactSourceFrames();key=(b'context',b'v',b't',b'p')
        memo.store(1,key,());memo.store(2,key,())
        self.assertEqual(memo.bytes,len(b'context')+6)
        self.assertEqual(memo.contexts,{b'context'})
    def test_new_context_cannot_bypass_memory_bound(self):
        memo=ExactSourceFrames()
        with patch('blender_bridge.anatomical_reuse.MAX_KEY_BYTES',10):
            memo.store(1,(b'first',b'v',b't',b'p'),())
            memo.store(2,(b'second',b'v',b't',b'p'),())
        self.assertEqual(len(memo.frames),1);self.assertEqual(memo.bytes,8)
        self.assertEqual(memo.dropped,1);self.assertEqual(memo.contexts,{b'first'})
    def test_oversized_geometry_does_not_allocate_reuse_arrays(self):
        _,b=self.pair();changed=mesh()
        class TooLarge:
            def __len__(self):return 50001
            def foreach_get(self,*_args):raise AssertionError('Allocated before geometry bounds')
        changed.vertices=TooLarge();b.inspect(changed,1,'skin','triangles')
        self.assertEqual(self.memo.hits,0);self.assertEqual(self.computed[-1],(False,1))

class CompleteReuseRoutingTests(unittest.TestCase):
    def exercise(self,paired,**kwargs):
        made=[]
        def measure(_bpy,_root,_options,*,collector_factory):
            a=collector_factory({});b=collector_factory({});made.extend((a,b))
            a.inspector=SimpleNamespace(complete_rows=[{'fixture':'source'}])
            if paired:b.inspector=SimpleNamespace(complete_rows=[{'fixture':'fitted'}])
            return {'polygon_topology_sha256':'a'*64},{'paired':paired,'source_frame_count':1}
        with patch('blender_bridge.complete_anatomical_review.measure_anatomical_safety',side_effect=measure):
            result=measure_complete(None,None,{'fitted_sha256':'b'*64} if paired else {},**kwargs)
        self.assertEqual(len(result[2]['original']['frames']),1)
        self.assertEqual(result[2]['fitted'] is not None,paired)
        return made

    def test_source_only_measurement_keeps_original_collectors_and_allocates_no_memo(self):
        with patch('blender_bridge.anatomical_reuse.ExactSourceFrames',side_effect=AssertionError('Native-only memo allocation')):
            made=self.exercise(False)
        self.assertTrue(all(type(c) is CompleteCollector for c in made))

    def test_paired_measurement_assigns_one_fresh_source_and_one_fitted_collector(self):
        made=self.exercise(True)
        self.assertEqual([c._source for c in made],[True,False])

    def test_explicit_internal_uncached_control_remains_available(self):
        with patch('blender_bridge.anatomical_reuse.ExactSourceFrames',side_effect=AssertionError('Control memo allocation')):
            made=self.exercise(True,collector_factory=CompleteCollector)
        self.assertTrue(all(type(c) is CompleteCollector for c in made))

    def test_unexpected_third_collector_is_rejected(self):
        factory=collector_factory(ExactSourceFrames());factory({});factory({})
        with self.assertRaisesRegex(ValueError,'COLLECTOR_COVERAGE'):factory({})

if __name__=='__main__':unittest.main(verbosity=2)
