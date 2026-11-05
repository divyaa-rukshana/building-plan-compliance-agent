import httpx
import pytest

from src.agents.cases import CASES
from src.agents.config import get_settings
from src.agents.llm import HttpLLM, LLMUnavailable, make_llm, LocalStubLLM
from src.agents.worker import run_proposal


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)
    def json(self):
        return self._d


def settings(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://provider.test/v1")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    monkeypatch.setenv("LLM_API_KEY", "k")
    return get_settings()


def test_no_base_url_uses_local_stub():
    assert isinstance(make_llm(get_settings()), LocalStubLLM)


def test_http_llm_reads_provider_usage_and_sets_timeout(monkeypatch):
    seen = {}
    def fake_post(url, headers=None, content=None, timeout=None):
        seen.update(url=url, timeout=timeout, auth=headers.get("Authorization"))
        return Resp({"choices": [{"message": {"content": "hello 0.75"}}], "usage": {"prompt_tokens": 11, "completion_tokens": 3}})
    monkeypatch.setattr(httpx, "post", fake_post)
    r = HttpLLM(settings(monkeypatch)).complete([{"role": "user", "content": "hi"}], "summary")
    assert (r.prompt_tokens, r.completion_tokens, r.estimated) == (11, 3, False)
    assert seen["timeout"] == 20 and seen["url"].endswith("/chat/completions") and seen["auth"] == "Bearer k"


def test_provider_errors_become_llm_unavailable(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectTimeout("slow")
    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(LLMUnavailable):
        HttpLLM(settings(monkeypatch)).complete([{"role": "user", "content": "x"}], "summary")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp({"unexpected": 1}))
    with pytest.raises(LLMUnavailable):
        HttpLLM(settings(monkeypatch)).complete([{"role": "user", "content": "x"}], "summary")


def test_resilience_wrapper_is_used(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp({"choices": [{"message": {"content": "ok"}}]}))
    def wrap(fn):
        calls.append(1)
        return fn()
    r = HttpLLM(settings(monkeypatch), resilience=wrap).complete([{"role": "user", "content": "x"}], "s")
    assert calls == [1] and r.estimated


def test_provider_down_in_a_full_run_degrades_and_escalates(monkeypatch):
    settings(monkeypatch)
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    def boom(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "post", boom)
    r = run_proposal(CASES["ex1"])
    assert r["degraded"] and r["route"] == "specialist-review" and r["findings"] and not r["summary"].startswith("The")
