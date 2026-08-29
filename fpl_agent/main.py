"""AgentCore Runtime entrypoint + a local CLI runner.

Deployed (AgentCore Runtime invokes the @app.entrypoint handler):
    the BedrockAgentCoreApp harness calls invoke(payload) with {"prompt": "..."}.

Local quick test (bypasses the runtime, just calls the Strands agent):
    python -m fpl_agent.main "Who should I captain this week?"
"""
import sys

from fpl_agent.agent import build_agent

agent = build_agent()


def _run_local(prompt: str) -> None:
    result = agent(prompt)
    print(result)


# --- AgentCore Runtime harness --------------------------------------------
# Import guarded so the local CLI works even before bedrock-agentcore is installed.
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload):
        """Runtime handler. payload = {"prompt": "..."}."""
        prompt = (payload or {}).get("prompt", "Who should I captain this week?")
        return str(agent(prompt))

except ImportError:  # pragma: no cover - only in a bare local env
    app = None


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Who should I captain this week?"
    # If run under the AgentCore runtime, let it own the process; else run locally.
    if app is not None and len(sys.argv) == 1:
        app.run()
    else:
        _run_local(prompt)
