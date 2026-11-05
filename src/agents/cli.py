"""Command line for demos and evaluation.

  python -m agents.cli run ex2 [--policy stricter] [--scenario missing-clause] [--debug tamper_far] [--json]
  python -m agents.cli eval
  python -m agents.cli cost [--n 20]
"""
import argparse
import json
import os
import sys

from . import cost as costmod
from .cases import CASES, SCENARIOS
from .config import get_settings
from .corpus_stub import StubCorpus
from .worker import run_proposal


def _run(name, scenario=None, debug=None):
    corpus = StubCorpus(**SCENARIOS[scenario]) if scenario else None
    return run_proposal(CASES[name], corpus=corpus, debug=debug)


def show(r):
    print(f"\nRUN {r['run_id']}   status={r['status']}   route={r['route'].upper()}   verified={r['verified']}   degraded={r['degraded']}")
    print("REASON :", r["reason"])
    if r["summary"]:
        print("SUMMARY:", r["summary"])
    print(f"LIMITS : steps {r['limits_used']['steps']}/{r['limits_used']['max_steps']}, tool calls "
          f"{r['limits_used']['tool_calls']}/{r['limits_used']['max_tool_calls']}, {r['limits_used']['wall_s']}s   "
          f"prompt={r['prompt_version']} policy={r['conflict_policy']}")
    for c in r["conflicts"]:
        print(f"CONFLICT {c['quantity']}: bye-laws {c['bylaws']}  |  RMP {c['rmp']}")
    print("FINDINGS")
    for f in r["findings"]:
        print(f"  [{f['status']:18s}] {'ok ' if f['verified'] else 'UNV'} {f['title']}: {f['limit']}")
        for c in f["citations"]:
            print(f"        cite {c['source_doc']} p.{c['page']} {c['clause_id']}: {c['quote'][:90]}")
    print("ESCALATION / DECISION PATH")
    for x in r["escalation_path"]:
        print("  -", x)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agents.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("case", choices=sorted(CASES))
    pr.add_argument("--policy")
    pr.add_argument("--scenario", choices=sorted(SCENARIOS))
    pr.add_argument("--debug", choices=["tamper_far"])
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--trace", action="store_true")
    sub.add_parser("eval")
    pc = sub.add_parser("cost")
    pc.add_argument("--n", type=int, default=20)
    a = ap.parse_args(argv)
    if getattr(a, "policy", None):
        os.environ["CONFLICT_POLICY"] = a.policy
    if a.cmd == "run":
        r = _run(a.case, a.scenario, a.debug)
        if a.json:
            print(json.dumps(r, indent=2, default=str))
        else:
            show(r)
            if a.trace:
                print("TRACE")
                for e in r["trace"]:
                    print(f"  {e['t_ms']:8.1f}ms {e['agent']:10s} {e['type']:8s} {e['name']:22s} {e['latency_ms']:6.2f}ms "
                          f"{json.dumps({k: v for k, v in e.items() if k not in ('t_ms','run_id','agent','type','name','latency_ms')}, default=str)[:110]}")
        return 0
    if a.cmd == "eval":
        rows = []
        for n in CASES:
            r = _run(n)
            rows.append((n, r["status"], r["route"], r["verified"], r["limits_used"]["steps"], r["reason"][:70]))
        print(f"{'case':18s}{'status':11s}{'route':22s}{'ver':6s}{'steps':6s}reason")
        for x in rows:
            print(f"{x[0]:18s}{x[1]:11s}{x[2]:22s}{str(x[3]):6s}{x[4]:<6d}{x[5]}")
        return 0
    if a.cmd == "cost":
        runs = []
        names = list(CASES)
        for i in range(a.n):
            r = _run(names[i % 4])         # ex1-ex4 only: real proposals, not guardrail demos
            runs.append(r["cost"])
        rep = costmod.report(runs)
        s = get_settings()
        print(json.dumps(rep, indent=2))
        print(f"\nprices: prompt {s.price_prompt_per_1k}/1k, completion {s.price_completion_per_1k}/1k; "
              f"{'token counts ESTIMATED (stub or provider did not return usage)' if any(r['estimated'] for r in runs) else 'token counts from provider'}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
