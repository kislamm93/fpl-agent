# CI/CD: GitHub push to main -> AgentCore Runtime

## Why GitHub Actions and not Jenkins

Jenkins would work, but it is the wrong shape for this job. Jenkins is a server:
you host it, patch it, expose it to the internet (or run an agent that polls), and
register a GitHub webhook so pushes reach it. You would also store long-lived AWS
access keys in its credential store. That is real infrastructure to maintain before
you deploy a single line.

GitHub Actions runs where the trigger already lives. "Push to main" and "merge a PR
to main" are the *same* event to GitHub — a merge commit landing on `main` — so one
`on: push: branches: [main]` trigger covers both. And it authenticates to AWS with
**OIDC**: GitHub mints a short-lived signed token per run, AWS trades it for
temporary credentials scoped to this repo and branch. No AWS keys exist anywhere.

Use Jenkins only if you are required to (existing corporate instance, builds must
run inside a private network). You'd need Jenkins admin access to add the job and
the credentials; you don't need anyone's permission to add a workflow file here.

## The pipeline

```
push to main
  -> assume AWS deploy role via OIDC        (no stored keys)
  -> docker buildx --platform linux/arm64   (AgentCore is arm64-only)
  -> push image to ECR, tagged :<git-sha>
  -> create-agent-runtime  (first run)
     update-agent-runtime  (every run after — same ARN, so callers never change)
  -> poll get-agent-runtime until READY     <- the ping test
  -> invoke-agent-runtime                   (non-gating; needs model access)
```

**READY *is* the ping test.** AgentCore only marks a runtime READY once the
container answers `GET /ping`. That is verified locally already:

```
GET /ping -> 200 {"status":"Healthy","time_of_last_update":...}
```

It needs no Bedrock model access, so it passes today even with the account's
token quota at 0.

## Three things that will bite you

1. **arm64 only.** An amd64 image pushes to ECR without complaint and then the
   runtime sits in `CREATING` until it fails. The workflow cross-builds with QEMU.
2. **`provenance: false`.** buildx defaults to attaching an attestation manifest,
   producing a multi-manifest image that AgentCore rejects. The build step disables it.
3. **Runtime name charset.** `agentRuntimeName` allows letters, digits and
   underscores — no hyphens. Hence `fpl_agent`, not `fpl-agent` (the ECR repo can
   keep the hyphen; they are different namespaces).

## One-time setup

```bash
# 1. Create the AWS side: ECR repo, GitHub OIDC provider, both IAM roles.
./scripts/bootstrap_aws.sh <your-github-owner>/fpl-agent

# 2. Push the code to GitHub.
git add -A && git commit -m "Add AgentCore CI/CD"
git remote add origin git@github.com:<owner>/fpl-agent.git
git push -u origin main
```

Then in **GitHub -> Settings -> Secrets and variables -> Actions**, add what the
bootstrap script prints:

| Kind | Name | Value |
|---|---|---|
| Secret | `AWS_DEPLOY_ROLE_ARN` | the deploy role ARN |
| Secret | `AGENTCORE_EXECUTION_ROLE_ARN` | the execution role ARN |
| Variable | `FPL_BACKEND_URL` | your **public** backend URL |

`FPL_BACKEND_URL` is a plain variable, not a secret — it is not sensitive, and the
agent needs no secrets at all (odds/Mongo/admin keys all stay on the backend).

## The two roles, and why there are two

- **Deploy role** — assumed by GitHub Actions. Can push to one ECR repo, manage the
  runtime, and `PassRole` the execution role. Its trust policy pins
  `sub = repo:<owner>/<repo>:ref:refs/heads/main`, so a fork or a feature branch
  gets nothing even though it presents a valid GitHub token.
- **Execution role** — assumed by the *runtime itself* at request time. Pulls the
  image, writes logs/traces, and calls `bedrock:InvokeModel`.

Keeping them apart means CI cannot invoke models and the agent cannot deploy itself.

## Known blockers (not CI problems)

- **Bedrock quota is 0 account-wide.** Every on-demand inference quota on account
  `198493113665` — Anthropic *and* Amazon Nova — is `0.0`, so all invokes return
  `ThrottlingException: Too many tokens per day`. Model *access* is granted; the
  allowance is zero. Raise it in Service Quotas; no quota-increase request is
  currently pending. Deploys still go green because READY needs no model access.
- ~~No public backend.~~ **Resolved.** The backend is live at
  `https://fpl-backend-xio6.onrender.com` (the `fpl-backend.onrender.com` host in
  the older notes is dead — it 404s on every path). All five tools were verified
  against it: `/events/`, `/bootstrap-static`, `/odds/upcoming`, `/fixture-ticker/`
  and `/entry/.../picks` all return 200 with correct data. Set as the repo variable
  `FPL_BACKEND_URL`.

  Note it is on Render's free tier, which sleeps when idle — the first tool call
  after a quiet period can take ~30-60s to cold-start. `backend.py` uses a 30s
  httpx timeout, so a cold start may time out on the first attempt and succeed on
  a retry.

## Rollback

Images are tagged with the commit SHA, so point the runtime at an older one:

```bash
aws bedrock-agentcore-control update-agent-runtime \
  --region eu-central-1 --agent-runtime-id <id> \
  --agent-runtime-artifact '{"containerConfiguration":{"containerUri":"<acct>.dkr.ecr.eu-central-1.amazonaws.com/fpl-agent:<old-sha>"}}' \
  --role-arn <exec-role-arn> \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --protocol-configuration '{"serverProtocol":"HTTP"}'
```

Or just revert the commit on `main` — the pipeline redeploys the previous code.
