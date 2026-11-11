"""ComfyUI integration contract tests against a local fake HTTP server, never a live GPU."""
from __future__ import annotations

import contextlib
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.ai.generate import (
    BUILTIN_NODES, ComfyGenerationError, ComfyUIClient, TextToImageSpec,
    _verify_png, workflow,
)
from ucc.core.errors import ValidationError
from ucc.ai.__main__ import main

JOB_ID = "fcded3c2-6235-405c-8589-a1cbec8a00a0"


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def valid_png() -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
            chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff")) + chunk(b"IEND", b""))


class FakeComfyHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str]] = []
    checkpoint_name: str = "already-installed.safetensors"
    nodes_available: set[str] = set(BUILTIN_NODES)
    pending = True
    image_list: list[dict] = []
    image_content: bytes = valid_png()
    response_prompt_id = JOB_ID
    use_redirect = False
    captured_workflow: dict | None = None

    def respond(self, obj: dict | list, code: int = 200) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        self.requests.append(("GET", self.path))
        if self.use_redirect:
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/unsafe")
            self.end_headers()
            return
        if self.path == "/object_info":
            self.respond({node: {} for node in self.nodes_available})
        elif self.path == "/models/checkpoints":
            self.respond([self.checkpoint_name])
        elif self.path == f"/history/{JOB_ID}":
            result = {} if self.pending else {JOB_ID: {"outputs": {"9": {"images": self.image_list}}}}
            self.respond(result)
        elif self.path.startswith("/view?"):
            content = self.image_content
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        self.requests.append(("POST", self.path))
        if self.path != "/prompt":
            self.send_error(404)
            return
        length = int(self.headers["Content-Length"])
        data = json.loads(self.rfile.read(length))
        self.__class__.captured_workflow = data["prompt"]
        self.respond({"prompt_id": self.response_prompt_id, "number": 0, "node_errors": {}})

    def log_message(self, *args) -> None:
        pass


