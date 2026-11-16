# Unity native-position geometric normals

This first-party runtime code corrects the admitted MPFB human's deformed
geometric normals while preserving Unity's actual skinned GPU position bytes.
No character, purchased asset or original Blender source is included here.
Distribution/license review remains open.

The current tested profile is Unity **6000.4.5f1**, Windows, **Direct3D 11**,
Built-in **Forward**, Linear color, unlimited skin weights and renderer quality
Auto. It covers one material with opaque Standard color/roughness, the exact
163-bone MPFB human family, twelve canonical expression shapes, original UVs and
an immutable native mesh identity. Scaled/sheared or negative root transforms,
normal/metallic texture maps and per-renderer property overrides produce errors.
Additional texturing profiles remain unverified. This is not a universal
skeleton or a generic model importer.

The saved `UccNativeNormals` component needs serialized references to the source
topology TextAsset, its SHA-256, the compute shader and the warmup shader. The
producer must validate `UnityQuadSource` and independently verify the imported
mesh against its actual Blender source before attaching those references.
`UccNativeMeshIdentity` binds positions, original normals/tangents, UVs,
triangles, every native influence, bind poses, bone/parent identities and shape
data. The runtime checks the identity rather than repairing the mesh.

During a visible Forward camera render, the native source renderer updates its
actual skin buffer through a colorless pass. An `AfterForwardOpaque` command
copies that current buffer into an owned mesh buffer, computes quad face and
angle-weighted vertex normals, then draws with the original Standard material.
The topology reverses handedness relative to native root coordinates, so the
computed normals are flipped once. Computing in root space avoids cancellation
from large world translations. Opaque depth is written before transparent draws.
There is no manual `Camera.Render`, CPU mesh baking, GPU readback or reference
source-pose buffer in the runtime update path.

The component owns its temporary material, mesh, GPU buffers and camera commands.
Disabling it releases those resources and restores source material/buffer flags
only while those fields still belong to the component. A failed initialization
records `LastError`, disables the component and restores its source state.
`IsInitialized` describes resources, not export or visual-quality approval.
The runtime also owns `forceMatrixRecalculationPerRender` while active and
restores its original value on cleanup. Unity does not serialize that property;
the saved Editor observation correctly records it as false before Play mode.

`Editor/UccUnityImport.cs` and `Editor/UccSourceWeights.cs` implement the explicit
import stage for a private, newly created export project. The stage binds the
source weight file to its hash, master and reviewed request; matches every native
vertex to the original source within 2 µm; retains every positive influence; and
creates an owned native mesh asset. This is a declared conversion after FBX
import. Existing output assets are rejected. The stage applies the reviewed
opaque material, coordinate correction, unlimited skin profiles and persists
the scene/prefab. Topology attachment validates the actual native fingerprint and
shader references before saving the runtime component. These mutation methods
must never be called by a fresh-reopen verifier. They are not yet exposed by a
complete application export transaction.

`Editor/UccUnityExportJobs.cs` exposes the fixed Stage / Attach / Reopen jobs.
`UccUnityObservation` reads actual native fields; the Python host independently
checks the original bind reference, reflected triangle winding/multiplicity,
exact corner UVs, every positive influence under the declared native storage
budget, facial deltas, bone identities/heads and reviewed material. The FBX
importer clamps its minimum bone weight to 0.001; the later explicit owned-mesh
conversion preserves the original influences independently of that filter.
`prepare_unity_engine` runs in exclusive private folders, guards reviewed inputs
and executable/resources, seals the saved input tree and checks a fresh copy
without repair. Its receipt explicitly leaves runtime verification and export
publication false. The package manifest now binds eleven first-party Unity
resources; this is source-payload validation, not frozen app acceptance.

`prepare_unity_runtime_source` captures actual original-master positions and
smooth geometric normals for 178 bone/facial diagnostics, then a fresh Blender
process recomputes every vector and manifest entry without rewriting outputs.
`verify_unity_runtime` supplies only pose instructions to an isolated graphical
Unity project. Editor-only observers read current native GPU position/normal
buffers through two automatic cameras; the host checks complete frame coverage,
exact position bytes, the original-source 50 µm / 0.5° caps, decoded renders and
cleanup. Expected deformed runtime vectors remain on the host. These tests do
not create shipping animation clips or publish an export. The observer is
excluded from player compilation with `UNITY_EDITOR`.

Fresh saved-scene reopens have exercised all 178 original-source pose/shape
diagnostics, translated/rotated placement, two automatic cameras and disable /
re-enable behavior. The detailed evidence is in
[the acceptance record](../../docs/acceptance/UCC-P1-UNITY-001.md).
Player builds, runtime cost, broader lighting/rendering features, actual imported
body-animation clips and the standalone creator's export transaction/UI still
need verification. Do not present these files as a completed export workflow.
