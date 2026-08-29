#!/usr/bin/env bash
# One-time AWS setup for the GitHub Actions -> AgentCore pipeline.
# Idempotent: safe to re-run. Requires admin-ish AWS creds locally.
#
#   ./scripts/bootstrap_aws.sh <github-owner>/<github-repo>
#
# Creates:
#   1. an ECR repository for the agent image
#   2. the GitHub OIDC identity provider (if the account doesn't have one)
#   3. a DEPLOY role GitHub Actions assumes keylessly, locked to this repo
#   4. an EXECUTION role the AgentCore runtime itself assumes
#
# Prints the two role ARNs to register as GitHub repo secrets.
set -euo pipefail

REPO="${1:?usage: bootstrap_aws.sh <owner>/<repo>}"
REGION="${AWS_REGION:-eu-central-1}"
ECR_REPO="${ECR_REPO:-fpl-agent}"
DEPLOY_ROLE="${DEPLOY_ROLE:-fpl-agent-gha-deploy}"
EXEC_ROLE="${EXEC_ROLE:-fpl-agent-agentcore-exec}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
OIDC_ARN="arn:aws:iam::${ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"

echo "account=$ACCOUNT region=$REGION repo=$REPO"

# --- 1. ECR repository ------------------------------------------------------
aws ecr describe-repositories --region "$REGION" --repository-names "$ECR_REPO" >/dev/null 2>&1 \
  || aws ecr create-repository --region "$REGION" --repository-name "$ECR_REPO" \
       --image-scanning-configuration scanOnPush=true >/dev/null
echo "ecr ok: $ECR_REPO"

# --- 2. GitHub OIDC provider ------------------------------------------------
# Lets GitHub Actions swap a signed workflow token for AWS creds: no stored keys.
aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" >/dev/null 2>&1 \
  || aws iam create-open-id-connect-provider \
       --url https://token.actions.githubusercontent.com \
       --client-id-list sts.amazonaws.com \
       --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
echo "oidc ok"

# --- 3. Deploy role (assumed by GitHub Actions) -----------------------------
# `sub` pins this to pushes on main of THIS repo only. A fork or another branch
# gets no credentials, even though they share the same OIDC issuer.
DEPLOY_TRUST="$(jq -nc --arg arn "$OIDC_ARN" --arg repo "$REPO" '{
  Version: "2012-10-17",
  Statement: [{
    Effect: "Allow",
    Principal: { Federated: $arn },
    Action: "sts:AssumeRoleWithWebIdentity",
    Condition: {
      StringEquals: { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      StringLike:   { "token.actions.githubusercontent.com:sub": ("repo:" + $repo + ":ref:refs/heads/main") }
    }
  }]
}')"

if aws iam get-role --role-name "$DEPLOY_ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$DEPLOY_ROLE" \
    --policy-document "$DEPLOY_TRUST" >/dev/null
else
  aws iam create-role --role-name "$DEPLOY_ROLE" \
    --assume-role-policy-document "$DEPLOY_TRUST" \
    --description "GitHub Actions deployer for the FPL AgentCore runtime" >/dev/null
fi

DEPLOY_POLICY="$(jq -nc \
  --arg ecr "arn:aws:ecr:${REGION}:${ACCOUNT}:repository/${ECR_REPO}" \
  --arg exec "arn:aws:iam::${ACCOUNT}:role/${EXEC_ROLE}" '{
  Version: "2012-10-17",
  Statement: [
    { Sid: "EcrAuth",  Effect: "Allow", Action: "ecr:GetAuthorizationToken", Resource: "*" },
    { Sid: "EcrPush",  Effect: "Allow", Resource: $ecr, Action: [
        "ecr:BatchCheckLayerAvailability","ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart","ecr:CompleteLayerUpload","ecr:PutImage",
        "ecr:BatchGetImage","ecr:DescribeRepositories","ecr:DescribeImages" ] },
    { Sid: "AgentCore", Effect: "Allow", Resource: "*", Action: [
        "bedrock-agentcore:CreateAgentRuntime","bedrock-agentcore:UpdateAgentRuntime",
        "bedrock-agentcore:GetAgentRuntime","bedrock-agentcore:ListAgentRuntimes",
        "bedrock-agentcore:InvokeAgentRuntime" ] },
    { Sid: "PassExecRole", Effect: "Allow", Action: "iam:PassRole", Resource: $exec,
      Condition: { StringEquals: { "iam:PassedToService": "bedrock-agentcore.amazonaws.com" } } }
  ]
}')"
aws iam put-role-policy --role-name "$DEPLOY_ROLE" \
  --policy-name deploy --policy-document "$DEPLOY_POLICY"
