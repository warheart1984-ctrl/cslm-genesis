"""HTTP session endpoint tests."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from http_app import Handler


def _post(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def test_session_turn_endpoint_returns_session_receipt() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        first = _post(
            f"{base}/v0/session/http-smoke/turn",
            {
                "prompt": "What is the chemical formula of water?",
                "draft": "Water's chemical formula is H2O.",
                "history_context": False,
            },
        )
        second = _post(
            f"{base}/v0/session/http-smoke/turn",
            {
                "prompt": "Tell me about water and Mars.",
                "draft": "Water's chemical formula is CO2. Mars has two moons.",
                "history_context": True,
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert first["session_id"] == "http-smoke"
    assert first["decision"] == "release"
    assert second["decision"] == "release"
    assert second["answer"] == "Mars has two moons."
    assert second["receipt"]["session"]["history_context"] is True
    assert second["receipt"]["session"]["contradictions"]