class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeComfyHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self) -> None:
        FakeComfyHandler.requests = []
        FakeComfyHandler.nodes_available = set(BUILTIN_NODES)
        FakeComfyHandler.checkpoint_name = "already-installed.safetensors"
        FakeComfyHandler.pending = True
        FakeComfyHandler.image_list = []
        FakeComfyHandler.image_content = valid_png()
        FakeComfyHandler.response_prompt_id = JOB_ID
        FakeComfyHandler.captured_workflow = None
        FakeComfyHandler.use_redirect = False
        self.spec = TextToImageSpec("already-installed.safetensors", "Original fantasy hero A-pose", seed=123)
        self.client = ComfyUIClient(self.url)

    def test_no_user_authorization_means_zero_requests(self):
        with self.assertRaisesRegex(ComfyGenerationError, "explicit"):
            self.client.submit(self.spec)
        self.assertEqual(FakeComfyHandler.requests, [])

    def test_valid_job_uses_fixed_builtin_graph_and_returned_id(self):
        queued = self.client.submit(self.spec, explicitly_authorized=True).to_dict()
        self.assertEqual(queued["status"], "QUEUED_UNVERIFIED")
        self.assertFalse(queued["geometry_generated"])
        self.assertEqual(queued["node_count"], 7)
        self.assertEqual(queued["prompt_id"], JOB_ID)
        names = {v["class_type"] for v in FakeComfyHandler.captured_workflow.values()}
        self.assertEqual(names, BUILTIN_NODES)
        graph = FakeComfyHandler.captured_workflow
        self.assertEqual(graph["4"]["inputs"]["ckpt_name"], self.spec.checkpoint)
        self.assertEqual(graph["3"]["inputs"]["seed"], 123)
        self.assertEqual(graph["5"]["inputs"]["width"], 512)
        self.assertEqual(FakeComfyHandler.requests[-1], ("POST", "/prompt"))
        self.assertEqual(len(queued["workflow_sha256"]), 64)
        self.assertNotIn(self.spec.prompt, json.dumps(queued))

    def test_checkpoint_missing_no_submission(self):
        FakeComfyHandler.checkpoint_name = "different-model.safetensors"
        with self.assertRaisesRegex(ComfyGenerationError, "checkpoint"):
            self.client.submit(self.spec, explicitly_authorized=True)
        self.assertNotIn(("POST", "/prompt"), FakeComfyHandler.requests)

    def test_required_node_missing_no_submission(self):
        FakeComfyHandler.nodes_available.remove("KSampler")
        with self.assertRaisesRegex(ComfyGenerationError, "KSampler"):
            self.client.submit(self.spec, explicitly_authorized=True)
        self.assertNotIn(("POST", "/prompt"), FakeComfyHandler.requests)

    def test_bad_prompt_id_rejected(self):
        FakeComfyHandler.response_prompt_id = "../../bad"
        with self.assertRaisesRegex(ComfyGenerationError, "prompt ID"):
            self.client.submit(self.spec, explicitly_authorized=True)

    def test_remote_and_redirect_unsupported(self):
        for url in ("https://127.0.0.1:8188", "http://192.168.1.2:8188", "http://user:pass@127.0.0.1:8188",
                    "http://127.0.0.1:8188/api", "http://127.0.0.1:8188?foo=1"):
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    ComfyUIClient(url)
        FakeComfyHandler.use_redirect = True
        with self.assertRaises(ComfyGenerationError):
            self.client.submit(self.spec, explicitly_authorized=True)
        self.assertNotIn(("POST", "/prompt"), FakeComfyHandler.requests)

    def test_invalid_specs_rejected(self):
        invalids = [
            {"width": 510}, {"height": 0}, {"steps": 0}, {"seed": -1},
            {"cfg": float("nan")}, {"sampler": "custom"}, {"prompt": " "},
        ]
        for kwargs in invalids:
            base = dict(checkpoint=self.spec.checkpoint, prompt=self.spec.prompt)
            base.update(kwargs)
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    TextToImageSpec(**base)

    def test_pending_history_no_download(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.client.fetch_images(JOB_ID, directory)
            self.assertEqual(result["status"], "PENDING")
            self.assertFalse(list(Path(directory).glob("*.png")))

    def test_download_png_uses_safe_deterministic_filename(self):
        FakeComfyHandler.pending = False
        FakeComfyHandler.image_list = [{"filename": "UCC_saved_00001_.png", "type": "output", "subfolder": ""}]
        with tempfile.TemporaryDirectory() as directory:
            result = self.client.fetch_images(JOB_ID, directory)
            self.assertEqual(result["status"], "PNG_DOWNLOADED_UNREVIEWED")
            name = f"ucc_{JOB_ID}_00.png"
            self.assertEqual((Path(directory) / name).read_bytes(), valid_png())
            self.assertEqual(len(result["images"][0]["sha256"]), 64)
            self.assertFalse(result["geometry_generated"])
            with self.assertRaisesRegex(ComfyGenerationError, "overwrite"):
                self.client.fetch_images(JOB_ID, directory)
            self.assertEqual((Path(directory) / name).read_bytes(), valid_png())

    def test_reject_malicious_history_filename_before_image_fetch(self):
        FakeComfyHandler.pending = False
        FakeComfyHandler.image_list = [{"filename": "../../secret.png", "type": "output", "subfolder": ""}]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ComfyGenerationError, "Unsafe"):
                self.client.fetch_images(JOB_ID, directory)
            self.assertFalse(any("/view" in x[1] for x in FakeComfyHandler.requests))
            self.assertFalse(list(Path(directory).iterdir()))

    def test_reject_wrong_folder_type(self):
        FakeComfyHandler.pending = False
        FakeComfyHandler.image_list = [{"filename": "valid.png", "type": "temp", "subfolder": "../../"}]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ComfyGenerationError, "location"):
                self.client.fetch_images(JOB_ID, directory)

    def test_bad_png_crc_or_trailer_fails_without_partial_output(self):
        FakeComfyHandler.pending = False
        FakeComfyHandler.image_list = [{"filename": "test.png", "type": "output", "subfolder": ""}]
        FakeComfyHandler.image_content = valid_png()[:-5] + b"BAD!!"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ComfyGenerationError):
                self.client.fetch_images(JOB_ID, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_reject_bad_prompt_id_without_server_contact(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValidationError):
                self.client.fetch_images("../../oops", directory)
        self.assertEqual(FakeComfyHandler.requests, [])

    def test_cli_without_permission_never_queues(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            status = main(["generate", "--base-url", self.url, "--checkpoint",
                           self.spec.checkpoint, "--prompt", self.spec.prompt])
        self.assertEqual(status, 2)
        self.assertEqual(FakeComfyHandler.requests, [])

    def test_cli_queue_requires_real_approval(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = main(["generate", "--base-url", self.url, "--checkpoint",
                           self.spec.checkpoint, "--prompt", self.spec.prompt,
                           "--confirm-local-execution", "--seed", "12"])
        self.assertEqual(result, 0)
        queued = json.loads(out.getvalue())
        self.assertEqual(queued["status"], "QUEUED_UNVERIFIED")
        self.assertEqual(queued["prompt_id"], JOB_ID)

    def test_cli_fetch_pending_without_creating_png(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["fetch", JOB_ID, "--base-url", self.url,
                                       "--output-dir", directory]), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "PENDING")
            self.assertFalse(list(Path(directory).glob("*.png")))

    def test_workflow_prefix_rejects_injection(self):
        with self.assertRaises(ValidationError):
            workflow(self.spec, "../out")


if __name__ == "__main__":
    unittest.main()
