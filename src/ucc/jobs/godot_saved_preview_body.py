"""Read-only portable C proof admission against current retained source metadata."""
from dataclasses import dataclass
from pathlib import Path
import math
from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_body_runtime import (RegisteredRuntimeExecutionSelection,
    FALSE_FLAGS,POLICY,PROFILE)
from ucc.export.godot_runtime_contract import FILES,CODE_FILES
from .godot_registered_body_references import verify_body_outputs,verify_import_configuration
from .godot_saved_preview_files import ProofReads
from .godot_saved_preview_streams import capture_body_streams,NAMES


@dataclass(frozen=True,slots=True)
class BodyPreviewProof:
    directory:Path
    receipt:dict
    execution:RegisteredRuntimeExecutionSelection
    frames:dict


def _commands(reads:ProofReads,work:Path,rows,project_sha:str) -> None:
    phases=('initial-import','configure-import','configured-import','actual-body300')
    tails=(['--rendering-method','mobile','--rendering-driver','vulkan','--position','-32000,-32000','--editor','--import'],
           ['--headless','--script','res://configure.gd'],
           ['--rendering-method','mobile','--rendering-driver','vulkan','--position','-32000,-32000','--editor','--import'],
           ['--rendering-method','mobile','--rendering-driver','vulkan','--position','-32000,-32000','--script','res://validate.gd'])
    if type(rows) is not list or len(rows)!=4:raise ValidationError('Incomplete saved C command sequence')
    prefix=None;transitions=[]
    for index,(row,phase,tail) in enumerate(zip(rows,phases,tails)):
        keys={'phase','command','return_code','cancelled','timed_out','elapsed_seconds'}
        if index in (0,2):keys.add('generated_project_transition')
        if (type(row) is not dict or set(row)!=keys or row['phase']!=phase
                or type(row['return_code']) is not int or row['return_code']!=0
                or row['cancelled'] is not False or row['timed_out'] is not False
                or type(row['elapsed_seconds']) not in (int,float) or not math.isfinite(row['elapsed_seconds'])
                or row['elapsed_seconds']<0 or type(row['command']) is not list
                or any(type(v) is not str or not 0<len(v)<=4096 for v in row['command'])
                or len(row['command'])!=3+len(tail) or row['command'][1]!='--path'
                or row['command'][3:]!=tail or not Path(row['command'][0]).is_absolute()
                or not Path(row['command'][2]).is_absolute()):
            raise ValidationError('Unsupported historical C phase evidence')
        if prefix is None:prefix=row['command'][:3]
        if row['command'][:3]!=prefix:raise ValidationError('Historical C command context changed')
        if reads.metadata(work/phase/'outcome.json',256*1024)!=row:
            raise ValidationError('Saved C final phase outcome differs from receipt')
        actual=dict(row);transition=actual.pop('generated_project_transition',None)
        if reads.metadata(work/phase/'process_outcome.json',256*1024)!=actual:
            raise ValidationError('Saved C raw phase outcome differs from receipt')
        for name in ('stdout.log','stderr.log'):reads.record(work/phase/name,16*1024*1024)
        if index in (0,2):
            if (type(transition) is not dict or set(transition)!={'phase','policy','previous_identity','new_identity','sha256','bytes'}
                    or transition['phase']!=phase or transition['policy']!='OWNED_EDITOR_IDENTICAL_PROJECT_CONFIGURATION_V1'
                    or transition['sha256']!=project_sha or type(transition['bytes']) is not int or transition['bytes']!=419
                    or any(type(transition[k]) is not list or len(transition[k])!=4
                           or any(type(v) is not int for v in transition[k]) or transition[k][2]!=419
                           for k in ('previous_identity','new_identity'))):
                raise ValidationError('Saved C owned editor transition changed')
            transitions.append(transition)
    if transitions[1]['previous_identity']!=transitions[0]['new_identity']:
        raise ValidationError('Saved C editor transition continuity changed')


