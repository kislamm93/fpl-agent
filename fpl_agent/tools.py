"""Strands @tool wrappers over the framework-free backend client.

The real logic + trimming lives in backend.py (independently testable). These
wrappers only add the tool docstrings the model reads to decide when to call.
"""
from strands import tool

from fpl_agent import backend


@tool
def current_gameweek() -> int:
    """Return the upcoming FPL gameweek number. Call this first so you never
    ask the user which gameweek they mean."""
    return backend.current_gameweek()


@tool
def match_odds() -> list[dict]:
    """Bookmaker odds for upcoming Premier League matches (MATCH-LEVEL — there is
    no player goalscorer market available). Each row gives the two teams (FPL
    short names) with their implied win % and the draw %, favourites first.

    Use it for captaincy: a team with a high win % is likely to attack and score,
    so its forwards/attacking midfielders are strong captain candidates; a big
    favourite also raises clean-sheet odds for its defenders."""
    return backend.match_odds()


@tool
def fixture_difficulty(from_gw: int, to_gw: int) -> list[dict]:
    """Per-team upcoming fixture difficulty from the OFFICIAL FPL FDR (1-5, lower =
    easier), easiest team first. Use as CONTEXT to confirm a fixture is soft and to
    break ties between similar-odds captain options."""
    return backend.fixture_difficulty(from_gw, to_gw)


@tool
def players(position: str = "all", limit: int = 30) -> list[dict]:
    """Player reference ranked by FPL expected points next GW (ep_next). Use it to
    attach real player names to the teams the odds favour and to sanity-check form,
    price, ownership and injury doubts. position: GKP|DEF|MID|FWD|all."""
    return backend.players(position, limit)


@tool
def manager_squad(manager_id: int, gameweek: int) -> list[dict]:
    """A specific manager's XI for the gameweek (starters first) with captain flags.
    Only call this when the user gives a manager_id and wants a captain pick from
    THEIR squad rather than league-wide."""
    return backend.manager_squad(manager_id, gameweek)


ALL_TOOLS = [current_gameweek, match_odds, fixture_difficulty, players, manager_squad]
