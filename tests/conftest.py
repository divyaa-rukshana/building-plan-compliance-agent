import pytest

ENV = ("LLM_BASE_URL", "LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL", "CORPUS_API_URL", "CORPUS_BACKEND", "AGENT_PLANNER",
       "CONFLICT_POLICY", "AGENT_MAX_STEPS", "AGENT_MAX_TOOL_CALLS", "AGENT_MAX_WALL_S", "PROMPT_VERSION",
       "PRICE_PROMPT_PER_1K", "PRICE_COMPLETION_PER_1K")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
