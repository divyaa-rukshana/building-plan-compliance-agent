
import json
from src.agents import eval_batch as eb
from src.schemas import BuildingProposalRequest

scenarios = json.loads(eb.SCENARIOS.read_text())

print("\n========== INPUT VALIDATION ==========")

for s in scenarios:
    try:
        BuildingProposalRequest(**s["proposal"])
    except Exception as e:
        print(f'\n{s["id"]} - {s["name"]}')
        print(e)

print("\n========== POLICY COMPARISON ==========")

for policy in ("escalate", "stricter"):
    print(f"\n--- {policy.upper()} ---")
    rows = eb.run_all(policy, "stub", scenarios)

    for r in rows:
        print(
            r["id"],
            "| Expected:", r["expected"],
            "| Actual:", r["route"],
            "| PASS:", r["ok"]
        )

    print("Metrics:", eb.metrics(rows))
