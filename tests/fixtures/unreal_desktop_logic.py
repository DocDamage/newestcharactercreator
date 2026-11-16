"""NONSHIPPING synthetic receipt metadata; never Blender, Unreal or asset evidence."""
from hashlib import sha256
import json


def receipt_result(destination, review):
    from ucc.jobs.unreal_export import UnrealExport
    destination.mkdir()
    record = {
        'UNIT_ONLY_NOT_REAL_ENGINE_EVIDENCE': True,
        'schema_version': 1, 'policy': 'UCC_UNREAL_EXPORT_TRANSACTION_V1',
        'engine_import_verified': True, 'source_parity_verified': True,
        'shader_compilation_verified': False, 'runtime_gpu_verified': False,
        'pie_verified': False, 'player_build_verified': False,
        'cloud_transmission_authorized': False, 'project_metadata_changed': False,
        'maximum_source_position_error_m': 0., 'maximum_normal_angle_deg': 0.,
        'request_sha256': 'd'*64,
        'master_sha256': dict((s.asset_id, s.sha256) for s in review.sources)['master'],
        'export_published': True, 'final_payload_verified': True,
        'private_static_native_verified': True, 'animation_clips_verified': False,
        'visual_quality_approved': False, 'distribution_license_review_complete': False,
    }
    content = json.dumps(record).encode('utf-8')
    (destination/'export_receipt.json').write_bytes(content)
    return UnrealExport(destination, record['request_sha256'], sha256(content).hexdigest(),
                       record['master_sha256'], destination.parent/'UNIT_WORK', 0., 0.)
