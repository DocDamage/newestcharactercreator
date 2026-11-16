"""Toolchain selection tests use metadata fixtures, never installed tools."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.jobs import unreal_toolchain as module


class UnrealToolchainTests(unittest.TestCase):
    def test_banned_or_unknown_compilers_fail_closed(self):
        metadata = {'BannedVisualCppVersions': ['14.51.0-14.51.99999', '14.44.0-14.44.35210']}
        self.assertTrue(module.compiler_allowed('14.44.35227', metadata))
        for version in ('14.51.36231', '14.44.35207', '14.44.35228', 'garbage'):
            self.assertFalse(module.compiler_allowed(version, metadata))
        self.assertFalse(module.compiler_allowed('14.44.35227', {}))

    def test_selected_fixture_tools_are_bound_and_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); engine = root/'Engine'; base = root/'pf86'
            editor = engine/'Binaries/Win64/UnrealEditor.exe'
            compiler = base/'Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe'
            sdk = base/'Windows Kits/10'
            files = [editor, compiler, compiler.with_name('link.exe'), compiler.parents[3]/'include/yvals_core.h',
                engine/'Binaries/ThirdParty/DotNet/10.0/win-x64/dotnet.exe',
                engine/'Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll',
                engine/'Binaries/Win64/UnrealEditor.modules',
                sdk/'Include/10.0.26100.0/um/Windows.h', sdk/'bin/10.0.26100.0/x64/rc.exe',
                sdk/'Lib/10.0.26100.0/um/x64/kernel32.lib']
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'HOST_METADATA_FIXTURE_NOT_AN_EXECUTABLE')
            build = engine/'Build/Build.version'; build.parent.mkdir()
            build.write_text(json.dumps({'MajorVersion': 5, 'MinorVersion': 9, 'PatchVersion': 0,
                'Changelist': 60351404, 'BranchName': '++UE5+Release-5.9'}))
            metadata = engine/'Config/Windows/Windows_SDK.json'; metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps({'BannedVisualCppVersions': ['14.44.0-14.44.35210', '14.51.0-14.51.99999']}))
            with patch.object(module.sys, 'platform', 'win32'), patch.dict(module.os.environ, {'ProgramFiles(x86)': str(base)}), patch.object(module, '_product_version', return_value='14.44.35227'):
                result = module.preflight_unreal_toolchain(editor)
            self.assertEqual(result.vs_root, base/'Microsoft Visual Studio/2022/BuildTools')
            self.assertEqual(result.compiler, compiler)
            self.assertNotEqual(result.identity_sha256, replace(result, compiler_version='14.51.36231').identity_sha256)
            result.require_unchanged()
            compiler.write_bytes(b'CHANGED')
            with self.assertRaises(ProjectStorageError): result.require_unchanged()

    def test_wrong_platform_rejects_before_any_tool_execution(self):
        with patch.object(module.sys, 'platform', 'linux'):
            with self.assertRaises(ValidationError): module.preflight_unreal_toolchain(Path('/missing'))
