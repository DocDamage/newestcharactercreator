"""Read-only native admission of a sealed published static Unreal project."""
from pathlib import Path
import math
import time
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.models import safe_relative_path
from ucc.export.unreal_contract import UnrealExportRequest, READINESS_FLAGS
from .unreal_preparation import PreparedUnrealSource
from .unreal_toolchain import UnrealToolchain
from .unreal_engine import (DELIVERY_FILES, _tree, _write, _capture, _admit,
    _verification_project, CAPTURE_POLICY)
from .export_guards import bounded_paths, protected_file, cancel_context, failure_reason
from .godot_candidate_inputs import read_json
from .master_preview import _digest
from .skin_material_preparation import _BudgetCancel

PORTABLE_METADATA = frozenset({'request.json', 'engine_recipe.json', 'README.txt'})


def check_payload(directory: Path, expected_files: dict, cancel=None) -> None:
    if type(expected_files) is not dict or set(expected_files) != DELIVERY_FILES | PORTABLE_METADATA:
        raise ValidationError('Published Unreal project requires a closed portable payload manifest')
    actual = {}
    for path in bounded_paths(directory, cancel, maximum_entries=256,
            allowed_directories=frozenset({'Content', 'Content/UCC', 'Config', 'DerivedSources'})):
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            if name not in expected_files:
                raise ProjectStorageError('Published Unreal project contains an unlisted/private input')
            protected_file(path); actual[name] = _digest(path, cancel)
    if actual != expected_files:
        raise ProjectStorageError('Published Unreal project differs from its sealed payload')


