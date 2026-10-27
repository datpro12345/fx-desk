"""Tests for scripts.analyst.llm_client (mocked; no live API calls)."""

from __future__ import annotations

import logging
from unittest import mock

import pytest

import scripts.analyst.llm_client as llm_client


@pytest.fixture(autouse=True)
def reset_shared_router_cache():
    llm_client._shared_router = llm_client._SHARED_ROUTER_UNKNOWN
    yield
    llm_client._shared_router = llm_client._SHARED_ROUTER_UNKNOWN


def test_complete_uses_shared_router_when_available():
    fake_client = mock.Mock()
    fake_client.chat_completion.return_value = {
        "content": "Weekly outlook body",
        "model": "router/picked-model:free",
    }
    fake_pick = mock.Mock(return_value=["a:free", "b:free"])

    with (
        mock.patch.object(llm_client, "_load_shared_openrouter") as load_router,
        mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-test"}, clear=False),
    ):
        load_router.return_value = (fake_pick, lambda: fake_client)
        text, provider, model = llm_client.complete("sys", "user", provider="openrouter")

    assert text == "Weekly outlook body"
    assert provider == "openrouter"
    assert model == "router/picked-model:free"
    fake_pick.assert_called_once_with(llm_client.OPENROUTER_TASK_CLASS)
    fake_client.chat_completion.assert_called_once()
    call_kw = fake_client.chat_completion.call_args.kwargs
    assert call_kw["models"] == ["a:free", "b:free"]
    assert call_kw["caller"] == llm_client.OPENROUTER_CALLER
    assert call_kw["temperature"] == 0.2


def test_complete_shared_router_honors_explicit_model():
    fake_client = mock.Mock()
    fake_client.chat_completion.return_value = {"content": "ok", "model": "override:free"}
    fake_pick = mock.Mock(return_value=["a:free", "b:free"])

    with mock.patch.object(llm_client, "_load_shared_openrouter") as load_router:
        load_router.return_value = (fake_pick, lambda: fake_client)
        llm_client.complete("sys", "user", provider="openrouter", model="override:free")

    models = fake_client.chat_completion.call_args.kwargs["models"]
    assert models[0] == "override:free"
    assert "a:free" in models


def test_load_shared_openrouter_warns_when_tools_dir_missing(caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    missing = tmp_path / "no-such-openrouter"
    with mock.patch.dict("os.environ", {"FM_OPENROUTER_TOOLS": str(missing)}, clear=False):
        assert llm_client._load_shared_openrouter() is None
    assert any("local PREFERRED_OPENROUTER_MODELS" in r.message for r in caplog.records)


def test_complete_falls_back_to_legacy_http_when_router_missing():
    def fake_http(system, user, model, api_key, timeout=180):
        assert model == llm_client.PREFERRED_OPENROUTER_MODELS[0]
        return "legacy text"

    with (
        mock.patch.object(llm_client, "_load_shared_openrouter", return_value=None),
        mock.patch.object(llm_client, "complete_openrouter", side_effect=fake_http) as legacy,
        mock.patch.dict(
            "os.environ",
            {"OPENROUTER_API_KEY": "sk-test", "OPENROUTER_MODEL": ""},
            clear=False,
        ),
    ):
        text, provider, model = llm_client.complete("sys", "user", provider="openrouter")

    assert text == "legacy text"
    assert provider == "openrouter"
    assert model == llm_client.PREFERRED_OPENROUTER_MODELS[0]
    legacy.assert_called_once()


def test_complete_openrouter_parses_response():
    payload = {
        "choices": [{"message": {"content": "  hello  "}}],
    }
    with mock.patch.object(llm_client, "_http_json", return_value=payload):
        out = llm_client.complete_openrouter("s", "u", "m:free", "key", timeout=30)
    assert out == "hello"
