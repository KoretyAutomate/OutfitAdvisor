"""local_llm.endpoint(): the model comes from models.toml, never from code or .env."""
import asyncio
import logging

import httpx
import pytest

import llm
import local_llm


def _write(tmp_path, body):
    p = tmp_path / "models.toml"
    p.write_text(body)
    return p


def test_reads_the_tier_and_builds_the_chat_url(monkeypatch, tmp_path):
    p = _write(tmp_path, '[smart]\nbase_url = "http://h:1/v1/"\nmodel = "m/x"\nvision = true\n')
    monkeypatch.setenv("LOCAL_LLM_CONFIG", str(p))
    assert local_llm.endpoint() == ("http://h:1/v1/chat/completions", "m/x")


def test_an_edit_takes_effect_without_a_restart(monkeypatch, tmp_path):
    p = _write(tmp_path, '[smart]\nbase_url = "http://h/v1"\nmodel = "a"\nvision = true\n')
    monkeypatch.setenv("LOCAL_LLM_CONFIG", str(p))
    assert local_llm.endpoint()[1] == "a"
    p.write_text('[smart]\nbase_url = "http://h/v1"\nmodel = "b"\nvision = true\n')
    assert local_llm.endpoint()[1] == "b"


@pytest.mark.parametrize("body", [None, "not = [toml", '[fast]\nmodel = "m"\n',
                                  '[smart]\nbase_url = "http://h/v1"\nmodel = "m"\n'])
def test_missing_broken_or_text_only_config_is_an_error_naming_the_file(monkeypatch, tmp_path, body):
    p = tmp_path / "models.toml"
    if body is not None:
        p.write_text(body)
    monkeypatch.setenv("LOCAL_LLM_CONFIG", str(p))
    with pytest.raises(local_llm.LocalLLMConfigError, match="models.toml"):
        local_llm.endpoint()


def test_chat_falls_back_instead_of_crashing_when_config_is_unusable(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("LOCAL_LLM_CONFIG", str(tmp_path / "absent.toml"))
    with caplog.at_level(logging.WARNING, logger="outfit.llm"):
        assert asyncio.run(llm._chat([{"role": "user", "content": "hi"}], max_tokens=5)) is None
    assert "config unusable" in caplog.text


class _Models:
    """Stands in for httpx.AsyncClient answering GET /v1/models."""
    def __init__(self, status=200, ids=(), boom=False):
        self.status, self.ids, self.boom, self.urls = status, ids, boom, []

    def __call__(self, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        self.urls.append(url)
        if self.boom:
            raise OSError("connection refused")
        req = httpx.Request("GET", url)
        return httpx.Response(self.status, json={"data": [{"id": i} for i in self.ids]}, request=req)


def test_serving_means_the_configured_model_is_listed(monkeypatch):
    fake = _Models(ids=["test/vision-model"])
    monkeypatch.setattr(local_llm.httpx, "AsyncClient", fake)
    assert asyncio.run(local_llm.serving()) is True
    assert fake.urls == ["http://127.0.0.1:9/v1/models"]


def test_vllm_up_with_another_model_is_not_serving(monkeypatch):
    """The 2026-10-15 failure: 200 on /models, 404 on every chat call."""
    monkeypatch.setattr(local_llm.httpx, "AsyncClient", _Models(ids=["Intel/Qwen3.5-122B-A10B-int4-AutoRound"]))
    assert asyncio.run(local_llm.serving()) is False


@pytest.mark.parametrize("fake", [_Models(boom=True), _Models(status=503, ids=["test/vision-model"])])
def test_vllm_down_is_not_serving(monkeypatch, fake):
    monkeypatch.setattr(local_llm.httpx, "AsyncClient", fake)
    assert asyncio.run(local_llm.serving()) is False


def test_unusable_config_is_not_serving(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_LLM_CONFIG", str(tmp_path / "absent.toml"))
    assert asyncio.run(local_llm.serving()) is False