def admit_body_proof(reads:ProofReads,selected,manifest,retained:Path) -> BodyPreviewProof:
    if selected.path.name!='diagnostic_receipt.json':raise ValidationError('Select the saved C diagnostic receipt')
    work=selected.path.parent;folder=work/'engine'
    receipt=reads.metadata(selected.path,4*1024*1024,selected.sha256)
    keys={'schema_version','policy','profile','execution_sha256','retention_manifest_sha256',
          'source_receipt_sha256','target_action_binding_sha256','spec_sha256','commands','files','observed'}|FALSE_FLAGS
    if (set(receipt)!=keys or type(receipt['schema_version']) is not int or receipt['schema_version']!=1
            or receipt['policy']!=POLICY or receipt['profile']!=PROFILE
            or receipt['retention_manifest_sha256']!=manifest.sha256
            or receipt['source_receipt_sha256']!=manifest.source_receipt_sha256
            or receipt['target_action_binding_sha256']!=manifest.selection.binding_sha256
            or any(receipt[k] is not False for k in FALSE_FLAGS)
            or canonical_bytes(receipt)!=reads.capture(selected.path,4*1024*1024,selected.sha256)):
        raise ValidationError('Saved C receipt does not bind current retained source/context')
    execution=RegisteredRuntimeExecutionSelection.from_bytes(reads.capture(folder/'execution.json',256*1024,receipt['execution_sha256']))
    if execution.retention_manifest_sha256!=manifest.sha256:
        raise ValidationError('Historical C execution belongs to another retained candidate')
    records={row.name:row for row in manifest.files}
    if any(row.sha256!=records[row.name].sha256 or row.bytes!=records[row.name].bytes for row in execution.code):
        raise ValidationError('Historical code identities differ from retained data')
    if execution.provenance_sha256!=records['runtime_code_provenance.json'].sha256:
        raise ValidationError('Historical code provenance identity changed')
    spec=reads.metadata(folder/'spec.json',256*1024,receipt['spec_sha256'])
    expected={'schema_version','policy','profile','vertices','corners','frames','fps','execution_sha256',
              'retention_manifest_sha256','target_action_binding_sha256','source_receipt_sha256','plan_sha256','files'}
    names=set(FILES)|{'runtime_request.json','source_receipt.json','project.godot','configure.gd','validate.gd',
                      'execution.json','expected_vec4.f32','expected_normals_vec4.f32'}
    if (set(spec)!=expected or type(spec['schema_version']) is not int or spec['schema_version']!=1
            or spec['policy']!=POLICY or spec['profile']!=PROFILE or type(spec['files']) is not dict
            or set(spec['files'])!=names or spec['execution_sha256']!=execution.sha256
            or spec['retention_manifest_sha256']!=manifest.sha256
            or spec['source_receipt_sha256']!=manifest.source_receipt_sha256
            or spec['target_action_binding_sha256']!=manifest.selection.binding_sha256
            or spec['plan_sha256']!=records['skin_plan.json'].sha256
            or any(type(spec[k]) is not int or spec[k]!=v for k,v in [('vertices',13380),('corners',53512),('frames',300),('fps',30)])):
        raise ValidationError('Closed saved C specification/source lineage changed')
    for name,digest in spec['files'].items():
        reads.record(folder/name,512*1024*1024 if name not in {'configure.gd','validate.gd','project.godot','execution.json'} else 256*1024,digest)
        if name in records and digest!=records[name].sha256:
            raise ValidationError('Saved C input does not match selected retained bytes')
    project=reads.capture(folder/'project.godot',419,spec['files']['project.godot'])
    if len(project)!=419 or b'\r' in project:raise ValidationError('Saved C configuration is not exact LF419')
    _commands(reads,work,receipt['commands'],spec['files']['project.godot'])
    native_stage=reads.metadata(retained/'native_stage.json',4*1024*1024,records['native_stage.json'].sha256)
    for name in NAMES:
        expected_sha=spec['files'][name] if name in spec['files'] else receipt['files'].get(name,{}).get('sha256')
        reads.record(folder/name,300*13380*16,expected_sha)
    captured,readback=capture_body_streams(folder,
        {name:spec['files'][name] if name in spec['files'] else receipt['files'][name]['sha256'] for name in NAMES},
        native_stage['files'],reads.budget)
    observed=verify_body_outputs(folder,execution.sha256,receipt['spec_sha256'],reads.budget,input_hashes=spec['files'])
    if observed!=receipt['observed'] or observed['readback']!=readback:
        raise ValidationError('Independent captured C comparison differs from saved receipt')
    config=verify_import_configuration(folder,'POST_REIMPORT',reads.budget)
    outputs=observed['output_files']|{
        'measurement.json':dict(sha256=observed['measurement_sha256'],bytes=(folder/'measurement.json').stat().st_size),
        'import_configuration.json':dict(sha256=config['report_sha256'],bytes=(folder/'import_configuration.json').stat().st_size),
        'character.glb.import':dict(sha256=config['import_settings_sha256'],bytes=(folder/'character.glb.import').stat().st_size)}
    if receipt['files']!=outputs:raise ValidationError('Saved C output closure differs')
    for name,row in outputs.items():
        if type(row['bytes']) is not int or row['bytes']<1:raise ValidationError('Invalid saved C output length')
        reads.record(folder/name,row['bytes'],row['sha256'])
        if reads.records[folder/name][2]!=row['bytes']:raise ValidationError('Saved C output length changed')
    reads.check()
    return BodyPreviewProof(folder,receipt,execution,captured)
