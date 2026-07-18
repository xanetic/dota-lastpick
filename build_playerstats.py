#!/usr/bin/env python3
"""
One windowed sweep of PRO player_matches (OpenDota explorer) -> two artifacts:

  data/hero_positions.json  — P(position 1..5 | hero) + flex entropy + n.
  data/players.json         — per pro account: name/team + hero game counts
                              (overall and per position) = "signature heroes".

Position per player = net_worth rank within team, with cores split by lane_role
(2->mid, 1->carry, 3->offlane); two lowest net_worth = pos5/pos4. Raw rows are
pulled in time windows and ranked in Python (the server-side window function
times out on the full pro history).

Usage:
  python3 build_playerstats.py --days 365 --window 14
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

from fetch_data import API, DATA_DIR

UA = {"User-Agent": "Mozilla/5.0 (compatible; lastpick-engine/1.0)"}

MIN_HERO_GAMES = 20      # to keep a hero in hero_positions
MIN_PLAYER_GAMES = 25    # to keep an account in players.json (focus on pros/regulars)
TOP_HERO_PER_PLAYER = 60
TOP_HERO_PER_POS = 20


def explorer(sql, retries=5):
    url = f"{API}/explorer?sql=" + urllib.parse.quote(sql)
    last = None
    for attempt in range(retries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120)
            d = json.loads(r.read().decode("utf-8"))
            if d.get("err"):
                raise RuntimeError(d["err"])
            return d.get("rows", [])
        except Exception as e:  # noqa: BLE001
            last = e
            code = getattr(e, "code", None)
            wait = 3.0 * (4 if code == 429 else 1) * (attempt + 1)
            print(f"  ! {e} (try {attempt+1}/{retries}), waiting {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"explorer failed: {last}")


def notable_names():
    rows = explorer("SELECT account_id, name, team_name FROM notable_players")
    return {r["account_id"]: (r.get("name"), r.get("team_name")) for r in rows}


def to_pos(nw_rank, lane_role):
    if nw_rank >= 5:
        return 5
    if nw_rank == 4:
        return 4
    if lane_role == 2:
        return 2
    if lane_role == 1:
        return 1
    if lane_role == 3:
        return 3
    return nw_rank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--window", type=int, default=14)
    ap.add_argument("--pause", type=float, default=1.2)
    args = ap.parse_args()

    print("Fetching notable player names...")
    names = notable_names()
    print(f"  {len(names)} notable players")

    hero_pos = defaultdict(lambda: defaultdict(int))            # hero -> pos -> count
    player_hero = defaultdict(lambda: defaultdict(int))         # acct -> hero -> count
    player_pos_hero = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # acct->pos->hero->count

    now = int(time.time())
    earliest = now - args.days * 86400
    step = args.window * 86400
    b = now
    total_rows = 0
    while b > earliest:
        a = max(earliest, b - step)
        sql = (
            "SELECT pm.match_id, pm.player_slot, pm.account_id, pm.hero_id, "
            "pm.net_worth, pm.lane_role "
            "FROM player_matches pm "
            "JOIN matches m ON m.match_id = pm.match_id "
            "JOIN leagues l ON l.leagueid = m.leagueid "
            f"WHERE l.tier IN ('premium','professional') "
            f"AND m.start_time >= {a} AND m.start_time < {b} "
            "AND pm.net_worth IS NOT NULL AND pm.hero_id IS NOT NULL"
        )
        try:
            rows = explorer(sql)
        except Exception as e:  # noqa: BLE001
            print(f"  window {a}-{b} failed: {e}", file=sys.stderr)
            b = a
            continue
        total_rows += len(rows)

        # group into (match, team)
        teams = defaultdict(list)
        for r in rows:
            teams[(r["match_id"], r["player_slot"] < 128)].append(r)
        for members in teams.values():
            if len(members) != 5:
                continue
            members.sort(key=lambda x: (x["net_worth"] or 0), reverse=True)
            for rank, m in enumerate(members, 1):
                pos = to_pos(rank, m["lane_role"])
                hid = m["hero_id"]
                hero_pos[hid][pos] += 1
                acct = m["account_id"]
                if acct and acct > 0:
                    player_hero[acct][hid] += 1
                    player_pos_hero[acct][pos][hid] += 1

        import datetime as dt
        d = dt.datetime.utcfromtimestamp(a).strftime("%Y-%m-%d")
        print(f"  {d}  rows {len(rows):5d}  (total {total_rows})")
        time.sleep(args.pause)
        b = a

    # ---- hero_positions.json ----
    hp = {}
    for hid, pc in hero_pos.items():
        n = sum(pc.values())
        if n < MIN_HERO_GAMES:
            continue
        dist = {str(p): round(pc.get(p, 0) / n, 4) for p in range(1, 6)}
        ent = 0.0
        for p in range(1, 6):
            x = pc.get(p, 0) / n
            if x > 0:
                ent -= x * math.log(x)
        hp[str(hid)] = {"pos": dist, "flex": round(ent / math.log(5), 3), "n": n}
    p1 = os.path.join(DATA_DIR, "hero_positions.json")
    json.dump(hp, open(p1, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Wrote {len(hp)} hero positions -> {p1}")

    # ---- players.json ----
    players = {}
    for acct, hc in player_hero.items():
        n = sum(hc.values())
        if n < MIN_PLAYER_GAMES:
            continue
        nm, team = names.get(acct, (None, None))
        by_hero = dict(sorted(hc.items(), key=lambda x: -x[1])[:TOP_HERO_PER_PLAYER])
        by_pos = {}
        for pos, hh in player_pos_hero[acct].items():
            by_pos[str(pos)] = dict(sorted(hh.items(), key=lambda x: -x[1])[:TOP_HERO_PER_POS])
        players[str(acct)] = {
            "name": nm, "team": team, "n": n,
            "by_hero": {str(k): v for k, v in by_hero.items()},
            "by_pos": {p: {str(k): v for k, v in hh.items()} for p, hh in by_pos.items()},
        }
    p2 = os.path.join(DATA_DIR, "players.json")
    json.dump(players, open(p2, "w", encoding="utf-8"), ensure_ascii=False)
    named = sum(1 for v in players.values() if v["name"])
    print(f"Wrote {len(players)} players ({named} named) -> {p2}  | size {os.path.getsize(p2)//1024} KB")

    # spot checks
    for hid in ("129", "26", "84"):
        if hid in hp:
            top = sorted(hp[hid]["pos"].items(), key=lambda x: -float(x[1]))[:3]
            print(f"  hero {hid}: pos {top} flex {hp[hid]['flex']} n {hp[hid]['n']}")


if __name__ == "__main__":
    main()
