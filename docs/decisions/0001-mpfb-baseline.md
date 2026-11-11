# ADR 0001 — Use MPFB as the first humanoid foundation

**Status:** Provisional until real Blender 5.3 verification.

**Decision:** Use MPFB inside the user's Blender installation as the initial human generator, invoked via a versioned, isolated worker. Keep the core character project model and export adapters independent of MPFB internals so later families (quadrupeds, dragons, mechanical characters) can use different bases and rigs.

**Why:** Reuse standardized parametric humanoid work rather than asking AI to create a clean topology and rig for every new character.

**First acceptance gate:** The actual MPFB installation must create a real human in Blender 5.3, write an editable `.blend`, reopen it in a separate process, and record real mesh/rig evidence. Capture installed versions and failures. Headless incompatibility should trigger evaluation of documented interactive Blender integration—not fake substitute geometry.

**Risks:** Blender/MPFB API drift, headless context requirements, extension distribution license, mesh attachment compatibility, rig retargeting, and multiple engine-specific export conventions.

**Next:** `UCC-P0-001` evidence captured locally and reviewed.
