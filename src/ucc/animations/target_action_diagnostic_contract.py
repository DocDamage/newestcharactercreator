"""Engine-neutral immutable position measurements; no execution or quality grant."""
from dataclasses import asdict, dataclass, field

from ucc.core.errors import ValidationError
from ucc.core.target_action_format import checked_sha, checked_text

PROFILE = 'UCC_TARGET_ACTION_POSITION_DIAGNOSTIC_V1'
APPROVAL_FLAGS = (
    'engine_import_verified', 'runtime_execution_verified', 'retargeting_verified',
    'editing_authorized', 'usable_action_approved', 'visual_quality_approved',
    'loop_quality_approved', 'contact_quality_verified', 'gait_quality_verified',
    'rotation_quality_verified', 'distribution_license_review_complete',
    'source_redistribution_authorized', 'cloud_transmission_authorized',
    'ai_input_authorized',
)
Vec3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TargetActionDiagnosticSelection:
    project_id: str
    revision: int
    project_sha256: str
    master_sha256: str
    clip_id: str
    binding_sha256: str
    source_binding_sha256: str
    catalog_record_sha256: str

    def __post_init__(self):
        checked_text(self.project_id, 160)
        checked_text(self.clip_id, 138)
        if type(self.revision) is not int or not 0 <= self.revision <= 2**63 - 1:
            raise ValidationError('Diagnostic saved revision is invalid')
        for name in self.__dataclass_fields__:
            if name not in {'project_id', 'revision', 'clip_id'}:
                checked_sha(getattr(self, name))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object):
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ValidationError('Diagnostic selection has missing or unknown fields')
        return cls(**value)

    def loader_args(self) -> dict:
        return dict(binding_sha256=self.binding_sha256, expected_project_id=self.project_id,
            expected_revision=self.revision,
            expected_master_blend='master/versions/'+self.master_sha256+'.blend',
            expected_project_sha256=self.project_sha256, expected_clip_id=self.clip_id,
            expected_source_binding_sha256=self.source_binding_sha256,
            expected_catalog_record_sha256=self.catalog_record_sha256)


@dataclass(frozen=True, slots=True)
class JointPositionEndpoints:
    """Explicitly mapped, already verified WORLD position endpoints only."""
    name: str
    first_world: Vec3
    last_world: Vec3


@dataclass(frozen=True, slots=True)
class DiagnosticSamples:
    """Captured cache endpoints and verified timeline translations, never paths."""
    first_vertices: bytes
    last_vertices: bytes
    world_matrix: tuple[float, ...]
    root_world_heads: tuple[Vec3, ...]
    hip_midpoints_world: tuple[Vec3, ...]
    fps: float = 30.0
    source_first_frame: int = 2
    target_first_frame: int = 1
    mapped_joint_endpoints: tuple[JointPositionEndpoints, ...] = ()
    root_motion_policy: str = 'SOURCE_HIP_MIDPOINT_V1'
    cache_sha256: str = field(kw_only=True)
    timeline_sha256: str = field(kw_only=True)

    def __post_init__(self):
        checked_sha(self.cache_sha256)
        checked_sha(self.timeline_sha256)


@dataclass(frozen=True, slots=True)
class DiagnosticClock:
    source_first_frame: int
    source_last_frame: int
    target_first_frame: int
    target_last_frame: int
    frame_count: int
    fps: float
    elapsed_span_s: float
    nominal_duration_s: float
    playback_policy: str = 'ONCE_HOLD_LAST'


@dataclass(frozen=True, slots=True)
class TrajectoryMetrics:
    net_displacement_m: Vec3
    net_distance_m: float
    path_length_m: float
    max_step_m: float
    max_speed_m_s: float
    mean_speed_m_s: float


@dataclass(frozen=True, slots=True)
class EndpointMeshGap:
    vertex_count: int
    raw_rms_m: float
    raw_max_m: float
    hip_translation_only_rms_m: float
    hip_translation_only_max_m: float


@dataclass(frozen=True, slots=True)
class JointPositionGap:
    name: str
    raw_distance_m: float
    hip_translation_only_distance_m: float


@dataclass(frozen=True, slots=True)
class TargetActionDiagnostics:
    selection: TargetActionDiagnosticSelection
    clock: DiagnosticClock
    root_world_head: TrajectoryMetrics
    source_hip_midpoint: TrajectoryMetrics
    endpoint_mesh: EndpointMeshGap
    proof_hashes: tuple[tuple[str, str], ...]
    mapped_joint_gaps: tuple[JointPositionGap, ...] = ()

    @property
    def diagnostic_only(self) -> bool:
        return True

    @property
    def measurement_profile(self) -> str:
        return PROFILE

    @property
    def root_motion_policy(self) -> str:
        return 'SOURCE_HIP_MIDPOINT_V1'

    def to_dict(self) -> dict:
        """Small aggregates only: no mesh vertices, poses, paths or trajectories."""
        return {**asdict(self), 'schema_version': 1, 'measurement_profile': PROFILE,
            'root_motion_policy': self.root_motion_policy, 'proof_hashes': dict(self.proof_hashes),
            'diagnostic_only': True, 'coordinate_space': 'WORLD_METRES_Z_UP',
            'endpoint_rms_policy': 'RMS_PER_VERTEX_EUCLIDEAN_WORLD_METRES',
            'compensation_policy': 'LAST_MINUS_FIRST_SOURCE_HIP_TRANSLATION_ONLY',
            'mapped_joint_position_endpoints_available': bool(self.mapped_joint_gaps),
            'automatic_threshold_pass': False,
            **{name: False for name in APPROVAL_FLAGS}}
