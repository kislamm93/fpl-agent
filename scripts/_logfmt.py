"""Collapse AgentCore's JSON log lines to one readable line each.

The runtime logs a full stackTrace array on every error, which makes `aws logs
tail` unreadable. Keep level, error type and message; drop the trace.
"""
import json
import sys

for line in sys.stdin:
    ts, _, rest = line.partition(" ")
    rest = rest.strip()
    if not rest:
        continue
    try:
        e = json.loads(rest)
    except ValueError:
        print(f"{ts}  {rest[:140]}")
        continue
    label = e.get("errorType") or e.get("message", "")
    print(f"{ts}  {e.get('level', ''):5} {label}")
    msg = e.get("errorMessage")
    if msg:
        print(f"{' ' * 20}  -> {msg[:130]}")
