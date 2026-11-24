"""Localhost server for the AAP Migration Lab wizard.

The page calls this process, and this process calls one controller. Browsers
cannot send those calls themselves: controller hosts do not grant CORS to
another origin. Credentials stay in the browser and are forwarded on each
GET. This process does not write them to disk or include the Authorization
header in its log line.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

if __package__:
    from .advise import AdviseError, advise
    from .precheck import PrecheckError, precheck
else:
    from advise import AdviseError, advise
    from precheck import PrecheckError, precheck

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/wizard.js": "wizard.js",
    "/wizard.css": "wizard.css",
}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}
API_ROOTS = {
    "",
    "/",
    "/api",
    "/api/",
    "/api/v2",
    "/api/v2/",
    "/api/controller",
    "/api/controller/",
    "/api/controller/v2",
    "/api/controller/v2/",
}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_JSON_BYTES = 65_536
MAX_UPSTREAM_BYTES = 2_000_000
UPSTREAM_TIMEOUT = 20
LOCAL_HOSTS = {"127.0.0.1", "::1"}


class ProxyState:
    """The single controller this process is allowed to call."""

    def __init__(self):
        self.origin = None
        self.verify_tls = True
        self.lock = threading.Lock()

    def reset(self):
        with self.lock:
            self.origin = None
            self.verify_tls = True

    def update(self, origin: str, verify_tls: bool):
        with self.lock:
            self.origin = origin
            self.verify_tls = bool(verify_tls)

    def snapshot(self):
        with self.lock:
            return self.origin, self.verify_tls


STATE = ProxyState()


def normalize_controller_url(url: str) -> str:
    """Reduce a pasted controller URL to its origin."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Enter the controller URL.")
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise ValueError("Use an http or https controller URL.")
    if parts.username or parts.password:
        raise ValueError("Put the username and password in the login fields, not in the URL.")
    if not parts.hostname:
        raise ValueError("The controller URL needs a hostname.")
    path = parts.path or ""
    if path not in API_ROOTS:
        raise ValueError(
            "Use the controller host, or a URL that ends at /api/v2/ or /api/controller/v2/."
        )
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    return f"{parts.scheme}://{netloc}"


def proxy_target(request_target: str) -> str:
    """Return the controller path for a /proxy/ request, query included."""
    parts = urlsplit(request_target)
    if parts.scheme or parts.netloc:
        raise ValueError("Proxy requests stay on this server.")
    path = parts.path or ""
    prefix = "/proxy/"
    if not path.startswith(prefix):
        raise ValueError("Proxy path is missing.")
    rest = unquote(path[len(prefix):])
    if rest.startswith("/"):
        rest = rest[1:]
    if "\\" in rest:
        raise ValueError("The proxy path cannot contain backslashes.")
    segments = [segment for segment in rest.split("/") if segment != ""]
    if not segments or segments[0] != "api":
        raise ValueError("The proxy only forwards /api/ paths.")
    if any(segment in (".", "..") for segment in segments):
        raise ValueError("The proxy path cannot contain . or .. .")
    suffix = "/" if rest.endswith("/") else ""
    query = f"?{parts.query}" if parts.query else ""
    return "/".join(segments) + suffix + query


