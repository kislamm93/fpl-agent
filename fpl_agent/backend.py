"""Framework-free client for the FPL backend (Render in prod, localhost in dev).

Everything here is plain Python + httpx so it can be unit/smoke tested without
Strands or the AgentCore runtime installed (see scripts/smoke_tools.py).

Golden rule: every function returns TRIMMED data — only the fields the agent
needs to reason. Never hand the model a raw bootstrap-static or odds dump.
"""
from __future__ import annotations

import difflib
import os
import re
from functools import lru_cache
from typing import Any

import httpx

FPL_BACKEND = os.environ.get("FPL_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

_POSITION = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
_POSITION_ID = {v: k for k, v in _POSITION.items()}


def _get(path: str, **params: Any) -> Any:
    r = httpx.get(f"{FPL_BACKEND}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------
# bootstrap helpers (teams + player index), cached per process
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _bootstrap() -> dict:
    return _get("/bootstrap-static")


def _teams() -> list[dict]:
    return _bootstrap().get("teams", [])


@lru_cache(maxsize=1)
def _team_by_id() -> dict[int, dict]:
    return {t["id"]: t for t in _teams()}


# --------------------------------------------------------------------------
# team-name resolver: The Odds API uses full names ("Manchester United",
# "Nottingham Forest") while FPL uses short forms ("Man Utd", "Nott'm Forest").
# --------------------------------------------------------------------------
# odds-style name (normalised) -> FPL short_name
_ALIASES = {
    "manchester city": "MCI",
    "manchester united": "MUN",
    "man city": "MCI",
    "man utd": "MUN",
    "tottenham hotspur": "TOT",
    "tottenham": "TOT",
    "spurs": "TOT",
    "newcastle united": "NEW",
    "newcastle": "NEW",
    "nottingham forest": "NFO",
    "nottm forest": "NFO",
    "wolverhampton wanderers": "WOL",
    "wolves": "WOL",
    "brighton and hove albion": "BHA",
    "brighton hove albion": "BHA",
    "brighton": "BHA",
    "west ham united": "WHU",
    "west ham": "WHU",
    "leeds united": "LEE",
    "leicester city": "LEI",
    "sheffield united": "SHU",
    "luton town": "LUT",
    "afc bournemouth": "BOU",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def resolve_team(name: str) -> dict | None:
    """Map an odds-API team name to the FPL team dict. Best-effort, None if unmatched."""
    teams = _teams()
    if not teams:
        return None
    by_short = {t["short_name"]: t for t in teams}
    norm_names = {_norm(t["name"]): t for t in teams}
    n = _norm(name)

    # 1. exact FPL name match
    if n in norm_names:
        return norm_names[n]
    # 2. curated alias -> short_name (only if that team plays this season)
    if n in _ALIASES and _ALIASES[n] in by_short:
        return by_short[_ALIASES[n]]
    # 3. fuzzy match on normalised full name
    close = difflib.get_close_matches(n, list(norm_names), n=1, cutoff=0.6)
    if close:
        return norm_names[close[0]]
    # 4. token-subset fallback (e.g. "hull city" vs "hull")
    n_tokens = set(n.split())
    for norm_name, t in norm_names.items():
        t_tokens = set(norm_name.split())
        if n_tokens & t_tokens and (n_tokens <= t_tokens or t_tokens <= n_tokens):
            return t
    return None


def _short(name: str) -> str:
    t = resolve_team(name)
    return t["short_name"] if t else name


# --------------------------------------------------------------------------
# Public, trimmed accessors used by the tools
# --------------------------------------------------------------------------
def current_gameweek() -> int:
    """The upcoming gameweek id (is_current, else is_next, else 1)."""
    events = _get("/events/")
    cur = next((e for e in events if e.get("is_current")), None)
    nxt = next((e for e in events if e.get("is_next")), None)
    return (cur or nxt or {"id": 1})["id"]


def fixture_difficulty(from_gw: int, to_gw: int) -> list[dict]:
    """Per-team upcoming difficulty from the official FPL FDR (1-5, lower = easier)."""
    data = _get("/fixture-ticker/", from_gw=from_gw, to_gw=to_gw)
    out = []
    for row in data.get("rows", []):
        opponents = []
        for gw, cells in row.get("cells", {}).items():
            for c in cells:
                venue = "H" if c["is_home"] else "A"
                opponents.append(f"GW{gw} {c['opponent_short']}({venue}) d{c['difficulty']}")
        out.append(
            {
                "team": row["short_name"],
                "fixture_count": row["fixture_count"],
                "total_difficulty": row["total"],
                "fixtures": opponents,
            }
        )
    return out  # already sorted easiest -> hardest by the backend


def match_odds() -> list[dict]:
    """Upcoming EPL match odds (MATCH-LEVEL — the backend has no player scorer market).

    Returns per match: teams (mapped to FPL short names), each side's implied win
    probability and the draw probability. Use the favoured team's attackers as
    captain candidates; a high clean-sheet-implying favourite also helps defenders.
    """
    matches = _get("/odds/upcoming")
    out = []
    for m in matches:
        cmo = m.get("combined_market_odds", {})
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        home_p = cmo.get(home.lower(), {}).get("implied_probability")
        away_p = cmo.get(away.lower(), {}).get("implied_probability")
        draw_p = cmo.get("draw", {}).get("implied_probability")
        out.append(
            {
                "home": _short(home),
                "away": _short(away),
                "home_win_pct": home_p,
                "draw_pct": draw_p,
                "away_win_pct": away_p,
                "kickoff": m.get("commence_time"),
            }
        )
    # strongest single-team favourite first
    out.sort(key=lambda r: max(r["home_win_pct"] or 0, r["away_win_pct"] or 0), reverse=True)
    return out


def players(position: str = "all", limit: int = 30) -> list[dict]:
    """Trimmed player reference, ranked by FPL expected points next GW (ep_next).

    position: GKP|DEF|MID|FWD|all. Fields kept: name, team, position, price,
    form, ep_next (FPL's own expected pts), owned_pct, plus a news flag if doubtful.
    """
    elements = _bootstrap().get("elements", [])
    tid = _team_by_id()
    want = position.upper()
    rows = []
    for p in elements:
        if want != "ALL" and _POSITION.get(p["element_type"]) != want:
            continue
        if p.get("status") == "u":  # unavailable / left the league
            continue
        team = tid.get(p["team"], {})
        rows.append(
            {
                "name": p["web_name"],
                "team": team.get("short_name", "?"),
                "position": _POSITION.get(p["element_type"], "?"),
                "price": round(p["now_cost"] / 10, 1),
                "form": float(p.get("form") or 0),
                "ep_next": float(p.get("ep_next") or 0),
                "owned_pct": float(p.get("selected_by_percent") or 0),
                "doubt": p.get("news") or None,
            }
        )
    rows.sort(key=lambda r: r["ep_next"], reverse=True)
    return rows[:limit]


def manager_squad(manager_id: int, gameweek: int) -> list[dict]:
    """A manager's XI for the gameweek (starters first), mapped to names/teams."""
    picks = _get(f"/entry/{manager_id}/event/{gameweek}/picks").get("picks", [])
    elements = {p["id"]: p for p in _bootstrap().get("elements", [])}
    tid = _team_by_id()
    out = []
    for pk in picks:
        el = elements.get(pk["element"], {})
        team = tid.get(el.get("team"), {})
        out.append(
            {
                "name": el.get("web_name", str(pk["element"])),
                "team": team.get("short_name", "?"),
                "position": _POSITION.get(el.get("element_type"), "?"),
                "slot": pk["position"],  # 1-11 starters, 12-15 bench
                "is_starter": pk["position"] <= 11,
                "is_captain": pk["is_captain"],
                "is_vice_captain": pk["is_vice_captain"],
                "ep_next": float(el.get("ep_next") or 0),
            }
        )
    out.sort(key=lambda r: r["slot"])
    return out
