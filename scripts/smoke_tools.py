"""Exercise the framework-free backend transforms against a running FPL backend.

Run the FPL backend first (localhost:8000) or set FPL_BACKEND_URL, then:
    python scripts/smoke_tools.py

No Strands / AgentCore needed — this proves the tools' data layer.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fpl_agent import backend as b  # noqa: E402


def show(title, data, n=5):
    print(f"\n=== {title} ===")
    if isinstance(data, list):
        print(f"({len(data)} rows, showing {min(n, len(data))})")
        for row in data[:n]:
            print(" ", json.dumps(row, ensure_ascii=False))
    else:
        print(" ", data)


if __name__ == "__main__":
    print(f"Backend: {b.FPL_BACKEND}")
    gw = b.current_gameweek()
    show("current_gameweek", gw)
    show("match_odds (favourites first)", b.match_odds())
    show("fixture_difficulty (official FDR, easiest first)", b.fixture_difficulty(gw, min(38, gw + 4)))
    show("players FWD (top ep_next)", b.players("FWD", limit=8), n=8)

    # name-resolver spot checks
    print("\n=== resolve_team spot checks ===")
    for name in ["Manchester United", "Nottingham Forest", "Newcastle United", "Spurs", "Coventry City"]:
        t = b.resolve_team(name)
        print(f"  {name!r:24} -> {t['short_name'] if t else None}")
