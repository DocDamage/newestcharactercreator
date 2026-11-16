"""Synthetic byte/header transaction fixture; NEVER Blender/Godot evidence."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import FILES, EngineInputPermission, GodotCandidateRequest
from ucc.library.provenance import LicensePolicy


class GodotTransactionFixture:
    def __init__(self, root: Path):
        self.root = root
        self.store = ProjectStore(root/'unit-project')
        master_bytes = b'BLENDER'+b'NOT_REAL_MODEL_UNIT_ONLY'*100
        master_sha = sha256(master_bytes).hexdigest()
        self.master = self.store.root/'master'/'versions'/(master_sha+'.blend')
        self.master.parent.mkdir(parents=True); self.master.write_bytes(master_bytes)
        project = self.store.save(replace(CharacterProject.new('Synthetic transaction only'),
            master_blend='master/versions/'+master_sha+'.blend', geometry_state='generated_unverified'))
        self.folder = root/'unit-candidate'; self.folder.mkdir()
        for name in FILES:
            (self.folder/name).write_bytes(('UNIT_BYTES_NOT_ENGINE_DATA:'+name).encode())
        self.motion = self.folder/'unit-motion.blend'
        self.motion.write_bytes(b'NOT_A_BLENDER_ACTION_UNIT_ONLY')
        self.exe = root/'never-executed.exe'; self.exe.write_bytes(b'UNIT_PROCESS_DOUBLE')
        self.scripts = Path(__file__).resolve().parents[2]/'engine_adapters'/'godot'
        self.policy = LicensePolicy('unit-only', 'Synthetic policy, no asset license claim', 'unit-test://transaction',
                                    reviewed=True, no_ai=True, can_use_non_unreal=True)
        sources = {'master': self.master, 'motion:unit': self.motion}
        digest = lambda path: sha256(path.read_bytes()).hexdigest()
        self.request = GodotCandidateRequest(str(uuid4()), project.project_id, project.revision,
            digest(self.store.file), master_sha, tuple((name, digest(self.folder/name)) for name in sorted(FILES)),
            tuple(EngineInputPermission(name, digest(path), self.policy, source_only=False) for name, path in sources.items()),
            tuple((name, digest(path)) for name, path in sources.items()))
        self.original_metadata = self.store.file.read_bytes()
        self.original_master = self.master.read_bytes()
        self.prior = self.store.root/'.ucc-candidates'/'godot'/'unit-previous-candidate'
        self.prior.mkdir(parents=True)
        (self.prior/'unit-marker').write_bytes(b'PREVIOUS_UNIT_CANDIDATE_NO_ENGINE_CLAIM')

    def kwargs(self) -> dict:
        return {'candidate_folder': self.folder, 'motion_sources': {'motion:unit': self.motion},
                'godot_exe': self.exe, 'adapter_directory': self.scripts}


def unit_bind_profile() -> dict:
    """Metadata-only profile fixture, not an observed model or source mesh."""
    return {'source_modifiers': [
        {'name': 'Unit armature', 'type': 'ARMATURE', 'rig_object': 'UNIT_ONLY',
         'use_vertex_groups': True, 'use_bone_envelopes': False,
         'use_deform_preserve_volume': False, 'use_multi_modifier': False,
         'show_viewport': True, 'show_render': True},
        {'name': 'Unit mask', 'type': 'MASK', 'mode': 'VERTEX_GROUP', 'vertex_group': 'unit-body',
         'invert_vertex_group': False, 'threshold': 0., 'use_smooth': False,
         'show_viewport': True, 'show_render': True, 'source_mesh_vertices': 19158,
         'vertex_group_sha256': 'a'*64}],
        'static_masks_baked': True, 'body_and_hand_targets_baked': True}
