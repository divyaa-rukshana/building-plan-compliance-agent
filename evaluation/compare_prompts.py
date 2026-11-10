
from pathlib import Path
import difflib
import csv

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "src" / "agents" / "prompts"
OUTPUT = ROOT / "evaluation"

files = ["planner.txt", "summary.txt"]
rows = []
report = []

for filename in files:
    v1_path = PROMPT_DIR / "v1" / filename
    v2_path = PROMPT_DIR / "v2" / filename

    v1 = v1_path.read_text(encoding="utf-8")
    v2 = v2_path.read_text(encoding="utf-8")

    diff = list(difflib.unified_diff(
        v1.splitlines(),
        v2.splitlines(),
        fromfile=f"V1/{filename}",
        tofile=f"V2/{filename}",
        lineterm=""
    ))

    similarity = difflib.SequenceMatcher(
        None, v1, v2
    ).ratio() * 100

    added = sum(
        1 for line in diff
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff
        if line.startswith("-") and not line.startswith("---")
    )

    rows.append({
        "prompt": filename,
        "v1_words": len(v1.split()),
        "v2_words": len(v2.split()),
        "v1_characters": len(v1),
        "v2_characters": len(v2),
        "similarity_percent": round(similarity, 2),
        "lines_added": added,
        "lines_removed": removed
    })

    report.append(f"\n## {filename}\n")
    report.append(
        f"- V1 words: {len(v1.split())}\n"
        f"- V2 words: {len(v2.split())}\n"
        f"- Similarity: {similarity:.2f}%\n"
        f"- Lines added in V2: {added}\n"
        f"- Lines removed from V1: {removed}\n"
    )
    report.append("\n### Changes\n")
    report.extend(line + "\n" for line in diff)

OUTPUT.mkdir(exist_ok=True)

with open(OUTPUT / "prompt_comparison.csv", "w",
          newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

(OUTPUT / "prompt_comparison.md").write_text(
    "# Prompt Version Comparison\n" + "".join(report),
    encoding="utf-8"
)

print("Prompt comparison completed!")
print("Created evaluation/prompt_comparison.csv")
print("Created evaluation/prompt_comparison.md")

for row in rows:
    print(row)
