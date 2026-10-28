import re
from typing import Tuple

INJECTION_PATTERNS = [
    r"ignore\s+all\s+previous",
    r"bypass\s+compliance",
    r"override\s+setback",
    r"system\s+override",
    r"respond\s+only\s+as",
    r"you\s+are\s+now\s+certified",
    r"force\s+clear"
]

TOXICITY_KEYWORDS = ["fraud", "bribe", "corrupt", "fake", "cheat", "scam"]

def scan_text_field_guardrail(text: str) -> Tuple[bool, str]:
    """Executes structural regex parsing and keyword audits against raw input text fields (L4)."""
    if not text:
        return True, "Passed"
        
    cleaned_text = text.lower().strip()
    
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned_text):
            return False, f"Prompt injection vector pattern discovered mapping signature: '{pattern}'"
            
    for keyword in TOXICITY_KEYWORDS:
        if keyword in cleaned_text:
            return False, f"Prohibited toxic phrase context discovered: '{keyword}'"
            
    return True, "Passed"

def filter_output_determination_token(output_routing: str, all_passed: bool) -> str:
    """Boundary output scanner that handles unauthorized clearance codes (L4)."""
    if output_routing == "clear-for-submission" and not all_passed:
        return "specialist-review"
    return output_routing
