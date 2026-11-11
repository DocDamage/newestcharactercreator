"""MPFB's documented HumanService route for headless humanoid creation.

This pure-Python adapter contains no :mod:`bpy` import. Blender supplies its
installed MPFB service and bpy instance at runtime; the unit tests supply
minimal mocks. Neither a mock nor syntactically correct script proves that
MPFB works in a specific Blender installation.

References:
https://github.com/makehumancommunity/mpfb2/blob/master/script_samples/03_adding_a_default_rig.py
https://github.com/makehumancommunity/mpfb2/blob/master/docs/services/humanservice.md
"""
from __future__ import annotations

import importlib
import sys
from typing import Any, Callable, Mapping

from blender_bridge.morphs import build_macro_info, inspect_applied_macro


class MpfbServiceError(RuntimeError):
    """MPFB service is absent, ambiguous, or returned an invalid character."""


# These are explicitly documented rig choices with bundled definitions.
# Do not expose Rigify generation without separately verifying the rigify API.
BUILTIN_RIGS = frozenset({"default", "default_no_toes", "game_engine", "mixamo", "mixamo_unity"})


def _module_names(registry: Mapping[str, Any]) -> list[str]:
    """Locate only already-loaded Blender extension packages, never arbitrary paths."""
    return sorted(name for name in registry if name == "mpfb" or name.endswith(".mpfb"))


def locate_human_service(
    registry: Mapping[str, Any] | None = None,
    loader: Callable[[str], Any] | None = None,
) -> tuple[Any, str]:
    """Resolve MPFB HumanService using MPFB's own dynamic-import convention.

    The extension is *not* installed or enabled here. Blender must load it
    through its ordinary extension mechanism. Ambiguous installations are
    rejected instead of picking one without provenance.
    """
    modules = sys.modules if registry is None else registry
    importer = importlib.import_module if loader is None else loader
    service_names = sorted(name for name in modules
                           if name == "mpfb.services.humanservice"
                           or name.endswith(".mpfb.services.humanservice"))
    if not service_names:
        packages = _module_names(modules)
        if len(packages) != 1:
            raise MpfbServiceError(
                "Expected exactly one enabled MPFB extension package in Blender; "
                f"found {len(packages)}. Enable MPFB in Blender Preferences and retry."
            )
        service_names = [packages[0] + ".services.humanservice"]
    if len(service_names) != 1:
        raise MpfbServiceError("Multiple MPFB HumanService modules loaded; disable duplicates")
    name = service_names[0]
    try:
        imported = importer(name)
    except (ImportError, AttributeError, RuntimeError) as exc:
        raise MpfbServiceError("Enabled MPFB HumanService could not be imported: " + name) from exc
    cls = getattr(imported, "HumanService", None)
    if cls is None or not callable(getattr(cls, "create_human", None)) \
            or not callable(getattr(cls, "add_builtin_rig", None)):
        raise MpfbServiceError("MPFB HumanService API missing create_human or add_builtin_rig")
    return cls, name


def locate_target_service(
    human_module: str,
    loader: Callable[[str], Any] | None = None,
) -> tuple[Any, str]:
    """Use the same already-enabled MPFB namespace as HumanService."""
    if not isinstance(human_module, str) or not (
        human_module == "mpfb.services.humanservice"
        or human_module.endswith(".mpfb.services.humanservice")
    ):
        raise MpfbServiceError("Untrusted MPFB HumanService module name")
    module_name = human_module.rsplit(".", 1)[0] + ".targetservice"
    importer = importlib.import_module if loader is None else loader
    try:
        mod = importer(module_name)
    except (ImportError, AttributeError, RuntimeError) as exc:
        raise MpfbServiceError("MPFB TargetService could not be imported") from exc
    target = getattr(mod, "TargetService", None)
    if target is None or any(not callable(getattr(target, method, None)) for method in (
        "get_default_macro_info_dict", "get_macro_info_dict_from_basemesh"
    )):
        raise MpfbServiceError("MPFB TargetService macro API is unavailable")
    return target, module_name


