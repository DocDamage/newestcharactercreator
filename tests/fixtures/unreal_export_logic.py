"""NONSHIPPING Unreal publication byte markers; never actual native evidence."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import json
from fixtures.unreal_source_logic import UnrealSourceFixture, digest
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_contract import READINESS_FLAGS
from ucc.export.unreal_blender_recipe import FILES, NORMAL_BYTES, VERIFICATION_FILE
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.godot_candidate_inputs import identity
from ucc.jobs.unreal_preparation import PreparedUnrealSource
from ucc.jobs.unreal_engine import PreparedUnrealEngine, DELIVERY_FILES
from ucc.jobs.unreal_toolchain import UnrealToolchain


class UnrealExportFixture:
    def __init__(self, root: Path):
        self.root = root
        source_fixture = UnrealSourceFixture(root)
        self.store = source_fixture.store; self.project = self.store.load()
        self.review = source_fixture.review; self.sources = source_fixture.sources
        self.exe = source_fixture.exe; self.worker = source_fixture.worker; self.data = source_fixture.data
        self.binding = source_fixture.binding | {'recipe_sha256':'b'*64, 'stage_sha256':'c'*64,
            'verification_sha256':'d'*64, 'source_master_sha256':self.sources['master'].stem,
            'material_master_sha256':self.sources['master'].stem, 'final_master_sha256':self.sources['master'].stem}
        self.proofs = self.store.root/'materials/proofs'; self.proofs.mkdir(parents=True)
        for letter in ('b','c','d'):
            (self.proofs/(letter*64+'.json')).write_bytes(b'{"UNIT_NOT_REAL_PROOF":true}')
        self.resource = root/'UNIT_FIRST_PARTY_RESOURCE.py'; self.resource.write_bytes(b'UNIT_NOT_EXECUTED_RESOURCE')
        engine_root = root/'UNIT_TOOLS/Engine'; self.editor = engine_root/'Binaries/Win64/UnrealEditor.exe'
        build_version = engine_root/'Build/Build.version'; ubt = engine_root/'UNIT_UBT.dll'
        dotnet = root/'UNIT_TOOLS/UNIT_DOTNET.exe'; compiler = root/'UNIT_TOOLS/VS/UNIT_COMPILER.exe'
        for path in (self.editor,build_version,ubt,dotnet,compiler):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('UNIT_NOT_EXECUTABLE:'+path.name).encode())
        self.toolchain = UnrealToolchain(engine_root,self.editor,build_version,ubt,dotnet,compiler,
            compiler.parent,root/'UNIT_TOOLS/SDK',
            tuple((str(p),digest(p)) for p in (self.editor,build_version,ubt,dotnet,compiler)),
            tuple((str(p),identity(p)) for p in (self.editor,build_version,ubt,dotnet,compiler)))
        self.toolchain.sdk_root.mkdir()
        self.request = replace(source_fixture.request, unreal_executable_sha256=digest(self.editor),
            unreal_build_version_sha256=digest(build_version), toolchain_sha256=self.toolchain.identity_sha256)
        source_dir = root/'UNIT_PRIVATE_SOURCE'; source_dir.mkdir()
        for name in FILES:
            (source_dir/name).write_bytes(bytes(NORMAL_BYTES) if name=='source_corner_normals.bin' else
                b'UNIT_NOT_REAL_SOURCE:'+name.encode())
        (source_dir/'source_reference.json').write_bytes(canonical_bytes({'material_spec':self.binding['spec']}))
        (source_dir/'unreal_source_stage.json').write_bytes(canonical_bytes({'fbx_metadata':
            {'expected_unreal_material_slot_name':'UNIT_SLOT_NOT_REAL'}}))
        (source_dir/VERIFICATION_FILE).write_bytes(canonical_bytes({'UNIT_NOT_REAL_SOURCE_PROOF':True,
            'request_sha256':self.request.sha256}))
        self.prepared = PreparedUnrealSource(source_dir,tuple((name,digest(source_dir/name)) for name in FILES),
            digest(source_dir/VERIFICATION_FILE),'UNIT_STAGE_ID','UNIT_VERIFY_ID',self.request.sha256,source_dir)
        engine_work = root/'UNIT_PRIVATE_ENGINE_JOB'; engine_work.mkdir()
        project = engine_work/'portable-project'; project.mkdir()
        for name in DELIVERY_FILES:
            path = project/name;path.parent.mkdir(parents=True,exist_ok=True)
            if name=='DerivedSources/character.fbx':path.write_bytes((source_dir/'character.fbx').read_bytes())
            elif name=='Character.uproject':path.write_bytes(canonical_bytes({'FileVersion':3,
                'EngineAssociation':'5.9','Category':'UCC private static character',
                'DisableEnginePluginsByDefault':True,'Plugins':[]}))
            elif name=='Config/DefaultEngine.ini':path.write_bytes(b'UNIT_CONFIG_NOT_REAL_ENGINE')
            else:path.write_bytes(('UNIT_NOT_REAL_UNREAL_ASSET:'+name).encode())
        files = {name:digest(project/name) for name in DELIVERY_FILES}
        receipt = {'schema_version':1,'policy':'UCC_UNREAL_ENGINE_PREPARATION_V1',
            'request_sha256':self.request.sha256,'toolchain_identity_sha256':self.toolchain.identity_sha256,
            'files':files,'source_fbx_sha256':files['DerivedSources/character.fbx'],
            'admission':{'saved_reopened_bind_verified':True},
            **{name:name in ('engine_import_verified','source_parity_verified') for name in READINESS_FLAGS}}
        (engine_work/'engine-receipt.json').write_bytes(canonical_bytes(receipt))
        self.engine = PreparedUnrealEngine(project,tuple(sorted(files.items())),self.request.sha256,
            digest(engine_work/'engine-receipt.json'),engine_work,.000001,.1)
        self.destination = plan_destination(root/'output',self.store.root)
        self.options = dict(request=self.request,destination=self.destination,blender_exe=self.exe,
            worker_script=self.worker,mpfb_data_dir=self.data,unreal_exe=self.editor,toolchain=self.toolchain)

    def verify_final(self, project_directory, **options):
        # Verify the test seam receives the actual published ten-file project,
        # rather than a private intermediate. This is filesystem logic ONLY.
        directory = Path(project_directory)
        if directory != self.destination.path or not directory.is_dir():
            raise AssertionError('Final native seam must receive the actual destination')
        expected = options['expected_files']
        if set(expected) != DELIVERY_FILES | {'request.json','engine_recipe.json','README.txt'}:
            raise AssertionError('Final native seam did not bind the complete ten-file payload')
        if any(digest(directory/name)!=sha for name,sha in expected.items()):
            raise AssertionError('Final native seam payload changed')
        if options['engine_receipt_path'] != self.engine.workdir/'engine-receipt.json':
            raise AssertionError('Wrong private native admission receipt')
        if options['engine_receipt_sha256'] != self.engine.receipt_sha256:
            raise AssertionError('Native receipt SHA not bound')
        if options['source'] != self.prepared or options['request'] != self.request:
            raise AssertionError('Wrong original source/request')
        return {'request_sha256':self.request.sha256,'toolchain_identity_sha256':self.toolchain.identity_sha256,
            'payload_files':expected,'admission':{'saved_reopened_bind_verified':True},
            **{name:name in ('engine_import_verified','source_parity_verified') for name in READINESS_FLAGS}}

    def patches(self):
        prefix='ucc.jobs.unreal_export.'
        return {'sources':patch(prefix+'static_export_sources',return_value=(self.review,self.sources,self.binding)),
            'worker':patch(prefix+'worker_dependency_files',return_value={self.worker}),
            'resources':patch(prefix+'bundled_unreal_adapter_paths',return_value={'capture_common.py':self.resource}),
            'preflight':patch(prefix+'preflight_unreal_toolchain',return_value=self.toolchain),
            'source_stage':patch(prefix+'prepare_unreal_source',return_value=self.prepared),
            'engine_stage':patch(prefix+'prepare_unreal_engine',return_value=self.engine),
            'final_native':patch(prefix+'verify_unreal_published_project',side_effect=self.verify_final)}
