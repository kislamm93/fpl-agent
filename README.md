# fpl-agent

A small **Amazon Bedrock AgentCore** agent that recommends an FPL captain for the
upcoming gameweek and gives a quick fixtures read. It synthesises two signals the
`fpl-backend` already produces — **market odds** and our **custom Fixture Ticker** —
and explains its pick in plain language. No new modelling, no scoring formula (yet).

Built to the spec in `../FPL_HANDOFF.md` / the "FPL Agent — Build Spec (v1)".

## What it does

- **Captain pick for the upcoming GW**, league-wide, with 2–3 alternatives and their numbers.
- **Squad-aware pick** if you pass a `manager_id` (best captain from that manager's XI).
- Reasons **odds-led, ticker-as-context**; hedges early in the week when prices/lineups move.

### Design note — odds are match-level
The backend has **no player goalscorer market**, only match win/draw/win odds. So the agent
reasons at the **team level**: attackers from heavily-favoured teams are the captain
candidates, cross-referenced with FPL `ep_next`/form and confirmed by the ticker.
Full contract details in [`NOTES_contracts.md`](./NOTES_contracts.md).

## Layout

```
fpl_agent/
  backend.py   framework-free client: HTTP + trimming + team-name resolver (testable)
  tools.py     Strands @tool wrappers: current_gameweek, match_odds,
               fixture_difficulty, players, manager_squad
  agent.py     Strands Agent + system prompt
  main.py      AgentCore Runtime entrypoint (@app.entrypoint) + local CLI runner
scripts/
  smoke_tools.py   exercises backend.py against a live backend (no Strands needed)
```

Config: **`FPL_BACKEND_URL` is the only setting.** The agent needs no secrets — the
ODDS_API_KEY / MONGODB_URI / ADMIN_KEY all stay on the backend.

---

## Prerequisites (do these once)

- [ ] **Node 20+** — the `@aws/agentcore` CLI needs it (this machine has v18 → `nvm install 20`).
- [ ] **`uv`** installed — `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- [ ] **AWS creds** configured (already ✓, account 198493113665, region `eu-central-1`).
- [ ] **Bedrock model access** — in the AWS console, Bedrock → *Model access*, submit the
      **Anthropic use-case details form** and enable a Claude Sonnet model. Until this is
      done, invokes fail with `ResourceNotFoundException: Model use case details have not
      been submitted`. (This is the current blocker — everything else works.)

---

## Run locally (no AgentCore CLI needed)

The backend must be running (`cd ../fpl-backend && ./dev-fpl.sh`, or point at Render).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                      # strands-agents + bedrock-agentcore + httpx
export FPL_BACKEND_URL=http://127.0.0.1:8000

# 1) Prove the data layer (no Bedrock, no Strands invoke — just the tools' HTTP+transforms):
python scripts/smoke_tools.py

# 2) Run the agent (needs Bedrock model access enabled):
python -m fpl_agent.main "Who should I captain this week?"
python -m fpl_agent.main "Best captain from manager 123456 for the upcoming GW?"
```

## Chat from the Fixture Ticker page (frontend integration)

The `fpl-season-review` Fixture Ticker page has a **Captaincy Assistant** chat panel.
The browser can't call AgentCore directly (requests must be AWS-signed), so it goes:

```
FixtureTicker chat  ->  POST /agent/chat (fpl-backend proxy)  ->  the agent
```

The backend proxy (`fpl-backend/app/routes/agent.py`) picks a target from config:
- `AGENT_RUNTIME_ARN` set → invokes the deployed AgentCore Runtime (prod).
- else `AGENT_URL` set → POSTs to this project's local dev server (below).
- else → 503 "Agent not configured".

**Local end-to-end (no AgentCore deploy needed, just Bedrock access):**

```bash
# terminal 1 — FPL backend + frontend (AGENT_URL=http://127.0.0.1:9000 is already in .env)
cd ../fpl-backend && ./dev-fpl.sh

# terminal 2 — this agent as a local HTTP server on :9000
cd fpl-agent && source .venv/bin/activate
pip install -e ".[serve]"
export FPL_BACKEND_URL=http://127.0.0.1:8000
uvicorn fpl_agent.serve:app --port 9000
```

Then open the Fixture Ticker page and ask a question. In prod, set `AGENT_RUNTIME_ARN`
(and AWS creds) on Render instead — the local server isn't used.

## Run / deploy with the AgentCore CLI

> The CLI is v0.x and changes fast — run `agentcore --help` and skim
> https://github.com/aws/agentcore-cli before relying on exact commands.

```bash
npm install -g @aws/agentcore     # requires Node 20+
# If the legacy python toolkit shares the name, uninstall it first:
#   uv tool uninstall bedrock-agentcore-starter-toolkit

# This repo is already hand-scaffolded (entrypoint = fpl_agent/main.py). If you prefer the
# wizard, `agentcore create` in an empty sibling dir and copy fpl_agent/ + pyproject in.

agentcore dev                     # local hot-reload against FPL_BACKEND_URL
agentcore invoke "Who should I captain this week?"

agentcore deploy                  # AgentCore Runtime in eu-central-1
agentcore invoke "..."            # test the deployed agent
agentcore status                  # get the Runtime ARN
```

Set `FPL_BACKEND_URL` in both the local env (`.env.local`) and the deployed runtime config
so the cloud agent hits the same public backend. Point it at the **Render** URL once the
backend is deployed.

**Model/region:** Strands resolved to `global.anthropic.claude-sonnet-4-6` (region-agnostic),
so no `eu.`/`us.` profile override is needed. Pin a specific model via a `BedrockModel` in
`agent.py` only if you want to.

---

## Definition of done (v1) — status

- [x] Task 0 contracts recorded; odds granularity confirmed (match-level) and reflected in design.
- [x] `fixture_difficulty`, `match_odds`, `players` (+ `manager_squad`, `current_gameweek`) return trimmed data wired to real schemas.
- [x] `current_gameweek` resolves with no manual GW input.
- [x] Tools smoke-tested green against the live backend; agent builds and registers all tools; reaches Bedrock.
- [ ] Live invoke — **blocked only on enabling Bedrock model access** (console form above).
- [ ] Deployed to AgentCore Runtime in `eu-central-1` (after Node 20 + CLI install).
- [x] `FPL_BACKEND_URL` is the only config; no secrets in the agent.

## Out of scope (next steps)
Transfer/chip advice, multi-week planners, AgentCore Memory (remember each mate's
`manager_id`), the Gateway rework (point at the backend OpenAPI instead of hand-written
tools), and wiring the deployed agent into the React site.
