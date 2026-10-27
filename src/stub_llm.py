import time
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Stub LLM Service")

class PromptRequest(BaseModel):
    prompt: str

@app.post("/v1/chat/completions")
def generate_response(req: PromptRequest):
    time.sleep(0.5) 
    return {
        "choices": [{"message": {"content": "This is a fixed stub response."}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}
    }