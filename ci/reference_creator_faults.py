"""Rehashed saved-result faults, confined to explicit disposable evidence copies."""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sqlite3

from ci.regional_sources import require, digest
from ci.source_reference_checks import clone
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.jobs.expression_storage import load_expression_library
from ucc.jobs.hand_storage import load_hand_library
from ucc.jobs.reference_expression_evidence import check_referenced_expression_preview, reference_expression_receipt
from ucc.library.provenance import AssetPolicyError


def copied_result(owner, original, root: Path):
    store = clone(owner, root/'owner')
    # The copy must describe the exact accepted owner revision, not a new clone revision.
    shutil.copyfile(owner.file, store.file)
    def rebased(path): return store.root/path.relative_to(owner.root)
    private_root = rebased(original.context.store.root)
    shutil.copytree(original.context.store.root, private_root)
    database = root/'catalog.sqlite3'
    with closing(sqlite3.connect(original.database_path.as_uri()+'?mode=ro', uri=True)) as src, closing(sqlite3.connect(database)) as dst:
        src.backup(dst)
    require(len(original.source_paths) == 1, 'Creator saved-fault fixture requires its one original source')
    source = root/'source.fbx'; shutil.copyfile(original.source_paths[0], source)
    with closing(sqlite3.connect(database)) as db:
        row = db.execute('UPDATE asset_sources SET source_path=? WHERE asset_id=?',
                         (str(source.resolve()), original.references[0]['asset_id']))
        require(row.rowcount == 1, 'Copied source registration is missing'); db.commit()
    private = ProjectStore(private_root); hand = original.context.old_hand
    context = replace(original.context, store=private,
        expression_library=load_expression_library(private, original.project.expression.library_sha256),
        old_hand=load_hand_library(private, hand.sha256) if hand else None,
        dependencies=tuple((rebased(p), sha) for p, sha in original.context.dependencies))
    preview = replace(deepcopy(original.preview), workdir=rebased(original.preview.workdir),
        verify_dir=rebased(original.preview.verify_dir), inspection=replace(original.preview.inspection,
            master=rebased(original.preview.inspection.master), report=rebased(original.preview.inspection.report)))
    receipt = preview.workdir/'reference_expression_preview.json'
    result = replace(original, context=context, preview=preview,
        private_evidence=tuple((rebased(p), sha) for p, sha in original.private_evidence),
        receipt_path=receipt, database_path=database.resolve(), source_paths=(source.resolve(),))
    receipt.write_text(json.dumps(reference_expression_receipt(result), sort_keys=True, separators=(',', ':')),
                       encoding='utf-8', newline='\n')
    result = replace(result, receipt_sha256=digest(receipt))
    check_referenced_expression_preview(store, database, result)
    return store, result, source


def saved_faults(owner, original, root: Path) -> dict:
    root.mkdir(exist_ok=False)
    protected = {str(p): digest(p) for p in owner.root.rglob('*') if p.is_file()}
    protected[str(original.source_paths[0])] = digest(original.source_paths[0])
    protected[str(original.database_path)] = digest(original.database_path)
    store, result, source = copied_result(owner, original, root); accepted = {}
    def rejected(name: str, changed) -> None:
        try: check_referenced_expression_preview(store, result.database_path, changed)
        except (ProjectStorageError, ValidationError, AssetPolicyError) as error:
            if name == 'preview_WAL_policy': require(isinstance(error, AssetPolicyError), 'WAL policy failed for an unrelated reason')
            accepted[name] = True
        else: raise RuntimeError('Coherently rehashed saved creator fault was accepted: '+name)
        print('ORIGINAL_CREATOR_SAVED_FAULT_REJECTED', name, flush=True)
    raw = source.read_bytes(); source.write_bytes(raw+b'changed disposable source')
    rejected('preview_changed_source', result); source.write_bytes(raw)
    check_referenced_expression_preview(store, result.database_path, result)
    receipt = result.receipt_path; raw = receipt.read_bytes(); payload = json.loads(raw); payload['unknown'] = True
    receipt.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
    rejected('preview_rehashed_receipt', replace(result, receipt_sha256=digest(receipt))); receipt.write_bytes(raw)
    check_referenced_expression_preview(store, result.database_path, result)
    binary = result.preview.workdir/'expression_skin.bin'; raw = binary.read_bytes()
    changed = bytearray(raw); changed[len(changed)//2] ^= 1; binary.write_bytes(changed)
    rejected('preview_damaged_skin_cache', result); binary.write_bytes(raw)
    check_referenced_expression_preview(store, result.database_path, result)
    changed = replace(result, preview=replace(result.preview, verify_dir=result.preview.workdir,
                                              reopen_job_id=result.preview.stage_job_id))
    raw = receipt.read_bytes()
    receipt.write_text(json.dumps(reference_expression_receipt(changed), sort_keys=True, separators=(',', ':')),
                       encoding='utf-8', newline='\n')
    rejected('preview_same_worker', replace(changed, receipt_sha256=digest(receipt))); receipt.write_bytes(raw)
    check_referenced_expression_preview(store, result.database_path, result)
    # Keep the writer open: the policy must be read from committed WAL, not an immutable DB shortcut.
    with closing(sqlite3.connect(result.database_path)) as writer:
        writer.execute('PRAGMA wal_autocheckpoint=0'); writer.execute('SELECT * FROM asset_sources').fetchall()
        before = digest(result.database_path); mtime = result.database_path.stat().st_mtime_ns
        asset = result.references[0]['asset_id']
        raw = writer.execute('SELECT license_json FROM asset_sources WHERE asset_id=?', (asset,)).fetchone()[0]
        policy = json.loads(raw); policy['no_ai'] = False
        writer.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?', (json.dumps(policy), asset)); writer.commit()
        require(digest(result.database_path) == before and result.database_path.stat().st_mtime_ns == mtime,
                'Live policy fault did not remain in WAL')
        rejected('preview_WAL_policy', result)
        writer.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?', (raw, asset)); writer.commit()
    check_referenced_expression_preview(store, result.database_path, result)
    require(all(digest(Path(p)) == sha for p, sha in protected.items()), 'Saved faults modified accepted original evidence')
    return accepted