def locate_human_properties(
    human_module: str,
    loader: Callable[[str], Any] | None = None,
) -> tuple[Any, str]:
    """Resolve MPFB HumanObjectProperties from the same enabled extension."""
    if not isinstance(human_module, str) or not (
        human_module == "mpfb.services.humanservice"
        or human_module.endswith(".mpfb.services.humanservice")
    ):
        raise MpfbServiceError("Untrusted MPFB HumanService module name")
    name = human_module.removesuffix(".services.humanservice") + ".entities.objectproperties"
    importer = importlib.import_module if loader is None else loader
    try:
        loaded = importer(name)
    except (ImportError, AttributeError, RuntimeError) as exc:
        raise MpfbServiceError("MPFB human object properties could not be imported") from exc
    properties = getattr(loaded, "HumanObjectProperties", None)
    if properties is None or any(
        not callable(getattr(properties, item, None)) for item in ("get_value", "set_value")
    ):
        raise MpfbServiceError("MPFB HumanObjectProperties API unavailable")
    return properties, name


def inspect_service(registry: Mapping[str, Any] | None = None,
                    loader: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """Report discoverability; never claim geometry creation or rigging."""
    try:
        _, name = locate_human_service(registry, loader)
    except MpfbServiceError as exc:
        return {"available": False, "api": "HumanService", "error": str(exc)}
    return {"available": True, "api": "HumanService", "module": name,
            "character_created": False, "rig_verified": False}


def _new_meshes(bpy: Any, before: set[int]) -> list[Any]:
    return [obj for obj in bpy.data.objects if obj.type == "MESH" and obj.as_pointer() not in before]


def create_human_with_rig(
    bpy: Any, service: Any, rig_name: str = "default", *,
    macro_parameters: dict[str, float] | None = None,
    target_service: Any | None = None,
) -> dict[str, Any]:
    """Create actual MPFB mesh + built-in armature in the caller's Blender process.

    Save/reopen and visual deformation checks happen outside this function.
    Failures never write a master file, so the per-job Blender process can exit.
    """
    if rig_name not in BUILTIN_RIGS:
        raise MpfbServiceError(f"Unapproved MPFB built-in rig: {rig_name!r}")
    old_meshes = {o.as_pointer() for o in bpy.data.objects if o.type == "MESH"}
    old_rigs = {o.as_pointer() for o in bpy.data.objects if o.type == "ARMATURE"}
    try:
        if macro_parameters is None:
            base = service.create_human()
        else:
            if target_service is None:
                raise MpfbServiceError("MPFB TargetService required for macro creation")
            macro_info = build_macro_info(target_service, macro_parameters)
            base = service.create_human(macro_detail_dict=macro_info)
    except Exception as exc:
        raise MpfbServiceError("MPFB HumanService.create_human() failed") from exc
    if getattr(base, "type", None) != "MESH" or base.as_pointer() in old_meshes:
        raise MpfbServiceError("MPFB service returned no new human basemesh")
    meshes = _new_meshes(bpy, old_meshes)
    if base not in meshes or len(base.data.vertices) <= 100:
        raise MpfbServiceError("MPFB basemesh contains insufficient geometry")
    try:
        rig = service.add_builtin_rig(base, rig_name)
    except Exception as exc:
        raise MpfbServiceError("MPFB built-in rig creation failed: " + rig_name) from exc
    if getattr(rig, "type", None) != "ARMATURE" or rig.as_pointer() in old_rigs:
        raise MpfbServiceError("MPFB did not return a newly created armature")
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE" and o.as_pointer() not in old_rigs]
    if rig not in rigs or len(rig.data.bones) < 5:
        raise MpfbServiceError("New MPFB armature has insufficient bones")
    macro_evidence = {}
    if macro_parameters is not None:
        try:
            macro_evidence = inspect_applied_macro(
                bpy, base, target_service, macro_parameters,
            )
        except Exception as exc:
            raise MpfbServiceError(
                "MPFB macro shapes were not verified on generated humanoid"
            ) from exc
    return {
        "method": "HumanService",
        "rig_choice": rig_name,
        "new_mesh_count": len(meshes),
        "new_mesh_vertices": [len(o.data.vertices) for o in meshes],
        "created_meshes": [{"name": o.name, "vertex_count": len(o.data.vertices)} for o in meshes],
        "rigs": [{"name": o.name, "bone_count": len(o.data.bones),
                  "bone_names": [b.name for b in o.data.bones]} for o in rigs],
        "all_armatures": [o.name for o in bpy.data.objects if o.type == "ARMATURE"],
        "shape_keys": {o.name: ([key.name for key in o.data.shape_keys.key_blocks]
                                if o.data.shape_keys else []) for o in meshes},
        "geometry_verified": False,
        "verified_reopen": False,
        "visual_deformation_verified": False,
        **macro_evidence,
    }
