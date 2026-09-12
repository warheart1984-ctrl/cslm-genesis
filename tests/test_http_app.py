"""HTTP session endpoint tests."""

from __future__ import annotations

import json
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer

from adapter import MockAdapter
from http_app import Handler
from session import SessionManager


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


def test_session_turn_endpoint_serializes_concurrent_updates() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"

        def submit(payload: dict[str, object]) -> dict[str, object]:
            return _post(f"{base}/v0/session/race/turn", payload)

        first_payload = {
            "prompt": "What is the chemical formula of water?",
            "draft": "Water's chemical formula is H2O.",
            "history_context": False,
        }
        second_payload = {
            "prompt": "How many moons does Mars have?",
            "draft": "Mars has two moons.",
            "history_context": False,
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(submit, (first_payload, second_payload)))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert {first["decision"], second["decision"]} == {"release"}
    session = SessionManager().load_session("race", MockAdapter(""))
    assert len(session.receipts) == 2
    assert {receipt["session"]["turn_id"] for receipt in session.receipts} == {"t1", "t2"}
