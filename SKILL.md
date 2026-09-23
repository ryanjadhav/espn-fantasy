---
name: "espn-fantasy"
description: "Manage an ESPN fantasy football team from the CLI: read rosters, matchups, injuries, transactions, and the waiver wire; submit waiver claims, free-agent add/drops, and start/sit lineup swaps via ESPN's internal JSON API using the user's espn_s2/SWID cookies. Use when the user asks about their fantasy team, lineup, waivers, or free agents."
---

# ESPN Fantasy

## Purpose
Pull ESPN fantasy football data as structured JSON and make roster moves —
no browser automation, no scraping. Reads go through `bin/espn_api.py`
(GET only); writes (waivers, free-agent moves, lineup swaps) go through
`bin/espn_txn.py` (POST to ESPN's write host). Both authenticate with the
user's own `espn_s2`/`SWID` session cookies.

## Configuration
All from environment — never hardcode league details:

```
ESPN_LEAGUE_ID   # required; from the league URL (fantasy.espn.com/football/team?leagueId=<id>)
ESPN_TEAM_ID     # required; the user's team id (shown by `espn_api.py check`)
ESPN_SEASON      # optional; inferred from the date if unset
ESPN_COOKIES     # optional; cookie file path, defaults to ~/.config/espn/cookies.json
```

Setup: have the user grab `espn_s2` + `SWID` from desktop Chrome
(espn.com → F12 → Application → Cookies → espn.com) and save as JSON
`{"espn_s2": "...", "SWID": "..."}` at `~/.config/espn/cookies.json`,
`chmod 600`. Never print, log, or paste the cookie values anywhere — not in
chat, files, or memory. Verify with `bin/espn_api.py check`.

## Tooling
```bash
python3 bin/espn_api.py check
python3 bin/espn_api.py mTeam mRoster
python3 bin/espn_api.py mMatchup --scoring-period 3
python3 bin/espn_api.py mTransactions2
python3 bin/espn_api.py freeagents --pos RB --limit 50

# Writes — ALWAYS --dry-run first; it prints the exact payload and sends nothing.
python3 bin/espn_txn.py claim --add "Jared Goff" --drop "Kenny Gainwell" --dry-run
python3 bin/espn_txn.py freeagent --add "Panthers D/ST" --drop "Ravens D/ST" --dry-run
python3 bin/espn_txn.py lineup --swap "Jared Goff" "Caleb Williams" --dry-run
```

Useful view combos (one request each):
- Teams + rosters + standings: `view=mTeam&view=mRoster&view=mStandings`
- Scoreboard / matchup: `view=mScoreboard&view=mMatchupScore` (+ `scoringPeriodId=N`)
- Live: `view=mBoxscore&view=mLiveScoring&view=mScoreboard` (+ `scoringPeriodId=N`)
- Transactions (trades, waivers): `view=mTransactions2`
- Waiver pool: `view=kona_player_info` + `X-Fantasy-Filter` header (see docs/api.md)

## Auth
Reads and writes use the `espn_s2` + `SWID` cookies from the cookie file.
Exit code 3, an `EXPIRED` result from `check`, or a 401/403 means the cookies
died: tell the user and have them re-grab both values and update the file
(`chmod 600`). Never store the values anywhere else.

## Operating Rules
1. Combine views to keep each check to 1–3 requests; do not hammer the API.
2. `bin/espn_txn.py` performs no write without an explicit approved move on the
   command line — always show the `--dry-run` output and get approval of the
   exact move before executing it for real.
3. Player names match case-insensitively; ambiguous partial names are rejected
   rather than guessed.
4. Treat `injuryStatus` values `QUESTIONABLE`, `DOUBTFUL`, `OUT`,
   `INJURY_RESERVE` as actionable for lineup decisions; `ACTIVE` is healthy.
5. Lineup slot IDs (football): 0 QB, 2 RB, 4 WR, 6 TE, 16 D/ST, 17 K,
   20 bench, 21 IR, 23 FLEX.
6. Trades are not supported by these scripts — they need ESPN's site UI.
