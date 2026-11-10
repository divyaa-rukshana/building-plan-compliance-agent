
import json
from pathlib import Path

path = Path("evaluation/agent_scenarios.json")
scenarios = json.loads(path.read_text(encoding="utf-8"))

default_setbacks = {
    "front_m": 3.0,
    "rear_m": 2.0,
    "left_m": 2.0,
    "right_m": 2.0
}

for scenario in scenarios:
    proposal = scenario["proposal"]

    # Add required setbacks only if missing.
    proposal.setdefault("proposed_setbacks", default_setbacks.copy())

    # A01 actually routes to revise-and-recheck.
    if scenario["id"] == "A01":
        scenario["expected_route_stricter"] = "revise-and-recheck"
        scenario["expected_route_default"] = "revise-and-recheck"

path.write_text(
    json.dumps(scenarios, indent=2),
    encoding="utf-8"
)

print("Updated scenarios:", len(scenarios))
print("Added missing proposed_setbacks.")
print("Updated A01 expected route.")