def verify_unreal_published_project(project_directory: Path, *, source: PreparedUnrealSource,
        request: UnrealExportRequest, toolchain: UnrealToolchain, engine_receipt_path: Path,
        engine_receipt_sha256: str, expected_files: dict, cancel=None, timeout_s=1800,
        progress=None) -> dict:
    if (type(source) is not PreparedUnrealSource or type(request) is not UnrealExportRequest
            or type(toolchain) is not UnrealToolchain or source.request_sha256 != request.sha256
            or request.toolchain_sha256 != toolchain.identity_sha256
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600):
        raise ValidationError('Published Unreal verification needs matching sealed source, request and toolchain')
    deadline, _ = cancel_context(cancel, time.monotonic()+timeout_s); budget = _BudgetCancel(cancel, deadline)
    directory = Path(project_directory); receipt_path = Path(engine_receipt_path)
    protected_file(receipt_path)
    if _digest(receipt_path, budget) != engine_receipt_sha256:
        raise ProjectStorageError('Unreal engine admission receipt changed before published verification')
    receipt = read_json(receipt_path, 4*1024*1024)
    if (receipt.get('policy') != 'UCC_UNREAL_ENGINE_PREPARATION_V1'
            or receipt.get('request_sha256') != request.sha256
            or receipt.get('toolchain_identity_sha256') != toolchain.identity_sha256
            or receipt.get('engine_import_verified') is not True
            or receipt.get('source_parity_verified') is not True):
        raise ValidationError('Published Unreal verification requires admitted matching static engine evidence')
    # Only source-controlled resource locations inside the retained private engine job are trusted.
    private = receipt_path.parent
    def sealed(name, sha_name):
        path = Path(receipt[name]); protected_file(path)
        if not path.is_relative_to(private) or _digest(path, budget) != receipt[sha_name]:
            raise ProjectStorageError('Unreal retained engine evidence changed or escaped its job')
        return path
    stage_receipt = sealed('stage_receipt_path', 'stage_receipt_sha256')
    profile = sealed('engine_profile_path', 'engine_profile_sha256')
    descriptor = sealed('source_descriptor_path', 'source_descriptor_sha256')
    proofs = {receipt_path: engine_receipt_sha256, stage_receipt: receipt['stage_receipt_sha256'],
        profile: receipt['engine_profile_sha256'], descriptor: receipt['source_descriptor_sha256']}
    stage_body = read_json(stage_receipt, 2*1024*1024)
    stage_native = stage_receipt.parent/'native-observation.json'
    protected_file(stage_native)
    if _digest(stage_native, budget) != stage_body['native_observation_sha256']:
        raise ProjectStorageError('Retained Unreal stage native observation changed')
    proofs[stage_native] = stage_body['native_observation_sha256']
    source_proof = source.directory/'unreal_source_verification.json'
    protected_file(source_proof)
    if _digest(source_proof, budget) != source.verification_sha256:
        raise ProjectStorageError('Unreal original source verification proof changed')
    proofs[source_proof] = source.verification_sha256
    source_hashes = dict(source.files)
    for name, digest in source_hashes.items():
        protected_file(source.directory/name)
        if _digest(source.directory/name, budget) != digest:
            raise ProjectStorageError('Original Unreal prepared source changed')
    if source_hashes['character.fbx'] != receipt['source_fbx_sha256']:
        raise ValidationError('Published Unreal source FBX differs from engine admission')
    toolchain.require_unchanged(budget); check_payload(directory, expected_files, budget)
    for name in DELIVERY_FILES:
        if expected_files[name] != receipt['files'][name]:
            raise ProjectStorageError('Published Unreal engine inputs differ from admitted portable bytes')
    work = private/('published-'+str(uuid4())); work.mkdir(exist_ok=False)
    try:
        plugin_files = {}
        for name, binding in receipt['observer_files'].items():
            safe_relative_path(name, 'Unreal observer input')
            path = Path(binding['path']); protected_file(path)
            if not path.is_relative_to(private) or _digest(path, budget) != binding['sha256']:
                raise ProjectStorageError('Unreal retained observer input changed or escaped its job')
            plugin_files[name] = (path, binding['sha256'])
            proofs[path] = binding['sha256']
        scripts = Path(receipt['scripts_directory'])
        if not scripts.is_relative_to(private):
            raise ProjectStorageError('Unreal verification scripts escaped their private engine job')
        script_before = _tree(scripts, budget)
        if set(script_before) != {'capture_common.py', 'stage.py', 'reopen.py'}:
            raise ProjectStorageError('Unreal verification script closure is incomplete')
        # Bind the retained scripts back to the validated first-party bundle.
        from .worker_resources import bundled_unreal_adapter_paths
        adapters = bundled_unreal_adapter_paths()
        if any(script_before[name] != _digest(adapters[name], budget) for name in script_before):
            raise ProjectStorageError('Unreal retained verifier script differs from bundled code')
        proofs.update({scripts/name: digest for name, digest in script_before.items()})
        project = work/'project'
        _verification_project(project, {name: expected_files[name] for name in DELIVERY_FILES},
            {'portable_root': directory}, plugin_files, budget, scripts)
        if progress: progress('PUBLISHED_UNREAL_VERIFICATION')
        spec = SkinMaterialSpec.from_dict(read_json(source.directory/'source_reference.json', 64*1024*1024)['material_spec'])
        fresh = work/'reopened'
        _capture(project, fresh, 'FRESH', request=request, toolchain=toolchain, profile_path=profile,
            descriptor=descriptor, material_spec=spec, stage_receipt=stage_receipt,
            scripts=scripts, budget=budget, deadline=deadline)
        admission = _admit(source, stage_receipt.parent, fresh, request, toolchain, spec, budget, deadline)
        toolchain.require_unchanged(budget); check_payload(directory, expected_files, budget)
        if _digest(receipt_path, budget) != engine_receipt_sha256 or script_before != _tree(scripts, budget):
            raise ProjectStorageError('Unreal retained engine evidence changed during published verification')
        for path, digest in proofs.items():
            protected_file(path)
            if _digest(path, budget) != digest:
                raise ProjectStorageError('Unreal retained proof or observer changed during published verification')
        for name, digest in source_hashes.items():
            if _digest(source.directory/name, budget) != digest:
                raise ProjectStorageError('Original source changed during published Unreal verification')
        result = {'schema_version': 1, 'policy': 'UCC_UNREAL_PUBLISHED_STATIC_VERIFICATION_V1',
            'request_sha256': request.sha256, 'toolchain_identity_sha256': toolchain.identity_sha256,
            'engine_receipt_sha256': engine_receipt_sha256, 'payload_files': expected_files,
            'reopened_receipt_sha256': _digest(fresh/'capture-receipt.json', budget),
            'admission': admission.to_dict(), 'workdir': str(work),
            **{name: name in ('engine_import_verified', 'source_parity_verified') for name in READINESS_FLAGS}}
        _write(work/'published-verification.json', result)
        return result
    except BaseException as error:
        error.add_note('Unreal published verification work retained at '+str(work))
        raise
