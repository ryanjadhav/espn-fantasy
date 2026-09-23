# ESPN Fantasy API reference (football, v3)

Unofficial internal API. Community-verified live on `lm-api-reads.fantasy.espn.com`
as of 2026-03-26. May change without notice.

Base: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{leagueId}`

Repeat the `view` param to combine: `?view=mTeam&view=mRoster&scoringPeriodId=2`.

## Views

| View | Returns |
|---|---|
| `mSettings` | League config, scoring rules, roster slots, trade deadline, veto rules |
| `mTeam` | Teams: names, owners (`members`), records, division |
| `mRoster` | `teams[].roster.entries`: player entries + `lineupSlotId` per team |
| `mStandings` | W/L/T, pointsFor/pointsAgainst per team |
| `mMatchupScore` / `mMatchup` | `schedule`: matchups and scores per matchup period |
| `mScoreboard` | Scoreboard for the requested scoring period |
| `mBoxscore` | Per-player scoring breakdown inside each matchup |
| `mLiveScoring` | Real-time scores during active periods (pair with `mBoxscore`) |
| `mTransactions2` | `transactions`: waivers, trades, free-agent adds |
| `mDraftDetail` | Draft history |
| `kona_player_info` | Player pool: stats, ownership %, projections, health (needs filter header for FA) |
| `proTeamSchedules_wl` | Pro team schedules (bye weeks) |
| `mStatus` | League status (drafted, in season, playoffs) |

## Roster entry shape

```
teams[].roster.entries[]:
  lineupSlotId            # 0 QB, 2 RB, 4 WR, 6 TE, 16 D/ST, 17 K, 20 BE, 21 IR, 23 FLEX
  playerPoolEntry:
    player:
      fullName
      proTeamId
      injuryStatus        # ACTIVE | QUESTIONABLE | DOUBTFUL | OUT | INJURY_RESERVE
      stats[]:            # statSourceId 0 = actual, 1 = projected; appliedTotal is the number
        { statSourceId, statSplitTypeId, appliedTotal }
```

## X-Fantasy-Filter (kona_player_info)

Pass as a request header with JSON. Free agents + waivers, top 50 by ownership:

```
{"players":{"filterStatus":{"value":["FREEAGENT","WAIVERS"]},
 "filterSlotIds":{"value":[0,2,4,6,17,16]},
 "limit":50,"sortPercOwned":{"sortPriority":1,"sortAsc":false}}}
```

`filterStatus` values: `FREEAGENT`, `WAIVERS`, `ONTEAM`.

## Schedule / matchup shape

```
schedule[]:
  matchupPeriodId
  home: { teamId, totalPoints, rosterForCurrentScoringPeriod: { entries[] } }
  away: { ... }
```

Team names resolve via `teams[].id` -> `location` + `nickname`.

## Writes (POST /transactions/) — verified working 2026-09-22

Writes go to a **different host** than reads:

```text
POST https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{leagueId}/transactions/
```

Headers: `Cookie` (espn_s2 + SWID), `Content-Type: application/json`,
`X-Fantasy-Source: kona`, `X-Fantasy-Platform: espn-fantasy-web`.

Envelope: `isLeagueManager: false`, `teamId`, `type`, `scoringPeriodId`
(from `mStatus` → `transactionScoringPeriod`), `executionType: "EXECUTE"`,
`memberId` (from `mTeam` → team's `owners[0]`), plus `items`.

| Operation | Outer `type` | Item fields |
|---|---|---|
| Waiver claim (add + optional drop) | `WAIVER` | ADD: `playerId`, `type: "ADD"`, `toTeamId`; DROP: `playerId`, `type: "DROP"`, `fromTeamId` |
| Immediate free-agent add/drop | `FREEAGENT` | Same item fields |
| Start/sit swap (verified working 2026-09-23) | `ROSTER` | `playerId`, `type: "LINEUP"`, `fromLineupSlotId`, `toLineupSlotId`, `fromTeamId`, `toTeamId` — one item per side of the swap |

Swap both directions in one transaction (e.g. Goff `20→0` + Caleb `0→20`) so
ESPN never sees an occupied-slot conflict. See `bin/espn_txn.py lineup`.

Response is the transaction object: `id`, `type`, `status` (`PENDING` for
waiver claims until the waiver run). A 400 "Invalid Input" means the payload
shape is wrong — do not retry blindly. See `bin/espn_txn.py`.

## Transactions shape

```
transactions[]:
  id, type              # e.g. WAIVER, TRADE, FREEAGENT
  status                # PENDING, EXECUTED, etc.
  proposedDate          # epoch ms
  items[]: { playerId, type, fromTeamId, toTeamId }
```

## Auth failures

```json
{"messages":["You are not authorized to view this League."],
 "details":[{"type":"AUTH_LEAGUE_NOT_VISIBLE"}]}
```
HTTP 401/403 or the body above = session expired. Re-sign-in via browser
takeover; do not retry the fetch.

## Game metadata (no auth needed)

```
GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl
GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026
```
