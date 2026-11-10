
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "evaluation" / "retrieval_report.csv"
OUTPUT = ROOT / "evaluation" / "retrieval_audit.txt"

with open(REPORT, "r", encoding="utf-8-sig") as file:
    rows = list(csv.DictReader(file))

with open(OUTPUT, "w", encoding="utf-8") as file:
    for row in rows:
        file.write("\n" + "=" * 90 + "\n")
        file.write(f"QUERY {row['query_id']}: {row['query']}\n")
        file.write("=" * 90 + "\n")

        results = json.loads(row["top5_results"])

        for result in results:
            file.write(
                f"\nRank: {result['rank']}\n"
                f"Source: {result['source']}\n"
                f"PDF Page: {result['page']}\n"
                f"Chunk: {result['chunk_index']}\n"
                f"Clause: {result['clause_id']}\n"
                f"Cosine Distance: {result['distance']}\n"
                f"Text:\n{result['text']}\n"
            )
            file.write("-" * 70 + "\n")

print(f"Audit file created: {OUTPUT}")
print(f"Queries inspected: {len(rows)}")
print("Total retrieved chunks:", sum(
    len(json.loads(row["top5_results"])) for row in rows
))
