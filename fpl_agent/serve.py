"""Minimal local HTTP server for the agent — dev use before AgentCore is deployed.

Run it:
    uvicorn fpl_agent.serve:app --port 9000     (needs FPL_BACKEND_URL + Bedrock access)

Then point the FPL backend at it with AGENT_URL=http://127.0.0.1:9000 so the
Fixture Ticker chat panel can reach the agent. In production the backend talks to
the deployed AgentCore Runtime instead (AGENT_RUNTIME_ARN) and this file is unused.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fpl_agent.sessions import agent_for

app = FastAPI(title="FPL Agent (local dev server)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class InvokeRequest(BaseModel):
    prompt: str
    # Pass one id per browser conversation so chats stay separate.
    session_id: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/invoke")
def invoke(req: InvokeRequest):
    """Run the agent once and return its text reply."""
    reply = str(agent_for(req.session_id)(req.prompt))
    return {"reply": reply}
