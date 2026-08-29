#!/usr/bin/env bash
# Tear down everything bootstrap_aws.sh and the CI pipeline created.
#
#   ./scripts/teardown_aws.sh          # dry run — prints the plan, deletes nothing
#   ./scripts/teardown_aws.sh --yes    # actually delete
#   ./scripts/teardown_aws.sh --yes --include-oidc
#
# The GitHub OIDC provider is account-wide and shared by any other repo that
# authenticates to this account, so it is KEPT unless you pass --include-oidc.
# It is free to leave in place.
#
# Idempotent: anything already gone is reported and skipped.
set -uo pipefail

REGION="${AWS_REGION:-eu-central-1}"
ECR_REPO="${ECR_REPO:-fpl-agent}"
RUNTIME_NAME="${RUNTIME_NAME:-fpl_agent}"
DEPLOY_ROLE="${DEPLOY_ROLE:-fpl-agent-gha-deploy}"
EXEC_ROLE="${EXEC_ROLE:-fpl-agent-agentcore-exec}"

APPLY=0
INCLUDE_OIDC=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y)       APPLY=1 ;;
    --include-oidc) INCLUDE_OIDC=1 ;;
    *) echo "unknown flag: $arg"; exit 2 ;;
  esac
done

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)" || exit 1
OIDC_ARN="arn:aws:iam::${ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"

if [ "$APPLY" -eq 0 ]; then
  echo "DRY RUN — nothing will be deleted. Re-run with --yes to apply."
fi
echo "account=$ACCOUNT region=$REGION"
echo

# run <description> -- <command...>
run() {
  local desc="$1"; shift
  [ "$1" = "--" ] && shift
  if [ "$APPLY" -eq 1 ]; then
    if "$@" >/dev/null 2>&1; then echo "  deleted   $desc"
    else                          echo "  skipped   $desc (absent or already gone)"; fi
  else
    echo "  would delete   $desc"
  fi
}

# --- 1. AgentCore runtime (delete before the role it depends on) ------------
echo "AgentCore:"
RUNTIME_ID="$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
  --query "agentRuntimes[?agentRuntimeName=='${RUNTIME_NAME}'].agentRuntimeId | [0]" \
  --output text 2>/dev/null)"
if [ -n "$RUNTIME_ID" ] && [ "$RUNTIME_ID" != "None" ]; then
  run "runtime $RUNTIME_NAME ($RUNTIME_ID)" -- \
    aws bedrock-agentcore-control delete-agent-runtime \
      --region "$REGION" --agent-runtime-id "$RUNTIME_ID"
else
  echo "  skipped   runtime $RUNTIME_NAME (not found)"
fi

# --- 2. CloudWatch log groups ----------------------------------------------
echo "CloudWatch:"
LGS="$(aws logs describe-log-groups --region "$REGION" \
  --log-group-name-prefix "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID:-zzz}" \
  --query 'logGroups[].logGroupName' --output text 2>/dev/null)"
if [ -n "$LGS" ]; then
  for lg in $LGS; do
    run "log group $lg" -- aws logs delete-log-group --region "$REGION" --log-group-name "$lg"
  done
else
  echo "  skipped   log groups (none found)"
fi

# --- 3. ECR repository (--force also drops every image inside) --------------
echo "ECR:"
COUNT="$(aws ecr list-images --region "$REGION" --repository-name "$ECR_REPO" \
  --query 'length(imageIds)' --output text 2>/dev/null)"
if [ -n "$COUNT" ] && [ "$COUNT" != "None" ]; then
  run "repository $ECR_REPO and its $COUNT image tag(s)" -- \
    aws ecr delete-repository --region "$REGION" --repository-name "$ECR_REPO" --force
else
  echo "  skipped   repository $ECR_REPO (not found)"
fi

# --- 4. IAM roles -----------------------------------------------------------
# A role cannot be deleted while any policy is still attached to it.
echo "IAM:"
for role in "$DEPLOY_ROLE" "$EXEC_ROLE"; do
  if ! aws iam get-role --role-name "$role" >/dev/null 2>&1; then
    echo "  skipped   role $role (not found)"
    continue
  fi
  for p in $(aws iam list-role-policies --role-name "$role" \
              --query 'PolicyNames[]' --output text 2>/dev/null); do
    run "inline policy $role/$p" -- \
      aws iam delete-role-policy --role-name "$role" --policy-name "$p"
  done
  for arn in $(aws iam list-attached-role-policies --role-name "$role" \
                --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null); do
    run "detach $role <- $arn" -- \
      aws iam detach-role-policy --role-name "$role" --policy-arn "$arn"
  done
  run "role $role" -- aws iam delete-role --role-name "$role"
done

# --- 5. OIDC provider (opt-in only) ----------------------------------------
echo "OIDC:"
if [ "$INCLUDE_OIDC" -eq 1 ]; then
  echo "  WARNING: shared account-wide; any other repo using it will break."
  run "provider $OIDC_ARN" -- \
    aws iam delete-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN"
else
  echo "  kept      $OIDC_ARN (free; pass --include-oidc to remove)"
fi

echo
if [ "$APPLY" -eq 1 ]; then
  echo "Teardown complete. GitHub secrets are unaffected — delete those by hand if"
  echo "you are done for good: https://github.com/<owner>/<repo>/settings/secrets/actions"
else
  echo "Dry run finished. Re-run with --yes to apply."
fi
