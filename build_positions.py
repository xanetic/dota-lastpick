#!/usr/bin/env python3
"""
Builds data/hero_positions.json — per-hero role distribution P(position | hero)
over the positions 1..5 (carry / mid / offlane / pos4 / pos5), from PRO matches.

Position inference per player (OpenDota, no STRATZ needed):
  - rank players within their team by net_worth (descending);
  - the two lowest net_worth = supports (lowest = pos5, next = pos4);
  - the three cores (top net_worth) are split by lane_role:
        lane_role 1 -> pos1 (safelane carry), 2 -> pos2 (mid), 3 -> pos3 (offlane);
        ties / unknown fall back to the net_worth rank.
This is the standard net-worth-rank + lane heuristic; STRATZ positions can replace
it later for ground truth.

Output per hero: {"pos": {1..5: prob}, "flex": entropy0_1, "n": games}.

Usage:
  python3 build_positions.py --days 365
"""

import argparse
import json
import math
import os
import urllib.parse
import urllib.request
from collections import defaultdict

from fetch_data import API, DATA_DIR

UA = {"User-Agent": "Mozilla/5.0 (compatible; lastpick-engine/1.0)"}


def explorer(sql):
    url = f"{API}/explorer?sql=" + urllib.parse.quote(sql)
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180)
    d = json.loads(r.read().decode("utf-8"))
    if d.get("err"):
        raise RuntimeError(d["err"])
    return d.get("rows", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()

    sql = f"""
    SELECT hero_id, nw_rank, lane_role, count(*) AS c FROM (
      SELECT pm.hero_id,
             row_number() OVER (PARTITION BY pm.match_id, (pm.player_slot < 128)
                                ORDER BY pm.net_worth DESC NULLS LAST) AS nw_rank,
             pm.lane_role
      FROM player_matches pm
      JOIN matches m ON m.match_id = pm.match_id
      JOIN leagues l ON l.leagueid = m.leagueid
      WHERE l.tier IN ('premium','professional')
        AND m.start_time > extract(epoch from now() - interval '{args.days} days')
        AND pm.net_worth IS NOT NULL
    ) t
    GROUP BY hero_id, nw_rank, lane_role
    """
    print("Querying pro player positions (one explorer aggregate)...")
    rows = explorer(sql)
    print(f"  {len(rows)} (hero, rank, lane) buckets")

    def to_pos(nw_rank, lane_role):
        if nw_rank == 5:
            return 5
        if nw_rank == 4:
            return 4
        # cores: split by lane_role
        if lane_role == 2:
            return 2
        if lane_role == 1:
            return 1
        if lane_role == 3:
            return 3
        return nw_rank  # fallback

    pos_counts = defaultdict(lambda: defaultdict(int))  # hero -> pos -> count
    for r in rows:
        hid = r["hero_id"]
        if not hid:
            continue
        p = to_pos(r["nw_rank"], r["lane_role"])
        pos_counts[hid][p] += r["c"]

    out = {}
    for hid, pc in pos_counts.items():
        n = sum(pc.values())
        if n < 20:
            continue
        dist = {str(p): round(pc.get(p, 0) / n, 4) for p in range(1, 6)}
        # normalized entropy as flex score (0 = one role, 1 = spread across all)
        ent = 0.0
        for p in range(1, 6):
            x = pc.get(p, 0) / n
            if x > 0:
                ent -= x * math.log(x)
        flex = round(ent / math.log(5), 3)
        out[str(hid)] = {"pos": dist, "flex": flex, "n": n}

    path = os.path.join(DATA_DIR, "hero_positions.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Wrote positions for {len(out)} heroes -> {path}")
    # spot check a known flex hero and a hard support
    for hid in ("129", "26", "84"):  # Mars, Lion, Ogre
        if hid in out:
            o = out[hid]
            top = sorted(o["pos"].items(), key=lambda x: -float(x[1]))[:3]
            print(f"  hero {hid}: top {top} flex {o['flex']} n {o['n']}")


if __name__ == "__main__":
    main()
