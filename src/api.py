import uuid
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from redis import Redis
from rq import Queue
from rq.job import Job
from src.schemas import BuildingProposalRequest, ComplianceResultResponse

from src.security import scan_text_field_guardrail
from src.security import scan_text_field_guardrail
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Building Plan Compliance API")
Instrumentator().instrument(app).expose(app)
redis_conn = Redis(host='redis', port=6379)
task_queue = Queue('agent_queue', connection=redis_conn)
QUARANTINE_FILE = "quarantined_records.jsonl"

def quarantine_record(payload: dict, error_message: str):
    entry = {"timestamp": datetime.utcnow().isoformat(), "error": error_message, "payload": payload}
    with open(QUARANTINE_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

@app.post("/proposals", status_code=status.HTTP_202_ACCEPTED, response_model=ComplianceResultResponse)
def submit_proposal(raw_payload: dict):
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    correlation_id = str(uuid.uuid4())          # one id for the request: returned here, passed to the worker, on every log line
    try:
        validated_proposal = BuildingProposalRequest(**raw_payload)
    except Exception as e:
        quarantine_record(raw_payload, str(e))
        raise HTTPException(status_code=422, detail=f"Quarantined: {str(e)}")

    task_queue.enqueue('src.worker.run_agent_pipeline', validated_proposal.model_dump(), job_id=run_id)
    passed, why = scan_text_field_guardrail(validated_proposal.notes or "")      # L4: before anything is queued
    if not passed:
        quarantine_record(raw_payload, f"input guardrail: {why}")
        raise HTTPException(status_code=422, detail=f"Quarantined by the input guardrail: {why}")

    task_queue.enqueue('src.worker.run_agent_pipeline', validated_proposal.model_dump(), correlation_id, job_id=run_id)
    task_queue.enqueue('src.worker.run_agent_pipeline', validated_proposal.model_dump(), correlation_id, job_id=run_id, result_ttl=86400)
    
    return ComplianceResultResponse(
        run_id=run_id, 
        correlation_id=correlation_id, 
        status="queued", 
        metrics={"submitted_at": datetime.utcnow().isoformat()}
    )

@app.get("/v1/compliance/status/{run_id}")
def get_pipeline_run_status(run_id: str):
    """
    Asynchronous tracking endpoint (A4). Fetches background job 
    footprints from the Redis Queue registry context.
    """
    try:
        job = Job.fetch(run_id, connection=redis_conn)
    except Exception:
        raise HTTPException(
            status_code=404, 
            detail="Requested validation correlation identifier not found in cluster."
        )

    if job.is_failed:
        return {"status": "failed", "error": "Internal pipeline worker thread execution crashed."}
        
    if job.is_finished:
        return {
            "status": "completed",
            "result": job.result
        }
        
    return {"status": job.get_status()}
