"""Finite private idle evidence serialization, distinct from 256 KiB intent."""
from hashlib import sha256
import json
from ucc.core.errors import ValidationError

MAX_EVIDENCE_BYTES = 16*1024*1024


def private_bytes(value, maximum=MAX_EVIDENCE_BYTES):
    result = bytearray()
    try:
        encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        for piece in encoder.iterencode(value):
            result.extend(piece.encode('utf-8'))
            if len(result) > maximum:
                raise ValidationError('Private idle evidence exceeds its finite byte limit')
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ValidationError('Invalid private idle JSON evidence') from error
    return bytes(result)


def private_sha(value):
    return sha256(private_bytes(value)).hexdigest()
