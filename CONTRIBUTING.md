# Contributing and coding-agent handoff

- Read `AGENTS.md` and `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md` before any change.
- Use one narrow work item / task ID per branch and PR. Avoid monolithic rewrites.
- Run both standard-library test suites from the root README.
- Actual character generation, animation, exporter, Blender and engine claims require **observed application evidence**, not synthetic fixtures or green unit tests.
- Write decisions as ADRs when an integration choice changes; do not silently replace MPFB or the selected stack.
- Do not auto-download paid/unknown-license assets or send art to cloud services without explicit consent.
- Do not commit Fab source assets, local AI checkpoints, private model inventories, generated evidence, or purchased animations.
- Validate failure paths: timeouts, cancellation, broken geometry, missing Blender/MPFB, malformed manifests, unexpected skeletons and missing permission records.
- Until licensing is decided, do not add a speculative open-source license or package third-party tools.
