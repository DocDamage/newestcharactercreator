"""Isolated nonshipping code identities and numeric records; never engine proof."""
from hashlib import sha256
from uuid import UUID
from pathlib import Path
from ucc.core.storage import ProjectStore
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.jobs.godot_registered_body_inputs import RegisteredBodyInputs
from ucc.export.godot_registered_body_runtime import RegisteredRuntimeExecutionSelection,RuntimeCodeSelection
from ucc.export.godot_runtime_contract import CODE_FILES


def execution_selection():
    return RegisteredRuntimeExecutionSelection(str(UUID(int=777)),"a"*64,
        tuple(RuntimeCodeSelection(name,sha256(("NONSHIPPING_NOT_EXECUTED:"+name).encode()).hexdigest(),len("NONSHIPPING_NOT_EXECUTED:"+name)) for name in sorted(CODE_FILES)),
        "b"*64,"c"*64,"d"*64,"Isolated synthetic coordination test only",True)


class BodyCoordinationFixture:
    """Coordinator-only data doubles. All native/engine gates are stubbed."""
    def __init__(self,root:Path):
        self.root=root;self.store=ProjectStore(root/'project');self.store.root.mkdir()
        (self.store.root/'.ucc-jobs').mkdir();self.store.file.write_bytes(b'NONSHIPPING_PROJECT_MARKER')
        source=root/'inputs';source.mkdir()
        names=('character.glb','skin_plan.json','project.godot','configure.gd','validate.gd')
        files={};records={}
        for name in names:
            raw=('NONSHIPPING_NOT_EXECUTED:'+name).encode();path=source/name;path.write_bytes(raw)
            files[name]=path;records[name]=dict(sha256=sha256(raw).hexdigest(),bytes=len(raw))
        self.inputs=RegisteredBodyInputs(files,records,{},lambda:None)
        self.selection=RegisteredInputSelection('nonshipping-project',1,*(['a'*64]*2),'nonshipping-clip',*(['a'*64]*3))
        self.execution=execution_selection()

    def args(self):
        return dict(selection=self.selection,retention_id=str(UUID(int=778)),expected_manifest_sha256='a'*64,
            database_path=self.root/'unused-catalog',permissions=(),preparation=None,
            expected_production_receipt_sha256='b'*64,execution=self.execution,
            godot_exe=self.root/'NOT_A_GODOT_CONSOLE.exe',godot_main_exe=self.root/'NOT_A_GODOT_MAIN.exe')
