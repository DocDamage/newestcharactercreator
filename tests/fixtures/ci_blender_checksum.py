"""INVENTED non-shipping checksum bytes for receipt-parser unit tests only.

These repeated-character digests are not official Blender hashes or cache pins.
"""
SYNTHETIC_SHA = "a" * 64
SYNTHETIC_HEAD = "b" * 40
SYNTHETIC_MANIFEST = (
    SYNTHETIC_SHA + "  blender-5.3.0-linux-x64.tar.xz\n"
    + "c" * 64 + "  blender-5.3.0-windows-x64.zip\n"
).encode("ascii")
