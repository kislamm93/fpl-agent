#!/usr/bin/env bash
# Tail the deployed agent's logs, without the stack-trace wall.
#
#   ./scripts/logs.sh            # last 30 minutes
#   ./scripts/logs.sh 2h         # last 2 hours
#   ./scripts/logs.sh 10m --raw  # full JSON, including stackTrace
#   ./scripts/logs.sh --follow   # stream live
set -uo pipefail

REGION="${AWS_REGION:-eu-central-1}"
RUNTIME_NAME="${RUNTIME_NAME:-fpl_agent}"
SINCE=30m; RAW=0; FOLLOW=""
for a in "$@"; do
  case "$a" in
    --raw) RAW=1 ;;
    --follow|-f) FOLLOW="--follow" ;;
    *) SINCE="$a" ;;
  esac
done

ID="$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
  --query "agentRuntimes[?agentRuntimeName=='${RUNTIME_NAME}'].agentRuntimeId | [0]" --output text)"
[ -z "$ID" ] || [ "$ID" = "None" ] && { echo "no runtime named $RUNTIME_NAME"; exit 1; }

LG="/aws/bedrock-agentcore/runtimes/${ID}-DEFAULT"
echo "runtime=$ID  log group=$LG  since=$SINCE" >&2

if [ "$RAW" -eq 1 ]; then
  exec aws logs tail "$LG" --region "$REGION" --since "$SINCE" $FOLLOW
fi

aws logs tail "$LG" --region "$REGION" --since "$SINCE" --format short $FOLLOW 2>/dev/null \
| python3 "$(dirname "$0")/_logfmt.py"
