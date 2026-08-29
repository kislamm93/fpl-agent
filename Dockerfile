# AgentCore Runtime only runs linux/arm64 images. Always build with:
#   docker buildx build --platform linux/arm64 ...
# A default amd64 build pushes fine but the runtime will never leave CREATING.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# pyproject is the single source of dependency truth, so the install layer is
# rebuilt on any source change. The deps are pure-python wheels; it's seconds.
COPY pyproject.toml ./
COPY fpl_agent ./fpl_agent
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser
USER appuser

# BedrockAgentCoreApp serves GET /ping (health) and POST /invocations here.
# The runtime only reports READY once /ping answers, which is what CI asserts on.
EXPOSE 8080

CMD ["python", "-m", "fpl_agent.main"]
