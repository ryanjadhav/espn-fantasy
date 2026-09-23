#!/usr/bin/env python3
"""Parse ESPN fantasy football API JSON into readable summaries.

Usage:
    python3 espn_parse.py teams league.json
    python3 espn_parse.py roster league.json --team 2
    python3 espn_parse.py matchup league.json --period 2
    python3 espn_parse.py transactions league.json
    python3 espn_parse.py freeagents league.json

league.json is the raw JSON saved from the API (fetched via the signed-in
live browser). Never contains credentials.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

SLOT_NAMES = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "D/ST", 17: "K",
    20: "BE", 21: "IR", 23: "FLEX",
}

# ESPN proTeamIds -> abbreviations (2026)
PRO_TEAMS = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR",
    15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
    21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA",
    27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}

INJURY_FLAGS = {"QUESTIONABLE": "Q", "DOUBTFUL": "D", "OUT": "OUT",
                "INJURY_RESERVE": "IR"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def team_names(data):
    names = {}
    for t in data.get("teams", []):
        tid = t.get("id")
        name = (t.get("location", "") + " " + t.get("nickname", "")).strip()
        names[tid] = name or f"Team {tid}"
    return names


def player_line(entry):
    """One-line summary of a roster entry."""
    pool = entry.get("playerPoolEntry", {}) or {}
    player = pool.get("player", {}) or {}
    name = player.get("fullName", "?")
    pro = PRO_TEAMS.get(player.get("proTeamId"), "")
    inj = INJURY_FLAGS.get(player.get("injuryStatus", "ACTIVE"), "")
    proj = actual = None
    for s in player.get("stats", []) or []:
        if s.get("statSourceId") == 1 and proj is None:
            proj = s.get("appliedTotal")
        elif s.get("statSourceId") == 0 and actual is None:
            actual = s.get("appliedTotal")
    bits = [name]
    if pro:
        bits.append(f"({pro})")
    if inj:
        bits.append(f"[{inj}]")
    nums = []
    if proj is not None:
        nums.append(f"proj {proj:.1f}")
    if actual is not None:
        nums.append(f"actual {actual:.1f}")
    if nums:
        bits.append("- " + ", ".join(nums))
    return " ".join(bits)


def cmd_teams(data, _args):
    names = team_names(data)
    for t in data.get("teams", []):
        rec = (t.get("record", {}) or {}).get("overall", {}) or {}
        print(f"{t.get('id')}: {names.get(t.get('id'))} "
              f"({rec.get('wins', 0)}-{rec.get('losses', 0)}-{rec.get('ties', 0)})")


def cmd_roster(data, args):
    names = team_names(data)
    tid = args.team
    team = next((t for t in data.get("teams", []) if t.get("id") == tid), None)
    if not team:
        print(f"error: no team id {tid}", file=sys.stderr)
        raise SystemExit(1)
    print(f"== {names.get(tid)} ==")
    entries = ((team.get("roster", {}) or {}).get("entries", []) or [])
    starters = [e for e in entries if e.get("lineupSlotId") not in (20, 21)]
    bench = [e for e in entries if e.get("lineupSlotId") == 20]
    ir = [e for e in entries if e.get("lineupSlotId") == 21]
    order = [0, 2, 2, 4, 4, 6, 23, 16, 17]
    starters.sort(key=lambda e: order.index(e.get("lineupSlotId"))
                  if e.get("lineupSlotId") in order else 99)
    print("-- starters --")
    for e in starters:
        slot = SLOT_NAMES.get(e.get("lineupSlotId"), e.get("lineupSlotId"))
        print(f"  {slot:4} {player_line(e)}")
    if bench:
        print("-- bench --")
        for e in bench:
            print(f"  BE   {player_line(e)}")
    if ir:
        print("-- IR --")
        for e in ir:
            print(f"  IR   {player_line(e)}")


def matchup_side(side, names):
    if not side:
        return "bye"
    tid = side.get("teamId")
    pts = side.get("totalPoints")
    pts_s = f"{pts:.1f}" if isinstance(pts, (int, float)) else "?"
    return f"{names.get(tid, tid)} {pts_s}"


def cmd_matchup(data, args):
    names = team_names(data)
    sched = data.get("schedule", []) or []
    if args.period is not None:
        sched = [m for m in sched if m.get("matchupPeriodId") == args.period]
    for m in sched:
        mp = m.get("matchupPeriodId")
        print(f"Period {mp}: {matchup_side(m.get('away'), names)} @ "
              f"{matchup_side(m.get('home'), names)}")


def cmd_transactions(data, _args):
    names = team_names(data)
    txns = data.get("transactions", []) or []
    if not txns:
        print("no transactions")
        return
    for t in txns:
        ts = t.get("proposedDate")
        when = (datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                .strftime("%Y-%m-%d %H:%M UTC") if ts else "?")
        items = []
        for it in t.get("items", []) or []:
            frm = names.get(it.get("fromTeamId"), it.get("fromTeamId"))
            to = names.get(it.get("toTeamId"), it.get("toTeamId"))
            items.append(f"player {it.get('playerId')} {frm} -> {to}")
        print(f"[{t.get('status')}] {t.get('type')} {when}: " +
              "; ".join(items))


def cmd_freeagents(data, _args):
    players = data.get("players", []) or []
    rows = []
    for p in players:
        info = p.get("player", {}) or {}
        pool = p.get("playerPoolEntry", {}) or info
        name = info.get("fullName", "?")
        pro = PRO_TEAMS.get(info.get("proTeamId"), "")
        inj = INJURY_FLAGS.get(info.get("injuryStatus", "ACTIVE"), "")
        proj = None
        for s in info.get("stats", []) or []:
            if s.get("statSourceId") == 1:
                proj = s.get("appliedTotal")
                break
        owned = p.get("ownership", {}) or {}
        pct = owned.get("percentOwned")
        rows.append((pct if pct is not None else -1, name, pro, inj, proj))
    rows.sort(reverse=True)
    for pct, name, pro, inj, proj in rows[:60]:
        bits = [name]
        if pro:
            bits.append(f"({pro})")
        if inj:
            bits.append(f"[{inj}]")
        if proj is not None:
            bits.append(f"proj {proj:.1f}")
        if pct is not None and pct >= 0:
            bits.append(f"{pct:.0f}% owned")
        print(" ".join(bits))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("teams", "transactions", "freeagents"):
        p = sub.add_parser(name)
        p.add_argument("json_file")
    p = sub.add_parser("roster")
    p.add_argument("json_file")
    p.add_argument("--team", type=int, required=True)
    p = sub.add_parser("matchup")
    p.add_argument("json_file")
    p.add_argument("--period", type=int, default=None)
    args = ap.parse_args()

    data = load(args.json_file)
    {"teams": cmd_teams, "roster": cmd_roster, "matchup": cmd_matchup,
     "transactions": cmd_transactions,
     "freeagents": cmd_freeagents}[args.cmd](data, args)


if __name__ == "__main__":
    main()
