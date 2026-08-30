"""AgentCore Runtime entrypoint + a local CLI runner.

Deployed (AgentCore Runtime invokes the @app.entrypoint handler):
    the BedrockAgentCoreApp harness calls invoke(payload, context) with
    {"prompt": "..."} plus a RequestContext carrying the session id.

Local quick test (bypasses the runtime, just calls the Strands agent):
    python -m fpl_agent.main "Who should I captain this week?"
"""
import sys

from fpl_agent.agent import build_agent
from fpl_agent.sessions import agent_for

DEFAULT_PROMPT = "Who should I captain this week?"


def _run_local(prompt: str) -> None:
    print(build_agent()(prompt))


# --- AgentCore Runtime harness --------------------------------------------
# Import guarded so the local CLI works even before bedrock-agentcore is installed.
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context):
        """Runtime handler. payload = {"prompt": "..."}.

        The second parameter MUST be named `context`: BedrockAgentCoreApp
        decides whether to pass the RequestContext by checking that the
        handler's second parameter is literally called "context".
        """
        prompt = (payload or {}).get("prompt", DEFAULT_PROMPT)
        agent = agent_for(getattr(context, "session_id", None))
        return str(agent(prompt))

except ImportError:  # pragma: no cover - only in a bare local env
    app = None


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or DEFAULT_PROMPT
    # If run under the AgentCore runtime, let it own the process; else run locally.
    if app is not None and len(sys.argv) == 1:
        app.run()
    else:
        _run_local(prompt)
