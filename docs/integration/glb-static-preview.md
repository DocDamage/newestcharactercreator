# Read-only GLB 3D triangle viewer — software rendering, no Blender required

This increment adds an **actual local 3D surface preview** of an existing user-selected `.glb` (glTF 2.0 binary) model. The window reads vertex positions, triangle indices, selected scene/node transforms and draws a bounded sample of real triangle surfaces using Qt's CPU-based `QPainter`. It is an inspection tool, **not** a skeletal 3D character editor or an import quality certificate.

## Access

In the UCC desktop application, choose **View → Preview local GLB model...** and select your existing GLB. A dock opens with the sampled geometry and mesh metadata. Rotate with the left mouse button, pan with the right mouse button, zoom with the scroll wheel, and use **Reset** to recenter the view. Source files are never modified or uploaded.

## Explicitly supported

- glTF 2.0 GLB with one bounded **embedded BIN** chunk, float32 `POSITION` attributes, unsigned 8/16/32-bit scalar triangle indices, or non-indexed triangle lists.
- Mesh instancing, scene-root selection, nested node matrix or translation/rotation/scale transforms. Only glTF `TRIANGLES` primitives are drawn.
- Bounded preview: 128 MiB source, up to 250,000 positions and 1,500,000 indices per primitive, and **at most 2,000 drawn triangles** per selected GLB. Sampling remains deterministic and is reported visibly, never silently treated as the whole model.
- Source-checks through the existing offline GLB inspector, controlled buffer-view offsets/strides, finite values, triangle index bounds and scene graph safety.

## Not supported (deliberate)

No PBR materials, textures, normal maps, morph target evaluation, skinning, animations, collision, scene lights, IK, user geometry edits, general FBX / `.blend` import, network texture loading, image-based AI geometry creation or target-engine export. The preview depicts **static vertex geometry**, so rigged characters may be shown in their **bind/rest pose** only. Pre-existing skin/animation metadata is shown as a warning, not played.

This viewer is **CPU software rendered**. It proves the project can load and interactively view real selected geometry before MPFB validation, but does not replace the eventually planned hardware-accelerated character editor. Extremely large meshes are sampled for UI responsiveness.

## Preview an existing UCC Blender master

On supported builds, the Character tab also offers **Preview saved master in UCC...**. This explicitly runs the user's installed Blender through the versioned worker to create a private static GLB from the project's saved, immutable `.blend`. The same bounded reader and CPU viewer draw its real exported triangles. This **does not** change the authoritative Blender file or certify animation/engine export. See [saved-master preview integration](saved-master-preview.md) and its real Blender CI evidence.

## Verification

Synthetic GLB fixtures are used only inside unit tests to verify buffer math, node rotations/transforms, bounds, indices, symlink rejection, unexpected formats and triangle sampling. GitHub's dedicated offscreen PySide6 workflow also instantiates the actual viewer, renders through Qt into an image, and checks docking/reset behavior on Windows/Linux. These checks are **not** a real game-engine import or evidence of MPFB working on Windows.
