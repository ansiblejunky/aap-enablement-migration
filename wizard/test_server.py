"""Proxy boundaries for the local wizard server."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from wizard.server import STATE, make_server, normalize_controller_url, proxy_target


class Recorder(BaseHTTPRequestHandler):
    hits = []
    marker = "a"

    def do_GET(self):
        Recorder.hits.append((self.path, self.headers.get("Authorization"), type(self).marker))
        if self.path.startswith("/api/v2/ping"):
            body = json.dumps({"version": "4.5.0", "marker": type(self).marker}).encode()
            self._send(200, "application/json", body)
            return
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:9/stolen")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        return

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start(handler, marker):
    handler.marker = marker
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _request(url, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode() or "null")
    except HTTPError as exc:
        raw = exc.read()
        parsed = json.loads(raw.decode() or "null") if raw else None
        return exc.code, parsed


class UrlTests(unittest.TestCase):
    def test_normalize_keeps_the_origin(self):
        self.assertEqual(
            normalize_controller_url("https://aap.example.com/api/v2/"),
            "https://aap.example.com",
        )
        self.assertEqual(
            normalize_controller_url("https://aap.example.com:8443/api/controller/v2"),
            "https://aap.example.com:8443",
        )

    def test_normalize_rejects_secrets_and_other_paths(self):
        with self.assertRaises(ValueError):
            normalize_controller_url("https://user:pass@aap.example.com")
        with self.assertRaises(ValueError):
            normalize_controller_url("file:///etc/passwd")
        with self.assertRaises(ValueError):
            normalize_controller_url("https://aap.example.com/ui/")

    def test_proxy_target_allows_api_and_rejects_escape(self):
        self.assertEqual(proxy_target("/proxy/api/v2/ping/"), "api/v2/ping/")
        self.assertEqual(
            proxy_target("/proxy/api/v2/organizations/?name=AAP%20Migration%20Lab"),
            "api/v2/organizations/?name=AAP%20Migration%20Lab",
        )
        with self.assertRaises(ValueError):
            proxy_target("/proxy/api/../../etc/passwd")
        with self.assertRaises(ValueError):
            proxy_target("/proxy/api/%2e%2e/secret")
        with self.assertRaises(ValueError):
            proxy_target("/proxy/http://evil.example/api/v2/ping/")


class ProxyTests(unittest.TestCase):
    def setUp(self):
        Recorder.hits = []
        STATE.reset()
        self.controller_a = _start(type("RecorderA", (Recorder,), {}), "a")
        self.controller_b = _start(type("RecorderB", (Recorder,), {}), "b")
        self.wizard = make_server("127.0.0.1", 0)
        self.wizard_thread = threading.Thread(target=self.wizard.serve_forever, daemon=True)
        self.wizard_thread.start()
        self.base = f"http://127.0.0.1:{self.wizard.server_address[1]}"

    def tearDown(self):
        for server in (self.wizard, self.controller_a, self.controller_b):
            server.shutdown()
            server.server_close()
        STATE.reset()

    def _origin(self, server):
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_proxy_forwards_get_and_stays_on_the_connected_controller(self):
        status, body = _request(
            self.base + "/connect",
            method="POST",
            payload={"url": self._origin(self.controller_a), "verify_tls": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["origin"], self._origin(self.controller_a))

        status, body = _request(
            self.base + "/proxy/api/v2/ping/",
            headers={"Authorization": "Bearer test-token"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["marker"], "a")
        self.assertEqual(Recorder.hits[-1][1], "Bearer test-token")

        status, body = _request(
            self.base + "/connect",
            method="POST",
            payload={"url": self._origin(self.controller_b) + "/api/v2/", "verify_tls": False},
        )
        self.assertEqual(status, 200)
        hits_before = len(Recorder.hits)
        status, body = _request(self.base + "/proxy/api/v2/ping/")
        self.assertEqual(body["marker"], "b")
        self.assertTrue(all(hit[2] != "a" for hit in Recorder.hits[hits_before:]))

        status, body = _request(self.base + "/proxy/api/v2/redirect")
        self.assertEqual(status, 502)
        self.assertIn("redirect", body["error"].lower())

        status, body = _request(self.base + "/proxy/api/%2e%2e/secret")
        self.assertEqual(status, 400)

    def test_advise_endpoint_scores_facts(self):
        status, body = _request(
            self.base + "/advise",
            method="POST",
            payload={
                "controller_version": "4.5.1",
                "api_style": "v2",
                "control_plane_nodes": 1,
                "execution_nodes": 0,
                "installer": "rpm",
                "rhel_major": 9,
                "hub": False,
                "eda": False,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["recommended_id"], "rpm-2.6")

    def test_precheck_endpoint_blocks_rhel_95(self):
        status, body = _request(
            self.base + "/precheck",
            method="POST",
            payload={
                "target": "rpm-2.6-growth",
                "controller_version": "4.5.8",
                "hub": True,
                "eda": False,
                "execution_nodes": 0,
                "hosts": [{
                    "name": "controller.lab",
                    "role": "automationcontroller",
                    "rhel": "9.5",
                }],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "blocked")
        os_check = next(item for item in body["checks"] if item["id"] == "os:controller.lab")
        self.assertIn("9.6", os_check["required"])

    def test_proxy_refuses_to_bind_beyond_localhost(self):
        with self.assertRaises(ValueError):
            make_server("0.0.0.0", 0)


if __name__ == "__main__":
    unittest.main()
