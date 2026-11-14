"""Bounded private worker receipts; require the expected job and operation."""
from pathlib import Path

from ucc.core.errors import ValidationError
from .master_preview import _digest
from .native_fit_evidence import read_json_record
from .protocol import JobResult


def cached_job_details(jobs: Path,folder: Path,operation: str,*,cancel=None,cancel_check=lambda:None) -> dict:
    if jobs.is_symlink() or folder.is_symlink() or folder.resolve().parent!=jobs.resolve():
        raise ValidationError('Private cache verification folder is redirected')
    result_file=folder/'result.json'
    if result_file.is_symlink() or not result_file.is_file():raise ValidationError('Missing private cache verification receipt')
    data,_=read_json_record(folder,{'name':result_file.name,'bytes':result_file.stat().st_size,'sha256':_digest(result_file,cancel)},
        result_file.name,4*1024*1024,cancel_check=cancel_check)
    result=JobResult.from_dict(data)
    if result.status!='ok' or result.operation!=operation or result.job_id!=folder.name:
        raise ValidationError('Private cache verification receipt identity differs')
    return result.details
