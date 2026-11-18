"""Synthetic Qt paint and OpenGL command-boundary controls for idle blending."""

from dataclasses import replace
from hashlib import sha256
import os
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call
import zlib

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ucc.preview.idle_loop_clock import LoopSample
from ucc.preview.motion_cache import MotionCache
from ucc.preview.surface_review import SurfaceReview
try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.motion_gpu import SkinRenderer
    from ucc.desktop.motion_viewer import MotionCanvas
except ImportError:
    QApplication = None


def synthetic_cache(*, different_topology=False):
    first = struct.pack('<9f', 0., 0., 0., 1., 0., 0., 0., 1., 0.)
    last = struct.pack('<9f', 0., 0., 1., 1., 0., 1., 0., 1., 1.)
    triangles = struct.pack('<III', 0, 1, 2)
    final_triangles = struct.pack('<III', 0, 2, 1) if different_topology else triangles
    block1, block2 = zlib.compress(first+triangles), zlib.compress(last+final_triangles)
    chunks = ((0,len(block1)),)*299 + ((len(block1),len(block2)),)
    hashes = (sha256(triangles).hexdigest(),)*299 + (sha256(final_triangles).hexdigest(),)
    surface = SurfaceReview('CHECKED', '', ((),)*300, ((0,0),)*300, hashes)
    world = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
    return MotionCache(block1+block2, chunks, ((0.,0.,0.),)*300, world, 30., 3, 1, 1., 2, surface)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1', 'Optional Qt unavailable')
class IdleLoopRendererQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Idle loop paint controls require Qt')
        cls.app = QApplication.instance() or QApplication(['idle-loop-paint-tests'])

    def renderer(self):
        renderer = SkinRenderer.__new__(SkinRenderer)
        renderer.material = None
        renderer.gl = Mock()
        renderer.gl.glGetError.return_value = 0
        renderer.program, renderer._idle_program = Mock(), Mock()
        renderer._idle_program.uniformLocation.return_value = 17
        renderer._draw, renderer.vao = Mock(), Mock()
        renderer.vertices, renderer.indices, renderer._idle_vertices = Mock(), Mock(), Mock()
        renderer.loaded = renderer._idle_cache = renderer._idle_right = None
        return renderer

    def canvas(self, cache):
        canvas = MotionCanvas(cache)
        renderer = SimpleNamespace(draw=Mock())
        canvas.renderer = renderer
        self.addCleanup(canvas.deleteLater)
        self.addCleanup(setattr, canvas, 'renderer', None)
        return canvas, renderer

    def test_guarded_wrap_forwards_pair_and_zero_alpha_uses_ordinary_draw(self):
        cache = synthetic_cache()
        canvas, renderer = self.canvas(cache)
        guard = Mock(return_value=True)
        sample = LoopSample(299,0,.4)
        canvas.set_idle_loop_sample(sample, guard)
        canvas.paintGL()
        self.assertIs(renderer.draw.call_args.args[0],cache)
        self.assertEqual(renderer.draw.call_args.args[1],299)
        self.assertIs(renderer.draw.call_args.kwargs['idle_sample'],sample)
        canvas.set_idle_loop_sample(LoopSample(0,1,0.), guard)
        canvas.paintGL()
        self.assertEqual(renderer.draw.call_args.args[1],0)
        self.assertNotIn('idle_sample',renderer.draw.call_args.kwargs)
        self.assertEqual(guard.call_count,2)
        canvas.clear_idle_loop_sample()
        canvas.paintGL()
        self.assertEqual(guard.call_count,2)
        self.assertNotIn('idle_sample',renderer.draw.call_args.kwargs)

    def test_denied_reentrant_or_replaced_cache_paint_cannot_fall_through(self):
        for action in ('denied', 'reentrant_clear', 'reentrant_cache_switch', 'different_cache'):
            with self.subTest(action=action):
                cache = synthetic_cache()
                canvas, renderer = self.canvas(cache)
                def guard():
                    if action=='reentrant_clear':
                        canvas.clear_idle_loop_sample(block_paint=True)
                    if action=='reentrant_cache_switch':
                        canvas.cache=replace(cache)
                    return action!='denied'
                canvas.set_idle_loop_sample(LoopSample(299,0,.5), guard)
                if action=='different_cache':
                    canvas.cache=replace(cache)
                canvas.paintGL()
                canvas.paintGL()
                renderer.draw.assert_not_called()

    def test_queued_paint_is_suppressed_after_explicit_revocation(self):
        canvas, renderer = self.canvas(synthetic_cache())
        guard = Mock(return_value=True)
        canvas.set_idle_loop_sample(LoopSample(299,0,.5), guard)
        canvas.clear_idle_loop_sample(block_paint=True)
        canvas.paintGL()
        guard.assert_not_called()
        renderer.draw.assert_not_called()

    def test_gl_uploads_original_wrap_pair_once_and_preserves_exact_draw(self):
        cache = synthetic_cache()
        renderer = self.renderer()
        renderer.draw(cache,299,320,180,idle_sample=LoopSample(299,0,.25))
        renderer.draw(cache,299,320,180,idle_sample=LoopSample(299,0,.75))
        left, topology = cache.frame(299)
        right, right_topology = cache.frame(0)
        self.assertEqual(topology,right_topology)
        self.assertNotEqual(left,right)
        renderer.vertices.allocate.assert_called_once_with(left,len(left))
        renderer._idle_vertices.allocate.assert_called_once_with(right,len(right))
        renderer.indices.allocate.assert_called_once_with(topology,len(topology))
        self.assertEqual(renderer.gl.glUniform1f.call_args_list,[call(17,.25),call(17,.75)])
        renderer.program.bind.assert_not_called()
        renderer.draw(cache,299,320,180)
        renderer.program.bind.assert_called_once()
        renderer.program.disableAttributeArray.assert_called_once_with(2)
        self.assertEqual(renderer._draw.call_count,3)
        self.assertEqual(renderer.gl.glUniform1f.call_count,2)

    def test_gl_rejects_different_topology_before_submitting(self):
        cache = synthetic_cache(different_topology=True)
        renderer = self.renderer()
        with self.assertRaisesRegex(RuntimeError, 'matching independently verified topology'):
            renderer.draw(cache,299,320,180,idle_sample=LoopSample(299,0,.5))
        renderer._idle_vertices.allocate.assert_not_called()
        renderer._draw.assert_not_called()
        renderer._idle_program.release.assert_called_once()
        renderer.vao.release.assert_called_once()
