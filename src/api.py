import uuid
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from redis import Redis
from rq import Queue
from rq.job import Job
from prometheus_fastapi_instrumentator import Instrumentator
from src.schemas import BuildingProposalRequest, ComplianceResultResponse
from src.security import scan_text_field_guardrail

app = FastAPI(title="Building Plan Compliance API")
Instrumentator().instrument(app).expose(app)
# 1. App Initialization
app = FastAPI(title="Building Plan Compliance API")
Instrumentator().instrument(app).expose(app)

redis_conn = Redis(host='redis', port=6379)
task_queue = Queue('agent_queue', connection=redis_conn)
QUARANTINE_FILE = "quarantined_records.jsonl"

def quarantine_record(payload: dict, error_message: str):
    entry = {"timestamp": datetime.utcnow().isoformat(), "error": error_message, "payload": payload}
    with open(QUARANTINE_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

# Exception handler for automatic Pydantic validation failures (Requirements F2 & D1)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.json()
    except Exception:
        body = {}
    quarantine_record(body, str(exc.errors()))
    return JSONResponse(
        status_code=422, 
        content={"message": "Invalid request quarantined", "errors": exc.errors()}
    )

# 2. Web UI Endpoint (Requirement A8)
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return """
    <html>
    <body style="font-family: Arial; padding: 20px; max-width: 600px; margin: auto;">
        <h2>Building Plan Compliance Pre-Check</h2>
        <form id="proposalForm" style="display: flex; flex-direction: column; gap: 10px;">
            <label>Plot Area (sqm): <input type="number" id="plot_area" required></label>
            <label>Road Width (m): <input type="number" id="road_width" required></label>
            <label>Height (m): <input type="number" id="building_height" required></label>
            <label>Use: 
                <select id="building_use">
                    <option value="residential">Residential</option>
                    <option value="commercial">Commercial</option>
                    <option value="mixed-use">Mixed-use</option>
                    <option value="institutional">Institutional</option>
                </select>
            </label>
            <button type="submit" style="padding: 10px; background: #007bff; color: white; border: none; cursor: pointer;">Run Pre-Check</button>
        </form>
        <pre id="result" style="background: #f4f4f4; padding: 10px; margin-top: 20px; white-space: pre-wrap;"></pre>
        <script>
        document.getElementById('proposalForm').onsubmit = async (e) => {
            e.preventDefault();
            document.getElementById('result').innerText = "Submitting to agent queue...";
            const data = {
                plot_area: parseFloat(document.getElementById('plot_area').value),
                road_width: parseFloat(document.getElementById('road_width').value),
                building_height: parseFloat(document.getElementById('building_height').value),
                building_use: document.getElementById('building_use').value,
                notes: ""
            };
            const res = await fetch('/proposals', {
                method: 'POST', 
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            document.getElementById('result').innerText = JSON.stringify(await res.json(), null, 2);
        };
        </script>
    </body>
    </html>
    """

# 3. Main Proposal Endpoint
@app.post("/proposals", status_code=status.HTTP_202_ACCEPTED, response_model=ComplianceResultResponse)
def submit_proposal(raw_payload: dict):
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    correlation_id = str(uuid.uuid4())
    
    # Validation & Quarantine (Requirements F2 & D1)
    try:
        validated_proposal = BuildingProposalRequest(**raw_payload)
    except Exception as e:
        quarantine_record(raw_payload, str(e))
        raise HTTPException(status_code=422, detail=f"Quarantined: {str(e)}")

    # Guardrail (Requirement L4)
    passed, why = scan_text_field_guardrail(getattr(validated_proposal, 'notes', "") or "")
    if not passed:
        quarantine_record(raw_payload, f"input guardrail: {why}")
        raise HTTPException(status_code=422, detail=f"Quarantined by the input guardrail: {why}")

    # Async Execution Queue (Requirement A4)
    task_queue.enqueue(
        'src.worker.run_agent_pipeline', 
        validated_proposal.model_dump(), 
        correlation_id, 
        job_id=run_id, 
        result_ttl=86400
    )
    
    return ComplianceResultResponse(
        run_id=run_id, 
        correlation_id=correlation_id, 
        status="queued", 
        metrics={"submitted_at": datetime.utcnow().isoformat()}
    )

# 4. Async Tracking Endpoint (Requirement A4)
@app.get("/v1/compliance/status/{run_id}")
def get_pipeline_run_status(run_id: str):
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

# 5. Feedback Endpoint (Requirement L6)
class Feedback(BaseModel):
    run_id: str
    satisfactory: bool
    reason: str

@app.post("/feedback")
async def submit_feedback(feedback: Feedback):
    with open("feedback.log", "a") as f:
        f.write(feedback.model_dump_json() + "\n")
    return {"status": "Feedback permanently recorded"}