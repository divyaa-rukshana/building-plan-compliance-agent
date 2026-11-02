"""All environment-specific settings. Nothing here is a secret or a model name (D4)."""
import os
from dataclasses import dataclass


def _f(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def _i(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return int(default)


@dataclass(frozen=True)
class Settings:
    llm_base_url: str      # empty -> built-in local stub LLM
    llm_api_key: str
    llm_model: str
    llm_timeout_s: float
    price_prompt_per_1k: float       # currency units per 1000 prompt tokens (0 for free tier)
    price_completion_per_1k: float
    prompt_version: str              # folder under agents/prompts
    planner: str                     # "rule" or "llm"
    max_steps: int                   # researcher loop iterations
    max_tool_calls: int
    max_wall_s: float
    verify_retries: int
    conflict_policy: str             # escalate | stricter | bylaws | rmp
    corpus_backend: str              # stub | chroma | http
    corpus_api_url: str              # empty -> built-in stub corpus (dev only)


def get_settings() -> Settings:
    e = os.environ.get
    return Settings(
        llm_base_url=e("LLM_API_BASE") or e("LLM_BASE_URL", ""),   # LLM_API_BASE is the name docker-compose.yml already sets
        llm_api_key=e("LLM_API_KEY", ""),
        llm_model=e("LLM_MODEL", ""),
        llm_timeout_s=_f("LLM_TIMEOUT_S", 20),
        price_prompt_per_1k=_f("PRICE_PROMPT_PER_1K", 0.0015),
        price_completion_per_1k=_f("PRICE_COMPLETION_PER_1K", 0.0020),
        prompt_version=e("PROMPT_VERSION", "v1"),
        planner=e("AGENT_PLANNER", "rule"),
        max_steps=_i("AGENT_MAX_STEPS", 20),
        max_tool_calls=_i("AGENT_MAX_TOOL_CALLS", 20),
        max_wall_s=_f("AGENT_MAX_WALL_S", 60),
        verify_retries=_i("AGENT_VERIFY_RETRIES", 1),
        conflict_policy=e("CONFLICT_POLICY", "escalate"),
        corpus_backend=e("CORPUS_BACKEND", "stub").lower(),
        corpus_api_url=e("CORPUS_API_URL", ""),
    )
