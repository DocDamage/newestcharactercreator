"""Published delivery checks reject changed, redirected and private inputs."""
from pathlib import Path
import tempfile
import unittest

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.jobs.unreal_engine import project_files, DELIVERY_FILES
from ucc.jobs.unreal_runtime_verification import check_payload, verify_unreal_published_project, PORTABLE_METADATA
from ucc.jobs.master_preview import _digest


class UnrealPublishedTests(unittest.TestCase):
    def test_portable_metadata_seal_and_changed_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in DELIVERY_FILES:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'HOST_ONLY_INVENTORY_FIXTURE')
            expected = project_files(root)
            for name in PORTABLE_METADATA:
                (root/name).write_text('HOST_ONLY_PORTABLE_METADATA_FIXTURE')
                expected[name] = _digest(root/name, None)
            check_payload(root, expected)
            (root/'DerivedSources/character.fbx').write_bytes(b'ALTERED')
            with self.assertRaises(ProjectStorageError): check_payload(root, expected)

    def test_manifest_cannot_authorize_arbitrary_private_files(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValidationError): check_payload(Path(temp), {'source_reference.json': 'a'*64})

    def test_wrong_context_rejects_before_clone_or_worker(self):
        with self.assertRaises(ValidationError):
            verify_unreal_published_project(Path('/missing'), source=None, request=None, toolchain=None,
                engine_receipt_path=Path('/missing'), engine_receipt_sha256='a'*64, expected_files={})