echo "deploy role ok: $DEPLOY_ROLE"

# --- 4. Execution role (assumed by the runtime) -----------------------------
EXEC_TRUST="$(jq -nc --arg acct "$ACCOUNT" --arg region "$REGION" '{
  Version: "2012-10-17",
  Statement: [{
    Effect: "Allow",
    Principal: { Service: "bedrock-agentcore.amazonaws.com" },
    Action: "sts:AssumeRole",
    Condition: {
      StringEquals: { "aws:SourceAccount": $acct },
      ArnLike: { "aws:SourceArn": ("arn:aws:bedrock-agentcore:" + $region + ":" + $acct + ":*") }
    }
  }]
}')"

if aws iam get-role --role-name "$EXEC_ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$EXEC_ROLE" \
    --policy-document "$EXEC_TRUST" >/dev/null
else
  aws iam create-role --role-name "$EXEC_ROLE" \
    --assume-role-policy-document "$EXEC_TRUST" \
    --description "Execution role for the FPL AgentCore runtime" >/dev/null
fi

EXEC_POLICY="$(jq -nc --arg ecr "arn:aws:ecr:${REGION}:${ACCOUNT}:repository/${ECR_REPO}" '{
  Version: "2012-10-17",
  Statement: [
    { Sid: "EcrPull", Effect: "Allow", Resource: $ecr, Action: [
        "ecr:BatchGetImage","ecr:GetDownloadUrlForLayer","ecr:BatchCheckLayerAvailability" ] },
    { Sid: "EcrAuth", Effect: "Allow", Action: "ecr:GetAuthorizationToken", Resource: "*" },
    { Sid: "Logs", Effect: "Allow", Resource: "*", Action: [
        "logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents",
        "logs:DescribeLogGroups","logs:DescribeLogStreams" ] },
    { Sid: "Telemetry", Effect: "Allow", Resource: "*", Action: [
        "xray:PutTraceSegments","xray:PutTelemetryRecords",
        "xray:GetSamplingRules","xray:GetSamplingTargets","cloudwatch:PutMetricData" ] },
    { Sid: "InvokeModels", Effect: "Allow", Resource: "*", Action: [
        "bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream" ] },
    { Sid: "WorkloadIdentity", Effect: "Allow", Resource: "*", Action: [
        "bedrock-agentcore:GetWorkloadAccessToken",
        "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
        "bedrock-agentcore:GetWorkloadAccessTokenForUserId" ] }
  ]
}')"
aws iam put-role-policy --role-name "$EXEC_ROLE" \
  --policy-name execution --policy-document "$EXEC_POLICY"
echo "exec role ok: $EXEC_ROLE"

cat <<OUT

Done. Register these in GitHub -> Settings -> Secrets and variables -> Actions:

  Secret  AWS_DEPLOY_ROLE_ARN            arn:aws:iam::${ACCOUNT}:role/${DEPLOY_ROLE}
  Secret  AGENTCORE_EXECUTION_ROLE_ARN   arn:aws:iam::${ACCOUNT}:role/${EXEC_ROLE}
  Variable FPL_BACKEND_URL               https://<your-public-backend>

OUT