class _RejectRedirects(HTTPRedirectHandler):
    """Refuse to follow a controller redirect, so Authorization stays put."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, msg, headers, fp)


def _opener(verify_tls: bool):
    context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
    return build_opener(_RejectRedirects, HTTPSHandler(context=context))


class WizardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Request line and status only. Authorization is a header, not this line.
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC_FILES:
            self._static(STATIC_FILES[path])
            return
        if path.startswith("/proxy/"):
            self._proxy()
            return
        self._send_json(404, {"error": "Not found."})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/connect":
            self._connect()
            return
        if path == "/advise":
            self._advise()
            return
        if path == "/precheck":
            self._precheck()
            return
        self._send_json(404, {"error": "Not found."})

    def _connect(self):
        payload = self._read_json()
        if payload is None:
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "Connect with a JSON object."})
            return
        try:
            origin = normalize_controller_url(payload.get("url", ""))
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        verify_tls = payload.get("verify_tls", True)
        if not isinstance(verify_tls, bool):
            self._send_json(400, {"error": "verify_tls must be true or false."})
            return
        STATE.update(origin, verify_tls)
        self._send_json(200, {"origin": origin, "verify_tls": verify_tls})

    def _advise(self):
        payload = self._read_json()
        if payload is None:
            return
        try:
            result = advise(payload)
        except AdviseError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception:
            sys.stderr.write("advise failed\n")
            self._send_json(500, {"error": "Could not score this environment."})
            return
        self._send_json(200, result)

    def _precheck(self):
        payload = self._read_json()
        if payload is None:
            return
        try:
            result = precheck(payload)
        except PrecheckError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception:
            sys.stderr.write("precheck failed\n")
            self._send_json(500, {"error": "Could not score this pre-check."})
            return
        self._send_json(200, result)

    def _proxy(self):
        origin, verify_tls = STATE.snapshot()
        if not origin:
            self._send_json(409, {"error": "Connect to a controller first."})
            return
        try:
            upstream_path = proxy_target(self.path)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        headers = {
            "Accept": self.headers.get("Accept", "application/json"),
            "User-Agent": "aap-migration-wizard",
        }
        authorization = self.headers.get("Authorization")
        if authorization:
            headers["Authorization"] = authorization
        request = Request(
            origin + "/" + upstream_path,
            headers=headers,
            method="GET",
        )
        response = None
        try:
            response = _opener(verify_tls).open(request, timeout=UPSTREAM_TIMEOUT)
            self._forward_upstream(response.status, response.headers, response)
        except HTTPError as exc:
            try:
                if exc.code in REDIRECT_STATUSES:
                    self._send_json(
                        502,
                        {
                            "error": (
                                "The controller redirected the request. "
                                "The wizard does not follow redirects."
                            )
                        },
                    )
                    return
                self._forward_upstream(exc.code, exc.headers, exc)
            finally:
                exc.close()
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            text = str(reason).lower()
            if "certificate" in text:
                message = (
                    "Could not verify the controller certificate. For a lab "
                    "certificate, turn TLS verification off and connect again."
                )
            elif "timed out" in text:
                message = "The controller did not answer in time."
            else:
                message = "Could not reach the controller."
            sys.stderr.write("controller unreachable: %s\n" % type(reason).__name__)
            self._send_json(502, {"error": message})
        except ValueError as exc:
            self._send_json(502, {"error": str(exc)})
        finally:
            if response is not None:
                response.close()

    def _forward_upstream(self, status, headers, stream):
        try:
            body = stream.read(MAX_UPSTREAM_BYTES + 1)
        except Exception:
            self._send_json(502, {"error": "Could not read the controller response."})
            return
        if len(body) > MAX_UPSTREAM_BYTES:
            self._send_json(502, {"error": "The controller response was too large."})
            return
        content_type = "application/json"
        if headers is not None:
            content_type = headers.get("Content-Type", content_type)
        self._send_bytes(status, content_type, body)

    def _static(self, name: str):
        path = STATIC_DIR / name
        if not path.is_file():
            self._send_json(404, {"error": "Wizard files are missing."})
            return
        data = path.read_bytes()
        content_type = CONTENT_TYPES.get(path.suffix, "application/octet-stream")
        self._send_bytes(200, content_type, data)

    def _read_json(self):
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(400, {"error": "Content-Length must be an integer."})
            return None
        if length < 0 or length > MAX_JSON_BYTES:
            self._send_json(413, {"error": "Request is too large."})
            return None
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Expected a JSON object."})
            return None

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _send_bytes(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    if host not in LOCAL_HOSTS:
        raise ValueError("The wizard binds to localhost only.")
    server = ThreadingHTTPServer((host, port), WizardHandler)
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="AAP Migration Lab wizard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        server = make_server(args.host, args.port)
    except ValueError as exc:
        parser.error(str(exc))
    url = f"http://{args.host}:{server.server_address[1]}/"
    print(f"AAP Migration Lab wizard at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
