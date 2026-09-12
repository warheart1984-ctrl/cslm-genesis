"""Local Ollama is the default live adapter; mock stays explicit."""

from __future__ import annotations

import os

from adapter import DEFAULT_BASE_URL, DEFAULT_MODEL, MockAdapter, select_adapter


def test_select_adapter_defaults_to_local_ollama(monkeypatch) -> None:
    monkeypatch.delenv("CSLM_ADAPTER", raising=False)
    monkeypatch.delenv("CSLM_BASE_LM_BASE_URL", raising=False)
    monkeypatch.delenv("CSLM_BASE_LM_MODEL", raising=False)
    adapter = select_adapter()
    assert adapter.model_id == DEFAULT_MODEL
    assert getattr(adapter, "base_url") == DEFAULT_BASE_URL


def test_mock_adapter_still_used_when_requested(monkeypatch) -> None:
    monkeypatch.setenv("CSLM_ADAPTER", "mock")
    adapter = select_adapter(draft_text="Water is H2O.")
    assert isinstance(adapter, MockAdapter)


def test_dotenv_does_not_override_real_env(tmp_path, monkeypatch) -> None:
    from envload import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("CSLM_BASE_LM_MODEL=should-not-win\n", encoding="utf-8")
    monkeypatch.setenv("CSLM_BASE_LM_MODEL", "already-set")
    load_dotenv(env_file)
    assert os.environ["CSLM_BASE_LM_MODEL"] == "already-set"
