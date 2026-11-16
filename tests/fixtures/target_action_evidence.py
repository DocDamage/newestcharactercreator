"""Nonshipping worker-metadata fixtures; never complete Action/cache admission."""
from dataclasses import replace
from copy import deepcopy
from hashlib import sha256
import json

from fixtures.target_action_contract import metadata_pair
from ucc.core.target_action import TargetActionFile
from ucc.jobs.neutral_master import HASHES, FALSE_FLAGS, POLICY
from ucc.jobs.protocol import JobRequest, JobResult


class ProofFiles:
    def __init__(self, directory):
        self.directory = directory.resolve()
        self.request, self.binding = metadata_pair()
        self.write('preparation_request.json', self.request.to_dict())

    def write(self, name, value):
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode()
        return self.bytes(name, payload)

    def bytes(self, name, payload):
        path = self.directory/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        record = TargetActionFile(name, sha256(payload).hexdigest(), len(payload))
        self.binding = replace(self.binding, files=tuple(
            record if item.name == name else item for item in self.binding.files))
        return path

    def neutral(self):
        b = self.binding
        return {'schema_version': 1, 'policy': POLICY, 'master_sha256': b.target.master_sha256,
            'blender_version': '5.3.0', 'mpfb_version': '2.0.18', 'bone_count': 163,
            'full_vertex_count': 19158, 'visible_vertex_count': 13380, 'inspected_datablocks': 90,
            'action_count': 0, 'driven_datablocks': 0, 'nla_tracks': 0, 'bone_constraints': 0,
            'exact_identity_pose_basis': True, 'expression_key_count': 12, 'source_state_preserved': True,
            **{name: 'b'*64 for name in HASHES}, **{name: False for name in FALSE_FLAGS},
            'state_sha256': b.target.neutral_state_sha256, 'rest_sha256': b.target.rest_sha256}

    def worker(self, prefix, job_id, operation, options, details, *, input_project='candidate.blend', neutral=False):
        request = JobRequest(job_id, operation, input_project, deepcopy(options)).as_dict()
        result = JobResult(job_id, operation, 'ok', details).as_dict()
        self.write(prefix + ('_request.json' if neutral else '/request.json'), request)
        self.write(prefix + ('_result.json' if neutral else '/result.json'), result)
        return request, result

    def neutral_pair(self):
        for label, job_id in zip(('first', 'second'), self.binding.producer.neutral_worker_job_ids):
            self.worker('neutral/'+label, job_id, 'inspect_mpfb_neutral_master',
                {'master_sha256': self.binding.target.master_sha256}, self.neutral(), neutral=True)
