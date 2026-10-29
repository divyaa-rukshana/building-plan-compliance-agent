
import csv
import json
import time
from pathlib import Path

from src.retrieval import search_corpus


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_FILE = ROOT / "evaluation" / "scenarios.json"
REPORT_FILE = ROOT / "evaluation" / "retrieval_report.csv"


def main():
    with SCENARIOS_FILE.open("r", encoding="utf-8") as file:
        scenarios = json.load(file)

    report = []
    total_results = 0
    queries_with_results = 0
    queries_with_clause_ids = 0
    total_seconds = 0.0

    for scenario in scenarios:
        query = scenario["query"]
        start = time.perf_counter()

        try:
            results = search_corpus(query, k=3)
            elapsed = time.perf_counter() - start
            error = ""
        except Exception as exc:
            results = []
            elapsed = time.perf_counter() - start
            error = str(exc)

        has_results = bool(results)
        has_clause_id = any(
            result.get("clause_id") for result in results
        )

        queries_with_results += int(has_results)
        queries_with_clause_ids += int(has_clause_id)
        total_results += len(results)
        total_seconds += elapsed

        report.append({
            "scenario_id": scenario["id"],
            "query": query,
            "results_count": len(results),
            "has_results": has_results,
            "has_clause_id": has_clause_id,
            "latency_seconds": round(elapsed, 4),
            "top_source": results[0]["source"] if results else "",
            "top_page": results[0]["page"] if results else "",
            "error": error,
        })

        print(
            f'{scenario["id"]:02d}/{len(scenarios)} | '
            f'{elapsed:.2f}s | '
            f'{len(results)} results | {query}'
        )

    with REPORT_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=report[0].keys())
        writer.writeheader()
        writer.writerows(report)

    count = len(scenarios)

    print("\n--- Retrieval Evaluation Summary ---")
    print(f"Total scenarios: {count}")
    print(
        f"Queries returning results: {queries_with_results}/{count} "
        f"({queries_with_results / count:.1%})"
    )
    print(
        f"Queries with a clause ID in top 3: "
        f"{queries_with_clause_ids}/{count} "
        f"({queries_with_clause_ids / count:.1%})"
    )
    print(f"Average results per query: {total_results / count:.2f}")
    print(f"Average query time: {total_seconds / count:.2f} seconds")
    print(f"CSV report saved to: {REPORT_FILE}")


if __name__ == "__main__":
    main()
