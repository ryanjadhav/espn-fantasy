# espn-fantasy

Manage your ESPN fantasy football team from the command line. Reads rosters,
matchups, injuries, and the waiver wire; submits waiver claims, free-agent
add/drops, and start/sit lineup swaps — no browser automation needed.

Pure Python 3, zero dependencies. Talks to ESPN's internal JSON API using
your own `espn_s2`/`SWID` session cookies.

> **Disclaimer:** This uses ESPN's unofficial internal API, which can change
> without notice. Use at your own risk. Don't hammer it — a few requests per
> session is plenty.

## Setup

### 1. Grab your ESPN session cookies

1. In desktop Chrome, sign in at [espn.com](https://www.espn.com) (and open
   your fantasy league once).
2. Open DevTools (`F12` or `Cmd+Option+I`) → **Application** tab →
   **Cookies** → `https://www.espn.com`.
3. Copy the values of the `espn_s2` and `SWID` cookies.

### 2. Save the cookies

Create `~/.config/espn/cookies.json` (owner-only permissions):

```json
{
  "espn_s2": "paste-espn_s2-value-here",
  "SWID": "paste-SWID-value-here"
}
```

```bash
mkdir -p ~/.config/espn
# write the file, then:
chmod 600 ~/.config/espn/cookies.json
```

Cookies expire periodically (you'll get an `EXPIRED` message). When that
happens, just re-grab the two values and update the file.

### 3. Point the scripts at your league

```bash
export ESPN_LEAGUE_ID="123456789"   # from your league URL:
                                    # fantasy.espn.com/football/team?leagueId=<id>
export ESPN_TEAM_ID="2"             # your team id (see check output)
export ESPN_SEASON="2026"           # optional; inferred from the date if unset
export ESPN_COOKIES="$HOME/.config/espn/cookies.json"  # optional override
```

Verify it works:

```bash
python3 bin/espn_api.py check
# OK: Your Team Name (2-0), pointsFor=276.92
```

## Use as an agent skill

The repo ships a [`SKILL.md`](SKILL.md) (name `espn-fantasy`) so an AI
agent can discover and operate these scripts: when to use `espn_api.py` vs
`espn_txn.py`, the required env vars, the `--dry-run`-first rule, and the
cookie handling rules. To install it for your agent, clone this repo into
your agent's skills directory (e.g. `~/.config/agent/skills/espn-fantasy`
or wherever your agent loads skills from) and set the env vars above.

## Usage

### Reads — `bin/espn_api.py`

```bash
# Raw API views (combine freely)
python3 bin/espn_api.py mTeam mRoster
python3 bin/espn_api.py mMatchup --scoring-period 3
python3 bin/espn_api.py mTransactions2

# Waiver wire / free agents, sorted by ownership
python3 bin/espn_api.py freeagents --pos RB --limit 50
python3 bin/espn_api.py freeagents --pos DST --limit 20

# Pretty-print a saved API response
python3 bin/espn_api.py mTeam mRoster > league.json
python3 bin/espn_parse.py roster league.json --team 2
```

### Writes — `bin/espn_txn.py`

Writes hit your **live** team. Always run with `--dry-run` first — it prints
the exact payload and sends nothing.

```bash
# Waiver claim (add + optional drop)
python3 bin/espn_txn.py claim --add "Jared Goff" --drop "Kenny Gainwell" --dry-run
python3 bin/espn_txn.py claim --add "Jared Goff" --drop "Kenny Gainwell"

# Immediate free-agent add/drop
python3 bin/espn_txn.py freeagent --add "Panthers D/ST" --drop "Ravens D/ST" --dry-run

# Start/sit swaps (each --swap exchanges the two players' lineup slots)
python3 bin/espn_txn.py lineup --swap "Jared Goff" "Caleb Williams" --dry-run
python3 bin/espn_txn.py lineup --swap "Jared Goff" "Caleb Williams" \
    --swap "Drake London" "Stefon Diggs"
```

Player names match case-insensitively; ambiguous partial names are rejected
rather than guessed.

## How it works

- Reads go to `lm-api-reads.fantasy.espn.com` (GET only).
- Writes go to `lm-api-writes.fantasy.espn.com` (`POST /transactions/`).
- Waiver claims use transaction type `WAIVER`, instant add/drops use
  `FREEAGENT`, lineup moves use `ROSTER` with `LINEUP` items (both sides of a
  swap in one transaction so ESPN never sees an occupied-slot conflict).
- See [`docs/api.md`](docs/api.md) for the endpoint/view reference.

## License

MIT — see [LICENSE](LICENSE).
