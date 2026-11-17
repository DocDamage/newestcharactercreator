"""Source-bound saved Godot preview loading; no engine or code execution."""
from pathlib import Path
from threading import Event
from typing import Callable
from ucc.core.errors import ProjectStorageError,ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import (RegisteredInputSelection,
    RegisteredRuntimeManifest,MAX_MANIFEST_BYTES,file_limit)
from ucc.export.godot_saved_preview import (SelectedProofFile,LoadedSavedGodotPreview)
from .godot_candidate_inputs import identity
from .godot_registered_runtime_admission import current_inputs,permission_bytes
from .godot_registered_runtime_storage import _load_directory
from .godot_registered_runtime_files import seal,check_seal_identities
from .target_action_context import operation_budget,protected
from .godot_saved_preview_files import ProofReads
from .godot_saved_preview_body import admit_body_proof
from .godot_saved_preview_draw import admit_draw_proof
from .godot_saved_preview_catalog import final_catalog_guard,coordination_paths


def _boundary(operation):
    try:return operation()
    except OSError as error:
        raise ProjectStorageError('Saved Godot preview IO failed: '+str(error)) from error
    except (KeyError,TypeError,ValueError,AttributeError,IndexError,OverflowError) as error:
        raise ValidationError('Malformed selected saved Godot preview evidence') from error


def load_saved_godot_preview(store:ProjectStore,*,selection:RegisteredInputSelection,
        draw_receipt:SelectedProofFile,body_receipt:SelectedProofFile,
        retained_manifest:SelectedProofFile,database_path:Path,
        permissions:tuple[EngineInputPermission,...],local_view_confirmed:bool,
        cancel:Event|None=None,timeout_s:float=300,
        progress:Callable[[str],None]|None=None) -> LoadedSavedGodotPreview:
    """Read explicitly selected proofs against the CURRENT desktop target binding.

    Historical code/executable identities are data. This loader never locates
    their installations, resolves adapter resources, constructs Prepared DTOs,
    writes a project/catalog, or invokes an engine/worker.
    """
    def operation():
        if (type(selection) is not RegisteredInputSelection or local_view_confirmed is not True
                or any(type(value) is not SelectedProofFile for value in (draw_receipt,body_receipt,retained_manifest))):
            raise ValidationError('Choose three typed saved proofs and explicitly confirm private local viewing')
        if len({value.path for value in (draw_receipt,body_receipt,retained_manifest)})!=3:
            raise ValidationError('Choose three distinct saved proof files')
        if retained_manifest.path.name!='manifest.json':
            raise ValidationError('Select the retained-input manifest.json explicitly')
        permission_bytes(permissions)
        database=protected(Path(database_path))
        with operation_budget(cancel,timeout_s) as budget:
            reads=ProofReads(budget)
            raw=reads.capture(retained_manifest.path,MAX_MANIFEST_BYTES,retained_manifest.sha256)
            manifest=RegisteredRuntimeManifest.from_bytes(raw)
            if manifest.sha256!=retained_manifest.sha256 or manifest.selection!=selection:
                raise ValidationError('Selected retained proof belongs to another current project/binding')
            if permission_bytes(manifest.permissions)!=permission_bytes(permissions):
                raise ValidationError('Caller permissions differ from the exact reviewed retained policies')
            if progress:progress('SAVED_GODOT_CURRENT_SOURCE_REVIEW')
            current=current_inputs(store,selection,database,permissions,budget,progress)
            retained=protected(retained_manifest.path.parent)
            retained_seal=seal(retained,manifest,budget)
            _load_directory(retained,manifest,current,permissions,budget,expected_seal=retained_seal)
            for row in manifest.files:
                reads.record(retained/row.name,file_limit(row.name),row.sha256)
                if reads.records[retained/row.name][2]!=row.bytes:
                    raise ValidationError('Selected retained payload length differs')
            check_seal_identities(retained,retained_seal,budget)
            if progress:progress('SAVED_GODOT_BODY_PROOF')
            body=admit_body_proof(reads,body_receipt,manifest,retained)
            if progress:progress('SAVED_GODOT_DRAW_PROOF')
            draw_id,frames=admit_draw_proof(reads,draw_receipt,body_receipt,body)
            # Capture current desktop proof bytes too; never use artifact selection
            # as authority for the active project or its explicitly chosen binding.
            source_hashes=dict(current.prepared_target.watched_inputs)
            source_hashes.update({path:current.source_hashes[name] for name,path in current.sources.items()})
            for path,digest in source_hashes.items():
                reads.record(path,512*1024*1024,digest)
            current.guard();reads.check();check_seal_identities(retained,retained_seal,budget)
            database_identity=identity(database)[:2];parent_identity=identity(database.parent)[:2]
            # No initial operation Budget is retained by this public background guard.
            def guard(*,cancel=None,timeout_s=300):
                def recheck():
                    with operation_budget(cancel,timeout_s) as fresh:
                        if (identity(protected(database))[:2]!=database_identity
                                or identity(protected(database.parent))[:2]!=parent_identity):
                            raise ProjectStorageError('Saved-preview catalog identity changed')
                        reads.check(fresh)
                        now=current_inputs(store,selection,database,permissions,fresh)
                        _load_directory(retained,manifest,now,permissions,fresh,expected_seal=retained_seal)
                        reads.check(fresh);check_seal_identities(retained,retained_seal,fresh)
                        final_catalog_guard(database,fresh,now.guard)
                        for path,stamp in reads.authority.items():
                            if identity(protected(path))!=stamp:
                                raise ProjectStorageError('Saved-preview proof changed after final logical guard')
                        check_seal_identities(retained,retained_seal,fresh)
                return _boundary(recheck)
            watched={path:identity(protected(path)) for path in reads.authority}
            for path,_ in current.prepared_target.watched_identities:
                watched[path]=identity(protected(path))
            coordination=coordination_paths(database)
            for path in coordination:
                protected(path);watched[path]=identity(path) if path.exists() else (0,0,0,0)
                watched[path.parent]=identity(protected(path.parent))
            paths=set(watched)|{path.parent for path in watched}
            watch_paths=tuple(sorted((path for path in paths if path.exists()),key=str))
            for path in watch_paths:protected(path)
            # Heavy proof hashing precedes the final logical rights check.
            # Its accepted catalog namespace is fenced, never resampled later.
            reads.check();check_seal_identities(retained,retained_seal,budget)
            coordinated=final_catalog_guard(database,budget,current.guard)
            watched.update(coordinated)
            for path,stamp in reads.authority.items():
                if identity(protected(path))!=stamp:
                    raise ProjectStorageError('Saved-preview proof changed after final logical guard')
            check_seal_identities(retained,retained_seal,budget)
            # Rebuild coordination watches ONLY from the fenced namespace:
            # empty WAL/SHM may have appeared or vanished during the RO check.
            # Missing coordination paths stay in stamps; their parent stays watched.
            watch_paths=tuple(sorted((set(watch_paths)-set(coordination))
                | {path for path,stamp in coordinated.items() if stamp!=(0,0,0,0)}
                | {database.parent},key=str))
            budget.check()
            return LoadedSavedGodotPreview(draw_id,selection,draw_receipt,body_receipt,retained_manifest,
                frames,database,watch_paths,tuple(sorted(watched.items(),key=lambda item:str(item[0]))),guard)
    return _boundary(operation)
