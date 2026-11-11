# GLB offline structural inspection — **not engine validation**

`ucc inspect-glb "path/to/file.glb"` uses only Python's standard library. It reads a bounded glTF 2.0 binary container, verifies chunk framing and JSON relationships, and reports meshes, primitives, skin joints, skinned nodes, animation clips, morph targets and material counts. It detects missing skin attributes, invalid object indices, out-of-range buffers and node cycles.

This can catch bad exports **before** attempting Godot, Unity or Unreal imports. It deliberately reports:

```json
{ "status": "OFFLINE_STRUCTURE_CHECKED", "engine_validated": false }
```

This report does *not* prove that mesh vertices actually deform, that bone rest poses are correct, that textures render or that an engine will accept the asset. A real master character and its animation must be imported and played in each requested engine. See `Development_Guardrails/docs/EXPORT_TEST_MATRIX.md` and issue #8.

The parser does not load or download external image/buffer URI references, does not run scripts or execute Blender, and rejects malformed containers. Test fixtures synthesize glTF structure only to test inspection errors; they are not shipped as ready-made character meshes.
