"""Load test (D6, A7) for the Building Plan Compliance Pre-Check API.

Declared SLO
    P95 end-to-end latency <= 3.5 s (submission to final compliance result)
    at a steady state of 3 concurrent requests, with 0 failed runs.

How "3 concurrent requests" is produced
    Each simulated architect submits a proposal, polls until the result is ready,
    and immediately submits the next one (wait_time = 0). So N users means exactly
    N runs in flight at all times. Run with 3 users to check the SLO, and with
    more users to find the level where the system stops meeting it.

What is measured
    "E2E submit-to-result": time from sending POST /proposals until the status
    endpoint reports completed. Because the client polls every POLL_INTERVAL_S,
    the measured time can be up to that much longer than the true time.
    POST /proposals and GET /status are also reported separately by Locust.

Run (the driver run_load_test.py does this for several user counts):
    locust -f locustfile.py --headless -u 3 -r 3 -t 90s --host http://localhost:8000

The API's rate limit (10 requests per minute per IP) must be raised for the test,
otherwise requests are answered with 429. See the instructions that come with this file.
"""
import json
import math
import os
import time
from pathlib import Path

from locust import HttpUser, constant, events, task

SLO_P95_MS = float(os.getenv("SLO_P95_MS", "3500"))
POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", "0.25"))
RUN_TIMEOUT_S = float(os.getenv("RUN_TIMEOUT_S", "30"))
WARMUP_S = float(os.getenv("WARMUP_S", "10"))
PROPOSAL_FILE = os.getenv("PROPOSAL_FILE", "docs/sample_proposal.json")
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", "results"))
E2E_TYPE = "E2E"
E2E_NAME = "submit-to-result"

PAYLOAD = json.loads(Path(PROPOSAL_FILE).read_text(encoding="utf-8-sig"))

_state = {"t_start": None, "rate_limited": False}
_ok_ms = []
_failures = []
_t_first = [None]
_t_last = [None]


def _percentile(values, p):
    """Nearest-rank percentile of a list of numbers."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return ordered[rank - 1]


def _record_e2e(environment, started, error=None):
    now = time.perf_counter()
    elapsed_ms = (now - started) * 1000.0
    environment.events.request.fire(
        request_type=E2E_TYPE,
        name=E2E_NAME,
        response_time=elapsed_ms,
        response_length=0,
        exception=error,
        context={},
    )
    t0 = _state["t_start"]
    if t0 is not None and (now - t0) < WARMUP_S:
        return  # warm-up runs (model and collection loading) are not part of the SLO sample
    if error is None:
        _ok_ms.append(elapsed_ms)
        if _t_first[0] is None:
            _t_first[0] = now
        _t_last[0] = now
    else:
        _failures.append(str(error))


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    _state["t_start"] = time.perf_counter()


class ArchitectUser(HttpUser):
    wait_time = constant(0)

    @task
    def submit_and_wait(self):
        started = time.perf_counter()
        run_id = None

        with self.client.post("/proposals", json=PAYLOAD, name="POST /proposals", catch_response=True) as resp:
            if resp.status_code == 202:
                try:
                    run_id = resp.json()["run_id"]
                    resp.success()
                except Exception:
                    resp.failure("202 response without run_id")
            elif resp.status_code == 429:
                resp.failure("429 rate limit")
                _state["rate_limited"] = True
            else:
                resp.failure("HTTP %s" % resp.status_code)

        if run_id is None:
            _record_e2e(self.environment, started, Exception("submission failed"))
            if _state["rate_limited"]:
                print("\nSTOPPING: the API answered 429. Raise RATE_LIMIT_PER_MINUTE and restart the api container.\n")
                self.environment.runner.quit()
            else:
                time.sleep(1)
            return

        outcome = None
        deadline = started + RUN_TIMEOUT_S
        while time.perf_counter() < deadline:
            with self.client.get("/v1/compliance/status/%s" % run_id, name="GET /status", catch_response=True) as status_resp:
                if status_resp.status_code == 200:
                    status_resp.success()
                    state = status_resp.json().get("status")
                    if state in ("completed", "failed"):
                        outcome = state
                else:
                    status_resp.failure("HTTP %s" % status_resp.status_code)
            if outcome:
                break
            time.sleep(POLL_INTERVAL_S)

        if outcome == "completed":
            _record_e2e(self.environment, started)
        elif outcome == "failed":
            _record_e2e(self.environment, started, Exception("run failed in the worker"))
        else:
            _record_e2e(self.environment, started, Exception("timeout after %ss" % RUN_TIMEOUT_S))


@events.quitting.add_listener
def _summarise(environment, **kwargs):
    users = getattr(environment.parsed_options, "num_users", 0)
    completed = len(_ok_ms)
    failed = len(_failures)
    span = (_t_last[0] - _t_first[0]) if (_t_first[0] and _t_last[0] and _t_last[0] > _t_first[0]) else None
    p50 = _percentile(_ok_ms, 0.50)
    p95 = _percentile(_ok_ms, 0.95)
    p99 = _percentile(_ok_ms, 0.99)
    passed = bool(completed > 0 and failed == 0 and p95 is not None and p95 <= SLO_P95_MS and not _state["rate_limited"])

    summary = {
        "users": users,
        "completed_runs": completed,
        "failed_runs": failed,
        "rate_limited": _state["rate_limited"],
        "e2e_p50_ms": round(p50, 1) if p50 is not None else None,
        "e2e_p95_ms": round(p95, 1) if p95 is not None else None,
        "e2e_p99_ms": round(p99, 1) if p99 is not None else None,
        "e2e_max_ms": round(max(_ok_ms), 1) if _ok_ms else None,
        "e2e_avg_ms": round(sum(_ok_ms) / completed, 1) if completed else None,
        "runs_per_second": round((completed - 1) / span, 3) if span and completed > 1 else None,
        "http_requests_per_second": round(getattr(environment.stats.total, "total_rps", 0.0), 2),
        "slo_p95_ms": SLO_P95_MS,
        "slo_met": passed,
        "warmup_s": WARMUP_S,
        "poll_interval_s": POLL_INTERVAL_S,
        "first_failures": _failures[:3],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / ("summary_u%s.json" % users)).write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 62)
    print("LOAD TEST SUMMARY  (%s concurrent users)" % users)
    print("=" * 62)
    for key in ("completed_runs", "failed_runs", "e2e_p50_ms", "e2e_p95_ms", "e2e_p99_ms", "e2e_max_ms",
                "runs_per_second", "http_requests_per_second"):
        print("%-26s %s" % (key, summary[key]))
    print("%-26s %s ms" % ("declared SLO (P95)", SLO_P95_MS))
    print("%-26s %s" % ("SLO MET", "YES" if passed else "NO"))
    print("=" * 62 + "\n")

    if not passed:
        environment.process_exit_code = 1