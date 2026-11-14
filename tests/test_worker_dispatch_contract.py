"""Compare desktop/worker dispatch metadata without pretending to run Blender."""
import ast
from pathlib import Path
import unittest

from blender_bridge.body_contact_areas import OPERATIONS as BODY_AREA_OPERATIONS
from blender_bridge.native_area_candidate import OPERATION as AREA_CANDIDATE_OPERATION
from ucc.jobs.protocol import SUPPORTED_OPERATIONS


class WorkerDispatchContractTests(unittest.TestCase):
    def test_every_desktop_operation_is_allowed_and_dispatched_by_worker(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'blender_bridge/entrypoint.py').read_text())
        names={'PROTOCOL_VERSION','BODY_CONTACT_OPERATIONS','OPERATIONS'};nodes=[]
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in node.targets):nodes.append(node)
            elif isinstance(node,ast.AugAssign) and isinstance(node.target,ast.Name) and node.target.id=='OPERATIONS':nodes.append(node)
            elif (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and
                  isinstance(node.value.func,ast.Attribute) and isinstance(node.value.func.value,ast.Name) and
                  node.value.func.value.id=='OPERATIONS' and node.value.func.attr=='add'):nodes.append(node)
        # Execute only the inspected static operation-set declarations, never
        # imports, Blender functions or the worker entrypoint.
        scope={'BODY_AREA_OPERATIONS':BODY_AREA_OPERATIONS,'AREA_CANDIDATE_OPERATION':AREA_CANDIDATE_OPERATION}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'worker-operation-metadata','exec'),scope)
        self.assertEqual(scope['OPERATIONS'],SUPPORTED_OPERATIONS)
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        dispatch=next(n.value.value for n in ast.walk(main) if isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='action' for t in n.targets) and isinstance(n.value,ast.Subscript) and
            isinstance(n.value.value,ast.Dict))
        self.assertEqual({ast.literal_eval(k) for k in dispatch.keys},SUPPORTED_OPERATIONS)
