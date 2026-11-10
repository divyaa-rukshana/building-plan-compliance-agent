
import csv
import json
import statistics
import sys
import time
from pathlib import Path

# Add project root to Python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval import search_corpus

SCENARIOS_FILE = ROOT / "evaluation" / "scenarios.json"
REPORT_FILE = ROOT / "evaluation" / "retrieval_report.csv"

TOP_K = 5


def load_scenarios():
    """Load the predefined evaluation queries."""
    with open(SCENARIOS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def evaluate():
    scenarios = load_scenarios()

    if not scenarios:
        raise ValueError("No evaluation scenarios found.")

    print("=" * 60)
    print("BUILDING REGULATION RETRIEVAL EVALUATION")
    print("=" * 60)

    # Warm up the model and retrieval pipeline.
    # This prevents first-time model loading from distorting
    # individual query latency measurements.
    print("\nWarming up retrieval pipeline...")
    search_corpus("building regulations", k=TOP_K)

    results = []
    latencies = []

    for scenario in scenarios:
        query_id = scenario["id"]
        query = scenario["query"]

        start_time = time.perf_counter()
        retrieved = search_corpus(query, k=TOP_K)
        latency = (time.perf_counter() - start_time) * 1000

        latencies.append(latency)

        top1 = retrieved[0] if retrieved else {}

        # Keep all top-5 retrieval results for later
        # manual relevance verification.
        top5_details = [
            {
                "rank": rank,
                "source": item["source"],
                "page": item["page"],
                "chunk_index": item["chunk_index"],
                "clause_id": item["clause_id"],
                "distance": item["distance"],
                "text": item["text"],
            }
            for rank, item in enumerate(retrieved, start=1)
        ]

        results.append({
            "query_id": query_id,
            "query": query,
            "retrieved_count": len(retrieved),
            "top1_source": top1.get("source", ""),
            "top1_page": top1.get("page", ""),
            "top1_clause_id": top1.get("clause_id") or "",
            "top1_distance": top1.get("distance", ""),
            "latency_ms": round(latency, 3),
            "top5_results": json.dumps(
                top5_details,
                ensure_ascii=False
            ),
            # These fields will be filled after manual relevance checks.
            "expected_source": "",
            "expected_clause": "",
            "relevant_in_top5": "",
            "first_relevant_rank": "",
        })

        print(
            f"[{query_id:02d}/{len(scenarios)}] "
            f"{query[:45]:45} | "
            f"{latency:.2f} ms | "
            f"{len(retrieved)} results"
        )

    # Write the complete evaluation report.
    fieldnames = [
        "query_id",
        "query",
        "retrieved_count",
        "top1_source",
        "top1_page",
        "top1_clause_id",
        "top1_distance",
        "latency_ms",
        "top5_results",
        "expected_source",
        "expected_clause",
        "relevant_in_top5",
        "first_relevant_rank",
    ]

    with open(REPORT_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Print performance summary.
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)

    print(f"Total queries:       {len(scenarios)}")
    print(f"Successful queries:  {sum(r['retrieved_count'] > 0 for r in results)}")
    print(f"Average latency:     {statistics.mean(latencies):.3f} ms")
    print(f"Median latency:      {statistics.median(latencies):.3f} ms")
    print(f"Minimum latency:     {min(latencies):.3f} ms")
    print(f"Maximum latency:     {max(latencies):.3f} ms")

    print(f"\nReport saved to: {REPORT_FILE}")

    print(
        "\nNOTE: Relevance metrics are pending manual verification "
        "of expected clauses and source documents."
    )


if __name__ == "__main__":
    evaluate()
