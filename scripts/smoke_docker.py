"""Smoke test for the running stack. Standard library only; run on the host after `docker compose up -d --build`.

    python scripts/smoke_docker.py                # one proposal
    python scripts/smoke_docker.py --n 9          # nine at once (shows the effect of --scale agent-worker=3)

Checks the whole path: API ingestion, queue, worker, agents, the stub LLM, ids, telemetry, and the two rejection paths.
Exit code 0 means every check passed.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
SAMPLE = {
    "land_use": "residential", "planning_area": "A", "plot_width_m": 20, "plot_depth_m": 30, "plot_area_sqm": 600,
    "abutting_road_width_m": 6, "proposed_height_m": 7.5, "proposed_floors": 2, "proposed_plinth_area_sqm": 360,
    "proposed_total_floor_area_sqm": 400, "proposed_setbacks": {"front_m": 5, "rear_m": 3.5, "left_m": 2.5, "right_m": 3.5}, "notes": "",
}


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach {url}: {e.reason}. Is the stack up (docker compose up -d --build)?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=120)
    a = ap.parse_args()
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

    print(f"1) submit {a.n} proposal(s)")
    t0 = time.time()
    ids = {}
    for _ in range(a.n):
        code, body = http("POST", a.base + "/proposals", SAMPLE)
        if code != 202:
            check("API accepted the proposal", False, f"HTTP {code} {body}")
            return 1
        ids[body["run_id"]] = body["correlation_id"]
    check("API returned 202, a run id and a correlation id for each", len(ids) == a.n and all(ids.values()), f"{time.time() - t0:.2f}s")

    print("2) poll GET /v1/compliance/status/{run_id}")
    done, t1 = {}, time.time()
    while len(done) < len(ids) and time.time() - t1 < a.timeout:
        for rid in ids:
            if rid not in done:
                code, s = http("GET", f"{a.base}/v1/compliance/status/{rid}")
                if code == 200 and s.get("status") in ("completed", "failed"):
                    done[rid] = s
        time.sleep(0.5)
    check("every run finished", len(done) == len(ids), f"{time.time() - t0:.1f}s for {len(ids)} run(s)")
    check("no run failed", all(s["status"] == "completed" for s in done.values()))
    if not done or any(s["status"] != "completed" for s in done.values()):
        return 1

    rid = next(iter(done))
    res = done[rid]["result"]
    print("3) result of the first run")
    print(f"     decision={res['decision']} outcome={res['outcome']} verified={res['verified']} degraded={res['degraded']}")
    print(f"     reason: {res['primary_reason'][:150]}")
    cites = {c["clause_id"] for f in res["findings"] for c in f["citations"]}
    t = res["telemetry"]
    check("result carries the API's run id and correlation id", res["run_id"] == rid and res["correlation_id"] == ids[rid])
    check("every trace event carries both ids", all(e["run_id"] == rid and e["correlation_id"] == ids[rid] for e in res["trace"]), f"{len(res['trace'])} events")
    check("findings exist and every one cites retrieved text", bool(res["findings"]) and all(f["citations"] for f in res["findings"]), f"{len(res['findings'])} findings")
    check("the 4.1 provisions were found and cited", {"BBMP2003/Table-4", "BBMP2003/Table-6", "BBMP2003/9.10.4", "RMP2015/4.1.2.ii.b"} <= cites)
    check("verified and not degraded", res["verified"] and not res["degraded"])
    check("model call went to the stub-llm service (provider token counts)", t["llm_calls"] == 1 and not t["tokens_estimated"],
          f"prompt={t['prompt_tokens']} completion={t['completion_tokens']}" if not t["tokens_estimated"] else
          "tokens are ESTIMATED: agent-worker has no LLM_API_BASE, or cannot reach stub-llm")
    check("cost recorded per step", bool(t["cost_by_step"]) and t["calculated_cost_usd"] > 0, f"{t['calculated_cost_usd']} USD, {t['cost_per_100_runs_estimate']} per 100 runs")
    check("corpus backend is stated", res["corpus_backend"] in ("stub", "chroma", "http"), res["corpus_backend"])

    print("4) rejection paths")
    code, _ = http("POST", a.base + "/proposals", {**SAMPLE, "plot_width_m": -1})
    check("malformed proposal rejected with 422", code == 422, f"HTTP {code}")
    inj = json.loads((DOCS / "injection_example.json").read_text())
    code, body = http("POST", a.base + "/proposals", inj)
    check("prompt injection rejected with 422 before any run starts", code == 422 and "guardrail" in json.dumps(body), f"HTTP {code}")
    code, _ = http("GET", f"{a.base}/v1/compliance/status/run-does-not-exist")
    check("unknown run id returns 404", code == 404)

    print(f"\nconflict policy: '{res['conflict_policy']}'" + ("  (default: most real proposals go to specialist-review; set CONFLICT_POLICY=stricter in .env to see clear and revise routes)"
                                                              if res["conflict_policy"] == "escalate" else ""))
    print("RESULT:", "ALL CHECKS PASSED" if all(results) else "SOME CHECKS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
