"""Tiny HTTP surface: POST /v0/complete → decision + receipt."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from adapter import MockAdapter, select_adapter
from envload import load_dotenv
from pipeline import run


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/v0/complete":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return
        prompt = str(data.get("prompt") or "").strip()
        if not prompt:
            self._json(400, {"error": "prompt is required"})
            return
        draft = data.get("draft")
        try:
            adapter = MockAdapter(str(draft)) if draft is not None else select_adapter()
            result = run(prompt, adapter=adapter)
        except RuntimeError as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, result.public_payload())


def main() -> None:
    load_dotenv()
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"cslm-genesis listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
