
import json
from pathlib import Path
from src.agents import eval_batch as eb

scenarios = json.loads(eb.SCENARIOS.read_text())

for policy in ("escalate", "stricter"):
    print(f"\n{'=' * 20} POLICY: {policy} {'=' * 20}")

    rows = eb.run_all(policy, "stub", scenarios)
    metrics = eb.metrics(rows)

    print("\nMETRICS:")
    for key, value in metrics.items():
        print(f"{key}: {value}")

    print("\nSCENARIO RESULTS:")
    for row in rows:
        status = "PASS" if row["ok"] else "FAIL"
        print(
            f'{status} | {row["id"]} | '
            f'Expected: {row["expected"]} | '
            f'Actual: {row["route"]} | '
            f'Citations: {row.get("citations", [])}'
        )
