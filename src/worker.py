from redis import Redis
from rq import Worker, Queue

from src.agents.pipeline import run_pipeline   # imported at start-up so forked work-horses do not re-import LangGraph per job

redis_conn = Redis(host='redis', port=6379)


def run_agent_pipeline(proposal_dict: dict, correlation_id: str = None):
    """rq job. Three-node LangGraph (extractor -> auditor -> verifier); see test_example/agent_design.md.
    The rq job id is the run id the API returned; the correlation id is passed through from the API."""
    return run_pipeline(proposal_dict, correlation_id)


if __name__ == "__main__":
    worker = Worker(
        [Queue("agent_queue", connection=redis_conn)],
        connection=redis_conn,
    )
    worker.work()
