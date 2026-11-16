"""NONSHIPPING synthetic receipt metadata; never Blender, Unity or asset evidence."""
from hashlib import sha256
import json
from ucc.jobs.unity_export import UnityExport


def receipt_result(destination, review):
    destination.mkdir()
    record = {
        'UNIT_ONLY_NOT_REAL_ENGINE_EVIDENCE': True,
        'request_sha256': 'd'*64,
        'master_sha256': dict((s.asset_id, s.sha256) for s in review.sources)['master'],
        'export_published': True, 'final_payload_verified': True,
        'private_runtime_diagnostics_verified': True, 'animation_clips_verified': False,
        'visual_quality_approved': False, 'distribution_license_review_complete': False,
    }
    content = json.dumps(record).encode('utf-8')
    (destination/'export_receipt.json').write_bytes(content)
    return UnityExport(destination, record['request_sha256'], sha256(content).hexdigest(),
                       record['master_sha256'], destination.parent/'UNIT_WORK', 0., 0.)
