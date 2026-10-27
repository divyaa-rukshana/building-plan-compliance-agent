import uuid
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from redis import Redis
from rq import Queue
from src.schemas import BuildingProposalRequest, ComplianceResultResponse

app = FastAPI(title="Building Plan Compliance API")
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
    try:
        validated_proposal = BuildingProposalRequest(**raw_payload)
    except Exception as e:
        quarantine_record(raw_payload, str(e))
        raise HTTPException(status_code=422, detail=f"Quarantined: {str(e)}")
    
    task_queue.enqueue('src.worker.run_agent_pipeline', validated_proposal.model_dump(), job_id=run_id)
    
    return ComplianceResultResponse(
        run_id=run_id, correlation_id=str(uuid.uuid4()), status="queued", metrics={"submitted_at": datetime.utcnow().isoformat()}
    )