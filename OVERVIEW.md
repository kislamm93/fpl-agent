# fpl-agent — what this is

A small AI agent that recommends an **FPL captain** for the upcoming gameweek and
gives a quick read on fixtures. It is built with **Strands** and runs on **Amazon
Bedrock AgentCore Runtime**.

It does no modelling of its own. It combines two signals the `fpl-backend`
already produces — bookmaker **match odds** and the **Fixture Ticker** (official
FPL difficulty) — cross-references them against player form and `ep_next`, and
explains its pick in plain language.

## How the pieces fit

Traffic flows **both ways**, which is the thing most people get wrong first:

```
   Fixture Ticker chat (React)
             |
             v
   fpl-backend  POST /agent/chat  ──────────►  AgentCore Runtime   [1]
   (holds AGENT_RUNTIME_ARN)                     (this project)
             ▲                                        |
             └──── GET /odds/upcoming, /events/, ─────┘            [2]
                   /bootstrap-static, /fixture-ticker/
                   (agent's tools call back for data)
```

1. **Backend → agent.** The browser can't call AgentCore directly (requests must
   be AWS-signed), so the backend proxies chat through to the runtime.
2. **Agent → backend.** The agent owns no data. Every one of its five tools is an
   HTTP client of the backend, which is why the runtime needs `FPL_BACKEND_URL`.

## Layout

| Path | What it does |
|---|---|
| `fpl_agent/backend.py` | Framework-free HTTP client. Trims every response before the model sees it, and resolves odds-API team names ("Nottingham Forest") to FPL short names ("NFO"). No Strands import, so it's testable on its own. |
| `fpl_agent/tools.py` | Five `@tool` wrappers: `current_gameweek`, `match_odds`, `fixture_difficulty`, `players`, `manager_squad`. |
| `fpl_agent/agent.py` | The Strands `Agent` and its system prompt. |
| `fpl_agent/sessions.py` | One agent per conversation, keyed by AgentCore's session id. Bounded and idle-expiring, so two people asking about captains never share a chat history. |
| `fpl_agent/main.py` | AgentCore entrypoint (`@app.entrypoint`) plus a local CLI runner. |
| `fpl_agent/serve.py` | Local dev HTTP server, so the frontend can reach the agent before it's deployed. |
| `scripts/smoke_tools.py` | Exercises the data layer against a live backend. No Strands or AWS needed. |
| `scripts/bootstrap_aws.sh` | One-time AWS setup: ECR, GitHub OIDC, both IAM roles. |
| `scripts/teardown_aws.sh` | Deletes all of it. Dry-run by default. |
| `.github/workflows/deploy.yml` | Push to `main` → build arm64 image → ECR → create/update runtime → wait for healthy. |

## Design notes

**Odds are match-level.** The backend has no player goalscorer market, only
win/draw/win. So the agent reasons at the **team** level: attackers from heavily
favoured teams are the captain candidates, and a big favourite also lifts its
defenders' clean-sheet chances. Contracts are recorded in `NOTES_contracts.md`.

**Trim before the model.** `backend.py` never hands raw `bootstrap-static` (1.6 MB)
to the agent — every accessor returns only the fields needed to reason.

**No secrets.** `FPL_BACKEND_URL` is the only configuration. `ODDS_API_KEY`,
`MONGODB_URI` and `ADMIN_KEY` all stay on the backend.

**Model.** Strands resolves to `global.anthropic.claude-sonnet-4-6`, a
region-agnostic inference profile, so no `eu.`/`us.` override is needed. Claude
Sonnet 5 and Opus 5 are not available to this account.

## Running it

```bash
# data layer only — no AWS, no Strands invoke
FPL_BACKEND_URL=https://fpl-backend-xio6.onrender.com python scripts/smoke_tools.py

# the agent itself (needs Bedrock model access)
python -m fpl_agent.main "Who should I captain this week?"
```

Deployment is automatic: see [`CICD.md`](./CICD.md). Detailed setup and history
are in [`README.md`](./README.md).

## Status

- Data layer verified green against the public backend (all five tools).
- Container verified locally: `GET /ping` → `{"status":"Healthy"}`.
- CI builds and pushes an arm64 image to ECR.
- **Blocked:** every Bedrock on-demand token quota on this AWS account is `0`,
  Anthropic and Amazon Nova alike, so invokes return `ThrottlingException`. That
  is a Service Quotas increase, not a model-access form.
