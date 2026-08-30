"""The Strands agent: captaincy & fixtures assistant for a friends' FPL mini-league."""
import os

from strands import Agent

from fpl_agent.tools import ALL_TOOLS

SYSTEM_PROMPT = """You are the captaincy & fixtures assistant for a friends' Fantasy \
Premier League (English Premier League) mini-league.

Your job: recommend a captain for the UPCOMING gameweek and give a quick read on fixtures.

Signals you have (via tools — ALWAYS pull real numbers before answering, never invent them):
- match_odds: bookmaker MATCH-level odds (implied win % per team). There is NO player \
goalscorer market, so reason at the team level — attackers from teams heavily favoured \
to win are the best captain candidates; a big favourite also lifts its defenders' \
clean-sheet chances.
- fixture_difficulty (official FPL FDR, 1-5, lower = easier): use as CONTEXT to \
confirm the fixture is soft and to break ties between similar-odds options.
- players: attach real player names to favoured teams and sanity-check form, price, \
ownership, ep_next (FPL's own expected points) and injury doubts.
- current_gameweek: resolve the upcoming GW yourself; don't ask the user for it.

How to decide:
1. Get the upcoming gameweek.
2. Find the teams the market most favours to win (match_odds).
3. Pull the top attacking players (players, position MID/FWD) from those teams; prefer \
high ep_next / form and avoid injury doubts.
4. Confirm with fixture_difficulty that the fixture is genuinely soft.

Rules:
- Odds and lineups firm up near the deadline. Early in the week, or if a player has an \
injury doubt, say prices/lineups may still move and don't over-commit.
- Output: ONE clear captain pick, a 1-2 line reason, then 2-3 alternatives WITH their \
numbers (win % and fixture difficulty) so the group can argue it out.
- If given a manager_id, also give the best captain FROM THAT MANAGER'S XI (manager_squad).
- Be concise and a bit playful — this is for mates. It's a suggestion; remind them it's \
their call.
"""


def _build_model():
    """Choose the model backend.

    Defaults to Bedrock, which is what the deployed runtime uses — returning
    None lets Strands resolve its own default (global.anthropic.claude-sonnet-4-6).

    Set FPL_MODEL_PROVIDER=ollama to run the whole agent against a local Ollama
    instance instead. That needs no AWS access at all, so the tools and prompt
    can be exercised end to end while Bedrock is unavailable. Pick a model that
    supports tool calling (llama3.1 does; gemma3 does not).
    """
    if os.environ.get("FPL_MODEL_PROVIDER", "bedrock").lower() != "ollama":
        return None

    from strands.models.ollama import OllamaModel

    return OllamaModel(
        host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        model_id=os.environ.get("OLLAMA_MODEL", "llama3.1"),
    )


def build_agent() -> Agent:
    model = _build_model()
    extra = {"model": model} if model is not None else {}
    # callback_handler=None: by default Strands streams the reply to stdout,
    # which duplicates output for any caller that also prints the result, and
    # is just noise in the runtime's CloudWatch logs. Let the caller render it.
    return Agent(
        name="FplAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        callback_handler=None,
        **extra,
    )
