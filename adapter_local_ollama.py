"""Local Ollama drafter. CSLM-Genesis still owns release."""

from __future__ import annotations

from adapter import DEFAULT_BASE_URL, DEFAULT_MODEL, OpenAICompatAdapter, select_adapter


def local_ollama_adapter() -> OpenAICompatAdapter:
    adapter = select_adapter()
    if not isinstance(adapter, OpenAICompatAdapter):
        return OpenAICompatAdapter(DEFAULT_BASE_URL, DEFAULT_MODEL)
    return adapter
