# Backend API contracts (verified live) — Task 0

Verified against the running backend at `http://127.0.0.1:8000` on 2026-08-02.
These are the exact shapes the tools depend on. Field names are from real responses,
not memory.

## ⚠️ Headline finding: odds are MATCH-LEVEL only

The backend exposes **no player-level (anytime-goalscorer) market**. `/odds/upcoming`
returns per-match win/draw/win implied probabilities. Therefore the captain logic is
**team-level**: favour attackers from teams the market strongly backs to win; a big
favourite also lifts its defenders' clean-sheet chances. This matches the spec's
documented fallback.

---

## `GET /events/`
List of 38 gameweek objects. We only need the flags:
- `id` (int), `is_current` (bool), `is_next` (bool).
- Pre-season now: GW1 has `is_current=false, is_next=true`.
- `current_gameweek()` = first `is_current`, else first `is_next`, else 1.

## `GET /fixture-ticker/?from_gw=&to_gw=&view=combined|attack|defense`
```
{ from_gw, to_gw, view, gameweeks: [int],
  rows: [ { team_id, name, short_name, total, fixture_count,
            cells: { "<gw>": [ {opponent_id, opponent_short, is_home,
                                 attack, defense, combined, difficulty} ] } } ] }
```
- Rows are pre-sorted easiest → hardest (by total asc, fixture_count desc).
- `difficulty` is the value for the requested `view` (lower = easier).
- Pre-season everything is `d5` because FPL team strengths are still 0 / uniform.
- Tool trims each row to `{team, fixture_count, total_difficulty, fixtures:[...]}`.

## `GET /odds/upcoming`
List (10 upcoming matches now). Each:
```
{ id, sport_key, sport_title, commence_time, home_team, away_team,
  combined_market_odds: { "<team name lowercased>": {name, price, implied_probability},
                          "draw": {name, price, implied_probability} } }
```
- `home_team`/`away_team` are **full names** ("Manchester United", "Nottingham Forest");
  `combined_market_odds` keys are those names lowercased, plus `"draw"`.
- `implied_probability` is already normalised to sum ~100 across the 3 outcomes.
- **Name mapping needed** to FPL short names — see `backend.resolve_team()`
  (alias table + difflib + token-subset fallback). Verified: Manchester United→MUN,
  Nottingham Forest→NFO, Newcastle United→NEW, Spurs→TOT, Coventry City→COV.
- Tool returns `{home, away, home_win_pct, draw_pct, away_win_pct, kickoff}`, favourites first.

## `GET /bootstrap-static` (used directly for players + team index)
- `teams[]`: `id, name, short_name, strength_attack_home/away, strength_defence_home/away`.
  Names are FPL short forms ("Man Utd", "Man City", "Spurs", "Nott'm Forest").
- `element_types[]`: `id` 1..4 → GKP/DEF/MID/FWD (`plural_name_short`).
- `elements[]` (players) fields used: `web_name, team, element_type, now_cost` (tenths),
  `form, ep_next` (FPL expected pts next GW), `selected_by_percent, status, news`.
  `status=='u'` → unavailable (filtered out).
- `players()` tool trims to `{name, team, position, price, form, ep_next, owned_pct, doubt}`
  ranked by `ep_next` desc, capped by `limit`.

## `GET /entry/{manager_id}/event/{event_id}/picks`
```
{ picks: [ {element, position, is_captain, is_vice_captain, multiplier} ], ... }
```
- `element` = player id → mapped via bootstrap `elements`.
- `position` 1..11 = starters, 12..15 = bench.
- `manager_squad()` tool trims to `{name, team, position, slot, is_starter,
  is_captain, is_vice_captain, ep_next}`, starters first.
- Squad-aware captain stretch is therefore feasible (no backend change needed).

## Not used in v1
- `GET /odds/{event_id}/clean-sheets` — BTTS-derived clean-sheet probs per team. Would
  need one call per match; deferred. Team win % is a good enough defender signal for now.
