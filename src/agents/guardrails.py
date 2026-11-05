"""L4: prompt-injection screen, toxicity check, output filter.

Honest limits: the screen is pattern based, so it catches common attacks and not clever ones;
the toxicity check is a small lexicon (swap in a model via TOXICITY_BACKEND later).
The real protection is structural: numbers come from the rule engine, citations are verified,
and the output filter makes a determination impossible to issue.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List

MAX_FREE_TEXT = 2000

_INJECTION = [
    r"ignore (all |any |the |your )?(previous|prior|above|earlier) (instructions?|prompts?|rules?)",
    r"disregard (all |any |the |your )?(previous|prior|above|earlier|system)",
    r"forget (everything|all|your) (instructions?|rules?|above)",
    r"(reveal|show|print|repeat|output) (me )?(your |the )?(system |hidden |initial )?(prompt|instructions)",
    r"you are now\b", r"\bact as\b", r"\bpretend (to be|you are)\b", r"new (instructions?|rules?|role)\b",
    r"\bsystem (prompt|message|override)\b", r"</?(system|assistant|tool|instructions?)>",
    r"\bdeveloper mode\b", r"\bjailbreak\b", r"\bdo anything now\b",
    r"(mark|declare|certify|approve|state|say|call) (this|the|my) (plan|building|proposal|drawing)[^.]{0,30}(compliant|approved|complies|clear)",
    r"(route|set the route|return|output) (it |this )?(to|as) (clear-for-submission|clear for submission)",
    r"override (the )?(verification|checks?|guardrails?|filters?)",
    r"skip (the )?(verification|checks?|validation)",
    r"call (the )?(tool|function)\b.*\b(with|using)\b",
]
_INJ_RE = [re.compile(p, re.I) for p in _INJECTION]

_TOXIC = {
    "idiot", "stupid", "moron", "dumb", "shut up", "scum", "bastard", "damn you", "hate you", "kill you",
    "fuck", "shit", "bitch", "asshole", "retard",
}

_ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).translate(_ZW)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class ScreenResult:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    clean_text: str = ""


def screen_injection(text: str) -> ScreenResult:
    t = normalize(text)
    reasons = []
    if len(text) > MAX_FREE_TEXT:
        reasons.append("free text too long")
    for rx in _INJ_RE:
        if rx.search(t):
            reasons.append("prompt-injection pattern detected")
    return ScreenResult(not reasons, reasons, t)


def screen_toxicity(text: str) -> ScreenResult:
    t = normalize(text).lower()
    hits = [w for w in _TOXIC if re.search(rf"\b{re.escape(w)}\b", t)]
    return ScreenResult(not hits, [f"toxic language detected" for w in hits], t)


def screen_input(*fields: str) -> ScreenResult:
    """Screen every free-text field (use, notes) before any model or tool sees it."""
    reasons: List[str] = []
    for f in fields:
        if not f:
            continue
        for r in (screen_injection(f), screen_toxicity(f)):
            reasons += r.reasons
    reasons = list(dict.fromkeys(reasons))
    return ScreenResult(not reasons, reasons, "")


# ---- output filter: the system may never issue a determination it is not authorised to make
_DETERMINATION = re.compile(
    r"\b(non-?compliant|compliant|complies|complying|compliance (is )?(confirmed|achieved)|approved?|approval granted|"
    r"certif(y|ies|ied|ication)|guarantee[sd]?|sanction(ed)? (is )?granted|passes? (all )?(checks|bye-?laws)|"
    r"safe to build|legal|illegal)\b", re.I)


def find_determinations(text: str) -> List[str]:
    return [m.group(0) for m in _DETERMINATION.finditer(text or "")]


def filter_output(text: str, fallback: str) -> tuple[str, List[str]]:
    """Return (safe_text, violations). Generated narrative that contains a determination is replaced."""
    v = find_determinations(text)
    if v or not text.strip():
        return fallback, v
    return text, []
