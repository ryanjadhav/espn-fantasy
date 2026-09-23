#!/usr/bin/env python3
"""ESPN fantasy football API writes (waiver claims, add/drops, lineup swaps).

Uses the same espn_s2/SWID cookies as espn_api.py, but POSTs to ESPN's
write host (lm-api-writes.fantasy.espn.com).

Configuration: same environment variables as espn_api.py
(ESPN_LEAGUE_ID, ESPN_TEAM_ID, ESPN_SEASON, ESPN_COOKIES).

Writes act on YOUR live team. This script never acts on its own: it only
executes the move named on its command line. Always use --dry-run first
to show the exact payload, then run for real.

Usage:
  espn_txn.py claim --add "Jared Goff" --drop "Kenny Gainwell" [--dry-run]
      Submit a waiver claim (add + optional drop). League must use waivers.
  espn_txn.py freeagent --add "Bo Nix" --drop "Kenny Gainwell" [--dry-run]
      Immediate free-agent add/drop (no waiver processing).
  espn_txn.py lineup --swap "Jared Goff" "Caleb Williams" \
      --swap "Drake London" "Stefon Diggs" [--dry-run]
      Start/sit swap(s): each --swap exchanges the two players' lineup slots.

Exit codes: 0 ok, 2 bad args/unresolvable player, 3 auth expired.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date


def _default_season():
    today = date.today()
    return str(today.year if today.month >= 8 else today.year - 1)


def _config():
    league_id = os.environ.get("ESPN_LEAGUE_ID")
    if not league_id:
        sys.exit("error: ESPN_LEAGUE_ID is not set (see README.md for setup)")
    try:
        team_id = int(os.environ.get("ESPN_TEAM_ID", ""))
    except ValueError:
        team_id = 0
    if not team_id:
        sys.exit("error: ESPN_TEAM_ID is not set (see README.md for setup)")
    season = os.environ.get("ESPN_SEASON") or _default_season()
    return league_id, team_id, season


try:
    LEAGUE_ID, TEAM_ID, SEASON = _config()
    WRITE_BASE = (
        "https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl"
        f"/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
    )
    _CONFIG_OK = True
except SystemExit:
    # --help works without configuration; real commands re-raise below.
    LEAGUE_ID, TEAM_ID, SEASON, WRITE_BASE = None, None, None, None
    _CONFIG_OK = False

sys.path.insert(0, os.path.dirname(__file__))
from espn_api import _cookie_header, api_get, AuthExpired  # noqa: E402


def _find_free_agent(name):
    filt = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
            "filterSlotIds": {"value": [0, 2, 4, 6, 16, 17]}, "limit": 200,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    data = api_get(["kona_player_info"], fantasy_filter=filt)
    want = name.strip().lower()
    hits = []
    for p in data.get("players", []):
        pl = p.get("player", {})
        full = (pl.get("fullName") or "")
        if full.lower() == want or want in full.lower():
            hits.append((pl.get("id"), full, p.get("status")))
    exact = [h for h in hits if h[1].lower() == want]
    pool = exact or hits
    if not pool:
        raise ValueError(f"no free agent/waiver player matching '{name}'")
    if len(pool) > 1 and not exact:
        raise ValueError(f"ambiguous name '{name}': " +
                         ", ".join(h[1] for h in pool))
    return pool[0]


def _find_rostered(name):
    data = api_get(["mRoster"])
    want = name.strip().lower()
    for t in data.get("teams", []):
        if t.get("id") != TEAM_ID:
            continue
        hits = []
        for e in t.get("roster", {}).get("entries", []):
            pl = e.get("playerPoolEntry", {}).get("player", {})
            full = (pl.get("fullName") or "")
            if full.lower() == want or want in full.lower():
                hits.append((pl.get("id"), full))
        exact = [h for h in hits if h[1].lower() == want]
        pool = exact or hits
        if not pool:
            raise ValueError(f"'{name}' is not on team {TEAM_ID}'s roster")
        if len(pool) > 1 and not exact:
            raise ValueError(f"ambiguous name '{name}': " +
                             ", ".join(h[1] for h in pool))
        return pool[0]
    raise ValueError(f"team {TEAM_ID} not found")


def _find_rostered_with_slot(name):
    data = api_get(["mRoster"])
    want = name.strip().lower()
    for t in data.get("teams", []):
        if t.get("id") != TEAM_ID:
            continue
        hits = []
        for e in t.get("roster", {}).get("entries", []):
            pl = e.get("playerPoolEntry", {}).get("player", {})
            full = (pl.get("fullName") or "")
            if full.lower() == want or want in full.lower():
                hits.append((pl.get("id"), full, e.get("lineupSlotId")))
        exact = [h for h in hits if h[1].lower() == want]
        pool = exact or hits
        if not pool:
            raise ValueError(f"'{name}' is not on team {TEAM_ID}'s roster")
        if len(pool) > 1 and not exact:
            raise ValueError(f"ambiguous name '{name}': " +
                             ", ".join(h[1] for h in pool))
        return pool[0]
    raise ValueError(f"team {TEAM_ID} not found")


SLOT_NAMES = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "D/ST", 17: "K",
              20: "BE", 21: "IR", 23: "FLEX"}


def _ctx():
    st = api_get(["mStatus"]).get("status", {})
    sp = st.get("transactionScoringPeriod") or st.get("currentMatchupPeriod")
    member = None
    for t in api_get(["mTeam"]).get("teams", []):
        if t.get("id") == TEAM_ID:
            owners = t.get("owners") or []
            member = owners[0] if owners else None
    if not sp or not member:
        raise ValueError("could not resolve scoringPeriodId/memberId")
    return sp, member


def _post(payload, dry_run):
    if dry_run:
        print(json.dumps(payload, indent=1))
        print("dry-run: nothing sent")
        return 0
    req = urllib.request.Request(
        WRITE_BASE + "/transactions/",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Cookie": _cookie_header(),
            "Content-Type": "application/json",
            "X-Fantasy-Source": "kona",
            "X-Fantasy-Platform": "espn-fantasy-web",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthExpired(f"HTTP {e.code} on write")
        print("WRITE FAILED: HTTP", e.code)
        print(e.read().decode("utf-8", "replace")[:1000])
        return 1
    txns = body.get("transactions", [body])
    for t in txns:
        items = [{"playerId": i.get("playerId"), "type": i.get("type"),
                  "fromTeamId": i.get("fromTeamId"),
                  "toTeamId": i.get("toTeamId")} for i in t.get("items", [])]
        print(json.dumps({"id": t.get("id"), "type": t.get("type"),
                          "status": t.get("status"), "items": items}, indent=1))
    return 0


def cmd_claim(add_name, drop_name, dry_run):
    sp, member = _ctx()
    items = []
    pid, full, status = _find_free_agent(add_name)
    items.append({"playerId": pid, "type": "ADD", "toTeamId": TEAM_ID})
    note = f"ADD {full} (id {pid}, pool status {status})"
    if drop_name:
        dpid, dfull = _find_rostered(drop_name)
        items.append({"playerId": dpid, "type": "DROP", "fromTeamId": TEAM_ID})
        note += f" / DROP {dfull} (id {dpid})"
    print(note, file=sys.stderr)
    payload = {"isLeagueManager": False, "teamId": TEAM_ID, "type": "WAIVER",
               "scoringPeriodId": sp, "executionType": "EXECUTE",
               "memberId": member, "items": items}
    return _post(payload, dry_run)


def cmd_freeagent(add_name, drop_name, dry_run):
    sp, member = _ctx()
    items = []
    pid, full, status = _find_free_agent(add_name)
    if status != "FREEAGENT":
        raise ValueError(f"{full} is on {status}, not a free agent "
                         "(use 'claim' for waiver players)")
    items.append({"playerId": pid, "type": "ADD", "toTeamId": TEAM_ID})
    note = f"ADD {full} (id {pid})"
    if drop_name:
        dpid, dfull = _find_rostered(drop_name)
        items.append({"playerId": dpid, "type": "DROP", "fromTeamId": TEAM_ID})
        note += f" / DROP {dfull} (id {dpid})"
    print(note, file=sys.stderr)
    payload = {"isLeagueManager": False, "teamId": TEAM_ID, "type": "FREEAGENT",
               "scoringPeriodId": sp, "executionType": "EXECUTE",
               "memberId": member, "items": items}
    return _post(payload, dry_run)


def cmd_lineup(swaps, dry_run):
    sp, member = _ctx()
    items, notes, seen = [], [], set()
    for a, b in swaps:
        pa, fa, sa = _find_rostered_with_slot(a)
        pb, fb, sb = _find_rostered_with_slot(b)
        if pa == pb:
            raise ValueError(f"cannot swap '{a}' with itself")
        if sa == sb:
            raise ValueError(f"'{fa}' and '{fb}' are both in slot {sa} "
                             "— nothing to swap")
        for pid in (pa, pb):
            if pid in seen:
                raise ValueError("a player appears in more than one swap")
            seen.add(pid)
        items.append({"playerId": pa, "type": "LINEUP",
                      "fromLineupSlotId": sa, "toLineupSlotId": sb,
                      "fromTeamId": TEAM_ID, "toTeamId": TEAM_ID})
        items.append({"playerId": pb, "type": "LINEUP",
                      "fromLineupSlotId": sb, "toLineupSlotId": sa,
                      "fromTeamId": TEAM_ID, "toTeamId": TEAM_ID})
        notes.append(
            f"SWAP {fa} (id {pa}) {SLOT_NAMES.get(sa, sa)} -> "
            f"{SLOT_NAMES.get(sb, sb)}  |  {fb} (id {pb}) "
            f"{SLOT_NAMES.get(sb, sb)} -> {SLOT_NAMES.get(sa, sa)}")
    print("\n".join(notes), file=sys.stderr)
    payload = {"isLeagueManager": False, "teamId": TEAM_ID, "type": "ROSTER",
               "scoringPeriodId": sp, "executionType": "EXECUTE",
               "memberId": member, "items": items}
    return _post(payload, dry_run)


def main(argv):
    if len(argv) < 1 or argv[0] in ("-h", "--help") or \
            argv[0] not in ("claim", "freeagent", "lineup"):
        print(__doc__)
        return 0
    if not _CONFIG_OK:
        _config()  # re-raises the friendly "not set" error
        return 2
    cmd, add_name, drop_name, dry_run = argv[0], None, None, False
    swaps = []
    i = 1
    while i < len(argv):
        if argv[i] == "--add" and i + 1 < len(argv):
            add_name, i = argv[i + 1], i + 2
        elif argv[i] == "--drop" and i + 1 < len(argv):
            drop_name, i = argv[i + 1], i + 2
        elif argv[i] == "--swap" and i + 2 < len(argv):
            swaps.append((argv[i + 1], argv[i + 2]))
            i += 3
        elif argv[i] == "--dry-run":
            dry_run, i = True, i + 1
        else:
            i += 1
    try:
        if cmd == "lineup":
            if not swaps:
                print("error: --swap <playerA> <playerB> is required",
                      file=sys.stderr)
                return 2
            return cmd_lineup(swaps, dry_run)
        if not add_name:
            print("error: --add <player> is required", file=sys.stderr)
            return 2
        if cmd == "claim":
            return cmd_claim(add_name, drop_name, dry_run)
        return cmd_freeagent(add_name, drop_name, dry_run)
    except AuthExpired as e:
        print(f"error: ESPN cookies expired ({e}).", file=sys.stderr)
        return 3
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
