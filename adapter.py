"""Base LM adapters. The model is a component; CSLM-Genesis owns release."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Protocol

from canonical import sha256_hex

DEFAULT_ADAPTER = "openai_compat"
DEFAULT_BASE_URL = "http://127.0.0.1:11435"
DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_TIMEOUT_SEC = 300


@dataclass(frozen=True)
class Draft:
    text: str
    model_id: str
    model_version: str
    generation_id: str


class BaseLMAdapter(Protocol):
    model_id: str
    model_version: str

    def generate(self, prompt: str) -> Draft: ...


class MockAdapter:
    """Deterministic adapter for tests and the week-1 demo."""

    def __init__(
        self,
        draft_text: str,
        model_id: str = "mock-v0",
        model_version: str = "mock",
    ) -> None:
        self.draft_text = draft_text
        self.model_id = model_id
        self.model_version = model_version

    def generate(self, prompt: str) -> Draft:
        generation_id = "gen:mock:" + sha256_hex(prompt + "\n" + self.draft_text)[:16]
        return Draft(
            text=self.draft_text,
            model_id=self.model_id,
            model_version=self.model_version,
            generation_id=generation_id,
        )


class OpenAICompatAdapter:
    """OpenAI-compatible HTTP adapter. Env-selected; not used in tests."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
    ) -> None:
        if not base_url.strip():
            raise RuntimeError("CSLM_BASE_LM_BASE_URL is required for openai_compat")
        if not model.strip():
            raise RuntimeError("CSLM_BASE_LM_MODEL is required for openai_compat")
        self.base_url = base_url.rstrip("/")
        self.model_id = model
        self.model_version = model
        self.api_key = api_key or ""
        self.timeout_sec = int(os.environ.get("CSLM_BASE_LM_TIMEOUT", str(DEFAULT_TIMEOUT_SEC)))

    def generate(self, prompt: str) -> Draft:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json"}
        token = self.api_key or ("ollama" if "127.0.0.1" in self.base_url or "localhost" in self.base_url else "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"base LM request failed: {exc}") from exc
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError("base LM returned no choices")
        text = str((choices[0].get("message") or {}).get("content") or "")
        generation_id = str(body.get("id") or f"gen:openai:{uuid.uuid4()}")
        return Draft(
            text=text,
            model_id=self.model_id,
            model_version=str(body.get("model") or self.model_version),
            generation_id=generation_id,
        )


def select_adapter(draft_text: str | None = None) -> BaseLMAdapter:
    kind = os.environ.get("CSLM_ADAPTER", DEFAULT_ADAPTER).strip().lower()
    if kind == "mock":
        if draft_text is None:
            raise RuntimeError(
                "mock adapter needs --draft or a fixture; unset CSLM_ADAPTER or use openai_compat for local Ollama"
            )
        return MockAdapter(draft_text)
    if kind == "openai_compat":
        return OpenAICompatAdapter(
            base_url=os.environ.get("CSLM_BASE_LM_BASE_URL", DEFAULT_BASE_URL),
            model=os.environ.get("CSLM_BASE_LM_MODEL", DEFAULT_MODEL),
            api_key=os.environ.get("CSLM_BASE_LM_API_KEY"),
        )
    raise RuntimeError(f"unknown CSLM_ADAPTER={kind!r}; use mock or openai_compat")
