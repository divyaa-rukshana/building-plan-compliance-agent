"""One interface in front of the model, so the provider changes by configuration (brief section 12).

- LLM_API_BASE (or LLM_BASE_URL) empty -> LocalStubLLM (fixed answers, no network).
- set -> OpenAI-style chat completions over HTTP, with a timeout on every call. The team's stub-llm service
  (src/stub_llm.py) is "http://stub-llm:8001": path /v1/chat/completions, request body needs a `prompt` field.
  So while LLM_MODEL is unset (stub) the request carries `prompt` as well as `messages`; with a real provider
  (LLM_MODEL set) it is a standard chat request only, because real providers reject unknown fields.
Member 1 wraps `call` with the circuit breaker via `resilience`. Failures raise LLMUnavailable.
"""
import json
import time
from typing import Callable, Dict, List, Optional

import httpx

from .config import Settings
from .cost import estimate_tokens


class LLMUnavailable(Exception):
    pass


class LLMReply:
    def __init__(self, text: str, prompt_tokens: int, completion_tokens: int, estimated: bool, model: str):
        self.text, self.prompt_tokens, self.completion_tokens = text, prompt_tokens, completion_tokens
        self.estimated, self.model = estimated, model


class LocalStubLLM:
    """Deterministic stand-in. `replies` lets tests script answers; otherwise returns a neutral sentence."""

    def __init__(self, replies: Optional[List[str]] = None, model: str = "local-stub", delay_s: float = 0.0):
        self.replies = list(replies or [])
        self.model = model
        self.delay_s = delay_s
        self.calls: List[List[Dict]] = []

    def complete(self, messages: List[Dict], step: str) -> LLMReply:
        self.calls.append(messages)
        if self.delay_s:
            time.sleep(self.delay_s)
        text = self.replies.pop(0) if self.replies else \
            "Findings were gathered from the cited provisions; see each finding for its limit and clause."
        p = sum(estimate_tokens(m["content"]) for m in messages)
        return LLMReply(text, p, estimate_tokens(text), True, self.model)


class HttpLLM:
    def __init__(self, s: Settings, resilience: Optional[Callable] = None):
        self.s = s
        self.model = s.llm_model
        self.resilience = resilience

    def _url(self) -> str:
        base = self.s.llm_base_url.rstrip("/")
        return base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")

    def _body(self, messages):
        body = {"messages": messages, "temperature": 0}
        if self.s.llm_model:
            body["model"] = self.s.llm_model
        else:   # team stub: PromptRequest(prompt: str)
            body["prompt"] = "\n\n".join(m["content"] for m in messages)
        return body

    def _call(self, messages):
        headers = {"Content-Type": "application/json"}
        if self.s.llm_api_key:
            headers["Authorization"] = f"Bearer {self.s.llm_api_key}"
        try:
            r = httpx.post(self._url(), headers=headers, content=json.dumps(self._body(messages)),
                           timeout=self.s.llm_timeout_s)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LLMUnavailable(str(e)) from e

    def complete(self, messages: List[Dict], step: str) -> LLMReply:
        data = self.resilience(lambda: self._call(messages)) if self.resilience else self._call(messages)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMUnavailable("malformed provider response") from e
        u = data.get("usage") or {}
        if "prompt_tokens" in u and "completion_tokens" in u:
            return LLMReply(text, int(u["prompt_tokens"]), int(u["completion_tokens"]), False, self.model)
        p = sum(estimate_tokens(m["content"]) for m in messages)
        return LLMReply(text, p, estimate_tokens(text), True, self.model)


def make_llm(s: Settings, resilience: Optional[Callable] = None):
    return HttpLLM(s, resilience) if s.llm_base_url else LocalStubLLM()
