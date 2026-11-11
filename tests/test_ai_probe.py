"""Tests read-only API discovery against an in-process local fake server."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.ai.probe import probe_comfyui, probe_webui, validate_loopback_base
from ucc.core.errors import ValidationError


class _TestServer(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        self.requests.append((self.command, self.path))
        if self.path == "/system_stats":
            body = {"system": {"os": "win32", "comfyui_version": "0.3.test"}}
        elif self.path == "/sdapi/v1/sd-models":
            body = [{"title": "private-checkpoint-name-not-to-share"}, {"title": "model-b"}]
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.invalid/exfiltrate")
            self.end_headers()
            return
        else:
            self.send_error(404)
            return
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self.send_error(405)

    def log_message(self, format, *args):
        return


class LocalAIProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _TestServer)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_comfyui_read_only(self):
        got = probe_comfyui(self.url)
        self.assertTrue(got.reachable)
        self.assertEqual(got.details["version"], "0.3.test")
        self.assertFalse(got.details["can_submit_workflows"])

    def test_webui_model_count_not_names(self):
        got = probe_webui(self.url)
        self.assertTrue(got.reachable)
        self.assertEqual(got.details["model_count"], 2)
        self.assertNotIn("private-checkpoint-name-not-to-share", json.dumps(got.to_dict()))
        self.assertFalse(got.details["can_submit_workflows"])

    def test_no_external_addresses(self):
        for bad in ("https://127.0.0.1:8188", "http://127.0.0.1.evil.com:8188",
                    "http://user:pw@127.0.0.1:8188", "file:///etc/passwd",
                    "http://localhost:8188/prompt", "http://localhost"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_loopback_base(bad)

    def test_invalid_response_is_offline_not_false_success(self):
        # WebUI model response is a list, not the required ComfyUI system object.
        from unittest.mock import patch
        with patch("ucc.ai.probe._get_json", return_value=[]):
            self.assertFalse(probe_comfyui(self.url).reachable)
        with patch("ucc.ai.probe._get_json", return_value={}):
            self.assertFalse(probe_webui(self.url).reachable)

    def test_http_redirect_is_not_followed(self):
        from ucc.ai.probe import _get_json
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError):
            _get_json(self.url, "/redirect")

    def test_all_calls_are_get(self):
        _TestServer.requests.clear()
        probe_comfyui(self.url)
        probe_webui(self.url)
        self.assertEqual({method for method, _ in _TestServer.requests}, {"GET"})
