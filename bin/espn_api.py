#!/usr/bin/env python3
"""ESPN fantasy football API client (read-only).

Authenticates with your espn_s2/SWID session cookies, which you grab once
from your browser (see README.md). Cookies live in a local JSON file
(default ~/.config/espn/cookies.json, chmod 600, owner-only).

Configuration (environment variables):
  ESPN_LEAGUE_ID   your league id (required) — find it in your ESPN fantasy
                   URL: fantasy.espn.com/football/team?leagueId=<id>
  ESPN_TEAM_ID     your team id within the league (required)
  ESPN_SEASON      season year (default: inferred from today's date)
  ESPN_COOKIES     path to cookies.json (default ~/.config/espn/cookies.json)

READ-ONLY: this script only performs GET requests. Writes (waiver claims,
free-agent add/drops, lineup swaps) go through bin/espn_txn.py.

Auth failure (HTTP 401/403 or "not authorized" body) means the cookies
expired -> exit code 3; re-grab espn_s2 + SWID from your browser
(DevTools > Application > Cookies > espn.com) and update cookies.json.

Usage:
  espn_api.py <view> [view ...] [--scoring-period N]
      Fetch league endpoint with one or more views, print raw JSON.
      e.g. espn_api.py mTeam mRoster
  espn_api.py freeagents --pos RB [--limit 50]
      Top free agents / waiver players at a position, sorted by ownership.
      --pos one of QB,RB,WR,TE,DST,K (default: all skill positions)
  espn_api.py check
      Verify the cookies are still valid (prints OK or EXPIRED).
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date


def _default_season():
    # NFL season year: the season starting in September of a given year.
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
    cookie_file = os.path.expanduser(
        os.environ.get("ESPN_COOKIES", "~/.config/espn/cookies.json")
    )
    base = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
        f"/seasons/{season}/segments/0/leagues/{league_id}"
    )
    return league_id, team_id, season, cookie_file, base


try:
    LEAGUE_ID, TEAM_ID, SEASON, COOKIE_FILE, BASE = _config()
    _CONFIG_OK = True
except SystemExit:
    # --help works without configuration; real commands re-raise below.
    LEAGUE_ID = TEAM_ID = SEASON = COOKIE_FILE = BASE = None
    _CONFIG_OK = False

POS_SLOT = {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "DST": 16, "K": 17}
ALL_SLOTS = [0, 2, 4, 6, 16, 17]
POS_NAME = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
PRO_TEAM = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "LV", 11: "IND", 12: "KC", 13: "TEN", 14: "LAR",
    15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
    21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA",
    27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}


class AuthExpired(Exception):
    pass


def _cookie_header():
    try:
        with open(COOKIE_FILE) as f:
            c = json.load(f)
        return f"espn_s2={c['espn_s2']}; SWID={c['SWID']}"
    except (OSError, KeyError, json.JSONDecodeError) as e:
        print(f"error: cannot read cookie file {COOKIE_FILE}: {e}", file=sys.stderr)
        sys.exit(2)


def api_get(views, scoring_period=None, fantasy_filter=None):
    params = []
    for v in views:
        params.append(("view", v))
    if scoring_period is not None:
        params.append(("scoringPeriodId", str(scoring_period)))
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Cookie": _cookie_header(),
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
        },
    )
    if fantasy_filter is not None:
        req.add_header("x-fantasy-filter", json.dumps(fantasy_filter))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthExpired(f"HTTP {e.code} from ESPN API")
        body = e.read().decode("utf-8", "replace")[:200]
        raise AuthExpired(f"HTTP {e.code}: {body}")
    if isinstance(data, dict) and any(
        "not authorized" in str(m).lower() for m in data.get("messages", [])
    ):
        raise AuthExpired("API body says not authorized")
    return data


def cmd_views(views, scoring_period=None):
    data = api_get(views, scoring_period=scoring_period)
    print(json.dumps(data))


def cmd_freeagents(pos=None, limit=50):
    slots = [POS_SLOT[pos.upper()]] if pos else ALL_SLOTS
    filt = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
            "filterSlotIds": {"value": slots},
            "limit": limit,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
    }
    data = api_get(["kona_player_info"], fantasy_filter=filt)
    out = []
    for p in data.get("players", []):
        pl = p.get("player", {})
        own = pl.get("ownership", {})
        out.append(
            {
                "name": pl.get("fullName"),
                "pos": POS_NAME.get(pl.get("defaultPositionId"), "?"),
                "proTeam": PRO_TEAM.get(pl.get("proTeamId"), "?"),
                "injury": pl.get("injuryStatus", "ACTIVE"),
                "pctOwned": round(own.get("percentOwned", 0), 1),
            }
        )
    print(json.dumps(out, indent=1))


def cmd_check():
    try:
        data = api_get(["mTeam"])
    except AuthExpired as e:
        print(f"EXPIRED: {e}")
        return 3
    me = next((t for t in data.get("teams", []) if t.get("id") == TEAM_ID), None)
    if me:
        rec = me.get("record", {}).get("overall", {})
        print(
            f"OK: {me.get('name')} "
            f"({rec.get('wins', '?')}-{rec.get('losses', '?')}), "
            f"pointsFor={rec.get('pointsFor', '?')}"
        )
        return 0
    print(f"OK: authorized, but team id {TEAM_ID} not found in response")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if not _CONFIG_OK:
        _config()  # re-raises the friendly "not set" error
        return 2
    try:
        if argv[0] == "check":
            return cmd_check()
        if argv[0] == "freeagents":
            pos, limit = None, 50
            i = 1
            while i < len(argv):
                if argv[i] == "--pos" and i + 1 < len(argv):
                    pos = argv[i + 1]
                    i += 2
                elif argv[i] == "--limit" and i + 1 < len(argv):
                    limit = int(argv[i + 1])
                    i += 2
                else:
                    i += 1
            cmd_freeagents(pos, limit)
            return 0
        # otherwise treat all non-flag args as views
        views, scoring = [], None
        i = 0
        while i < len(argv):
            if argv[i] == "--scoring-period" and i + 1 < len(argv):
                scoring = int(argv[i + 1])
                i += 2
            else:
                views.append(argv[i])
                i += 1
        cmd_views(views, scoring_period=scoring)
        return 0
    except AuthExpired as e:
        print(
            "error: ESPN cookies expired "
            f"({e}). Re-grab espn_s2 + SWID from your browser.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
