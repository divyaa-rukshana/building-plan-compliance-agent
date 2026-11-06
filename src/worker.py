from prometheus_client import start_http_server
from redis import Redis
from rq import Queue, SimpleWorker

from src.agents.pipeline import run_pipeline   # imported at start-up so LangGraph loads once

redis_conn = Redis(host='redis', port=6379)


def run_agent_pipeline(proposal_dict: dict, correlation_id: str = None):
    """rq job. Three-node LangGraph (extractor -> auditor -> verifier).
    The rq job id is the run id the API returned; the correlation id is passed through from the API."""
    return run_pipeline(proposal_dict, correlation_id)


if __name__ == "__main__":
    start_http_server(8002)      # D5: agent metrics at http://agent-worker:8002/metrics
    worker = SimpleWorker(
        [Queue("agent_queue", connection=redis_conn)],
        connection=redis_conn,
    )
    worker.work()