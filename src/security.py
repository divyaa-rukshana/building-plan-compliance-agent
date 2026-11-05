"""L4 guardrails for free-text fields and for the system's own output.

Three jobs:
  1. screen_input / scan_text_field_guardrail : reject prompt-injection and toxic text BEFORE any agent, tool or model sees it
  2. filter_output / find_determinations      : stop generated text from issuing a determination the system may not make
  3. filter_output_determination_token        : stop a routing code of "clear-for-submission" that the evidence does not support

Honest limits: the screens are pattern and lexicon based, so a novel phrasing can pass. The real protection is structural:
numbers come from a rule engine, every citation is verified against retrieved text, and a clear route needs checked findings.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple

MAX_FREE_TEXT = 2000

# (id, regex). Matching runs on text that is NFKC-normalised, zero-width-stripped, lower-cased and whitespace-collapsed.
INJECTION_PATTERNS: List[Tuple[str, str]] = [
    ("I01", r"ignore (all |any |the |your )?(previous|prior|above|earlier) (instructions?|prompts?|rules?|messages?)"),
    ("I02", r"ignore\s+all\s+previous"),
    ("I03", r"disregard (all |any |the |your )?(previous|prior|above|earlier|system)"),
    ("I04", r"forget (everything|all|your) (instructions?|rules?|above)"),
    ("I05", r"(reveal|show|print|repeat|output) (me )?(your |the )?(system |hidden |initial )?(prompt|instructions)"),
    ("I06", r"\byou are now\b"),
    ("I07", r"\bact as (a |an |the )?(officer|inspector|authority|approver|system|assistant|admin|administrator|developer|certifier|judge|municipal|sanctioning)"),
    ("I08", r"\bpretend (to be|you are)\b"),
    ("I09", r"\b(follow|use|apply|obey) (these |the following |my )?new (instructions?|rules?)\b|\bnew role\b"),
    ("I10", r"\bsystem (prompt|message|override)\b"),
    ("I11", r"</?(system|assistant|tool|instructions?)>"),
    ("I12", r"\bdeveloper mode\b|\bjailbreak\b|\bdo anything now\b"),
    ("I13", r"(mark|declare|certify|approve|state|say|call) (this|the|my) (plan|building|proposal|drawing)[^.]{0,30}(compliant|approved|complies|clear)"),
    ("I14", r"(route|set the route|return|output) (it |this )?(to|as) (clear-for-submission|clear for submission)"),
    ("I15", r"override (the )?(verification|checks?|guardrails?|filters?|setbacks?)"),
    ("I16", r"skip (the )?(verification|checks?|validation)"),
    ("I17", r"bypass (the )?(compliance|verification|checks?|guardrails?|filters?)"),
    ("I18", r"respond only as\b|you are now certified|force clear"),
]
_INJ = [(i, re.compile(p)) for i, p in INJECTION_PATTERNS]

# integrity terms chosen by the team plus abusive language; matched as whole words (so "bypass road" or "faker street" pass)
TOXICITY_KEYWORDS = ["fraud", "bribe", "corrupt", "fake", "cheat", "scam", "idiot", "stupid", "moron", "shut up",
                     "scum", "bastard", "kill you", "hate you", "fuck", "shit", "bitch", "asshole"]
_TOX = [(w, re.compile(rf"\b{re.escape(w)}\b")) for w in TOXICITY_KEYWORDS]

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH)
    return re.sub(r"\s+", " ", t).strip().lower()


@dataclass
class ScreenResult:
    ok: bool
    reasons: List[str] = field(default_factory=list)      # generic labels with a rule id; never the matched text


def screen_injection(text: str) -> ScreenResult:
    t = normalize(text)
    reasons = []
    if len(text or "") > MAX_FREE_TEXT:
        reasons.append("free text too long")
    reasons += [f"prompt-injection pattern detected ({i})" for i, rx in _INJ if rx.search(t)]
    return ScreenResult(not reasons, reasons)


def screen_toxicity(text: str) -> ScreenResult:
    t = normalize(text)
    hit = any(rx.search(t) for _, rx in _TOX)
    return ScreenResult(not hit, ["toxic or prohibited language detected"] if hit else [])


def screen_input(*fields: str) -> ScreenResult:
    """Screen every free-text field of a proposal. One bad field rejects the proposal."""
    reasons: List[str] = []
    for f in fields:
        if not f:
            continue
        for r in (screen_injection(f), screen_toxicity(f)):
            reasons += r.reasons
    return ScreenResult(not reasons, list(dict.fromkeys(reasons)))


def scan_text_field_guardrail(text: str) -> Tuple[bool, str]:
    """Team-facing API (unchanged signature): (passed, reason)."""
    r = screen_input(text or "")
    return (True, "Passed") if r.ok else (False, "; ".join(r.reasons))


# ------------------------------------------------------------------ output side
_DETERMINATION = re.compile(
    r"\b(non-?compliant|compliant|complies|complying|compliance (is )?(confirmed|achieved)|approved?|approval granted|"
    r"certif(y|ies|ied|ication)|guarantee[sd]?|sanction(ed)? (is )?granted|passes? (all )?(checks|bye-?laws)|"
    r"safe to build|legal|illegal)\b", re.I)


def find_determinations(text: str) -> List[str]:
    return [m.group(0) for m in _DETERMINATION.finditer(text or "")]


def filter_output(text: str, fallback: str) -> Tuple[str, List[str]]:
    """Generated narrative that contains a determination word is replaced by `fallback`."""
    v = find_determinations(text)
    if v or not (text or "").strip():
        return fallback, v
    return text, []


def filter_output_determination_token(output_routing: str, all_passed: bool, checked_findings: int = 1) -> str:
    """A clear-for-submission code is allowed only when every check passed AND at least one check was actually made.
    (The earlier version cleared a proposal for which no check had run.)"""
    if output_routing == "clear-for-submission" and (not all_passed or checked_findings < 1):
        return "specialist-review"
    return output_routing
