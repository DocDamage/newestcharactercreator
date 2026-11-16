"""Read-only selection of the existing, admitted Windows Unreal build tools."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import ctypes
import math
import os
import sys
import time

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expressions import is_sha256
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_contract import ENGINE_VERSION
from .export_guards import protected_file, cancel_context, failure_reason
from .godot_candidate_inputs import identity, read_json
from .master_preview import _digest
from .skin_material_preparation import _BudgetCancel

COMPILER_VERSION = '14.44.35227'
SDK_VERSION = '10.0.26100.0'


def _product_version(path: Path) -> str:
    """Use the selected PE's version resource; never execute a PATH compiler."""
    version = ctypes.WinDLL('version', use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    version.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
    length = version.GetFileVersionInfoSizeW(str(path), None)
    if not length:
        raise ProjectStorageError('Selected compiler has no readable product version')
    data = ctypes.create_string_buffer(length)
    if not version.GetFileVersionInfoW(str(path), 0, length, data):
        raise ProjectStorageError('Cannot read selected compiler version resource')
    pointer = ctypes.c_void_p(); size = ctypes.c_uint()
    if not version.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(size)) or size.value < 52:
        raise ProjectStorageError('Selected compiler version resource is malformed')
    values = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
    return '.'.join(str(value) for value in (values[4] >> 16, values[4] & 65535, values[5] >> 16))


def _version_tuple(value):
    return tuple(int(part) for part in value.split('.'))


def compiler_allowed(version: str, sdk_metadata: dict) -> bool:
    try:
        current = _version_tuple(version)
        if version != COMPILER_VERSION:
            return False
        ranges = sdk_metadata['BannedVisualCppVersions']
        if type(ranges) is not list or not ranges:
            return False
        return not any(_version_tuple(low) <= current <= _version_tuple(high)
                       for low, high in (item.split('-') for item in ranges))
    except (ValueError, TypeError, KeyError):
        return False


@dataclass(frozen=True, slots=True)
class UnrealToolchain:
    engine_root: Path
    editor_exe: Path
    build_version: Path
    ubt: Path
    dotnet: Path
    compiler: Path
    vs_root: Path
    sdk_root: Path
    files: tuple[tuple[str, str], ...]
    identities: tuple[tuple[str, tuple], ...]
    compiler_version: str = COMPILER_VERSION
    sdk_version: str = SDK_VERSION

    def __post_init__(self):
        paths = (self.engine_root, self.editor_exe, self.build_version, self.ubt, self.dotnet,
                 self.compiler, self.vs_root, self.sdk_root)
        if (any(not isinstance(path, Path) or not path.is_absolute() for path in paths)
                or type(self.files) is not tuple or len(dict(self.files)) != len(self.files)
                or any(type(name) is not str or not is_sha256(value) for name, value in self.files)
                or not {str(path) for path in (self.editor_exe, self.build_version, self.ubt,
                    self.dotnet, self.compiler)} <= set(dict(self.files))):
            raise ValidationError('Unreal toolchain needs complete absolute selected-tool SHA bindings')

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'policy': 'UCC_UNREAL_INSTALLED_TOOLCHAIN_V1',
            'engine_version': ENGINE_VERSION, 'compiler_version': self.compiler_version,
            'sdk_version': self.sdk_version,
            **{name: str(getattr(self, name)) for name in ('engine_root', 'editor_exe',
                'build_version', 'ubt', 'dotnet', 'compiler', 'vs_root', 'sdk_root')},
            'files': dict(self.files)}

    @property
    def identity_sha256(self) -> str:
        return sha256(canonical_bytes(self.to_dict())).hexdigest()

    def require_unchanged(self, cancel=None) -> None:
        if self.compiler_version != COMPILER_VERSION or self.sdk_version != SDK_VERSION:
            raise ValidationError('Unreal toolchain is outside the admitted compiler/SDK profile')
        identities = dict(self.identities)
        if set(identities) != set(dict(self.files)):
            raise ValidationError('Unreal toolchain file identity closure is incomplete')
        for name, expected in self.files:
            path = Path(name); protected_file(path)
            if identity(path) != identities[name] or _digest(path, cancel) != expected:
                raise ProjectStorageError('Selected Unreal build tool changed; run toolchain review again')


def preflight_unreal_toolchain(editor_exe: Path, *, cancel=None, timeout_s: float = 300) -> UnrealToolchain:
    if sys.platform != 'win32':
        raise ValidationError('This Unreal profile requires the installed Windows x64 editor and VS2022 tools')
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600:
        raise ValidationError('Unreal toolchain review needs a bounded deadline')
    deadline, _ = cancel_context(cancel, time.monotonic()+timeout_s)
    budget = _BudgetCancel(cancel, deadline)
    editor = Path(editor_exe); protected_file(editor)
    if editor.name != 'UnrealEditor.exe' or editor.parent.name != 'Win64' or editor.parent.parent.name != 'Binaries':
        raise ValidationError('Select the installed Engine/Binaries/Win64/UnrealEditor.exe')
    engine = editor.parents[2]
    build = engine/'Build/Build.version'
    metadata = engine/'Config/Windows/Windows_SDK.json'
    for path in (build, metadata): protected_file(path)
    version = read_json(build, 128*1024)
    actual = f"{version['MajorVersion']}.{version['MinorVersion']}.{version['PatchVersion']}-{version['Changelist']}+{version['BranchName']}"
    if actual != ENGINE_VERSION:
        raise ValidationError('Selected Unreal editor build differs from the admitted Unreal 5.9 build')
    base = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))
    candidates = [base/'Microsoft Visual Studio/2022'/edition/'VC/Tools/MSVC'/folder/'bin/Hostx64/x64/cl.exe'
        for edition in ('BuildTools', 'Community', 'Professional', 'Enterprise')
        for folder in ('14.44.35207', '14.44.35227')]
    compiler = next((path for path in candidates if path.is_file()
        and compiler_allowed(_product_version(path), read_json(metadata, 256*1024))), None)
    if compiler is None:
        raise ProjectStorageError('Existing patched VS2022 compiler 14.44.35227 is required; banned 14.51/PATH tools cannot be used. Select or configure an existing supported VS2022 installation; nothing was installed.')
    sdk = base/'Windows Kits/10'
    files = [editor, build, metadata, compiler,
        compiler.with_name('link.exe'), compiler.parents[3]/'include/yvals_core.h',
        engine/'Binaries/ThirdParty/DotNet/10.0/win-x64/dotnet.exe',
        engine/'Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll',
        sdk/f'Include/{SDK_VERSION}/um/Windows.h', sdk/f'bin/{SDK_VERSION}/x64/rc.exe',
        sdk/f'Lib/{SDK_VERSION}/um/x64/kernel32.lib', engine/'Binaries/Win64/UnrealEditor.modules']
    for path in files: protected_file(path)
    hashes = tuple(sorted((str(path), _digest(path, budget)) for path in files))
    reason, message = failure_reason(cancel, deadline)
    if reason: raise ProjectStorageError(message)
    result = UnrealToolchain(engine, editor, build, files[7], files[6], compiler,
        compiler.parents[7], sdk, hashes, tuple(sorted((str(path), identity(path)) for path in files)))
    result.require_unchanged(budget)
    return result
