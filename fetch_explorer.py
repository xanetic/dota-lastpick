#!/usr/bin/env python3
"""
Builds data/corpus.json — a large engine-training corpus of professional drafts,
pulled via OpenDota's /api/explorer SQL endpoint (bypasses the per-match rate
limit that capped fetch_data.py at ~990 matches).

This corpus is for the REASONING ENGINE only (contest/priority meta, teammate
affinity, similar-draft retrieval states). The game itself keeps using the
curated data/matches.json (which has player names + clean tournament names).

Records use the SAME schema as matches.json so attributes_bootstrap.py / tune.js
consume it unchanged (player names are absent — the engine does not use them).

Usage:
  python3 fetch_explorer.py --days 900 --window 21
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import datetime as dt
from collections import defaultdict

from fetch_data import API, DATA_DIR, load_patches, patch_for

UA = {"User-Agent": "Mozilla/5.0 (compatible; lastpick-engine/1.0)"}


def explorer(sql, retries=5):
    url = f"{API}/explorer?sql=" + urllib.parse.quote(sql)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("err"):
                raise RuntimeError(data["err"])
            return data.get("rows", [])
        except Exception as e:  # noqa: BLE001
            last = e
            code = getattr(e, "code", None)
            wait = 3.0 * (4 if code == 429 else 1) * (attempt + 1)
            print(f"  ! {e} (try {attempt+1}/{retries}), waiting {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"explorer failed: {last}")


def window_meta(a, b):
    sql = (
        "SELECT m.match_id, m.start_time, m.duration, m.radiant_win, "
        "m.radiant_score, m.dire_score, l.name AS league, l.tier "
        "FROM matches m JOIN leagues l ON m.leagueid=l.leagueid "
        f"WHERE l.tier IN ('premium','professional') "
        f"AND m.start_time>={a} AND m.start_time<{b} "
        "AND m.radiant_win IS NOT NULL"
    )
    return explorer(sql)


def window_picks(a, b):
    sql = (
        "SELECT pb.match_id, pb.is_pick, pb.hero_id, pb.team, pb.ord "
        "FROM picks_bans pb "
        "JOIN matches m ON m.match_id=pb.match_id "
        "JOIN leagues l ON l.leagueid=m.leagueid "
        f"WHERE l.tier IN ('premium','professional') "
        f"AND m.start_time>={a} AND m.start_time<{b}"
    )
    return explorer(sql)


def build(meta_rows, pb_rows, patches):
    meta = {r["match_id"]: r for r in meta_rows}
    by_match = defaultdict(list)
    for r in pb_rows:
        if r["hero_id"]:
            by_match[r["match_id"]].append(r)

    out = []
    for mid, rows in by_match.items():
        m = meta.get(mid)
        if not m:
            continue
        picks_rows = sorted([r for r in rows if r["is_pick"]], key=lambda x: x["ord"])
        bans_rows = [r for r in rows if not r["is_pick"]]
        if len(picks_rows) < 10:
            continue  # need a full captains-mode draft

        def side(t):
            return "radiant" if t == 0 else "dire"

        picks = [{"hero_id": r["hero_id"], "team": side(r["team"]), "order": r["ord"], "player": None}
                 for r in picks_rows]
        bans = [{"hero_id": r["hero_id"], "team": side(r["team"]), "order": r["ord"]} for r in bans_rows]
        last = picks_rows[-1]  # highest ord pick = the last pick
        # sanity: both teams present
        if sum(1 for p in picks if p["team"] == "radiant") < 4 or sum(1 for p in picks if p["team"] == "dire") < 4:
            continue
        st = m.get("start_time")
        out.append({
            "match_id": mid,
            "year": dt.datetime.utcfromtimestamp(st).year if st else None,
            "patch": patch_for(st, patches),
            "league": m.get("league") or "Pro match",
            "is_ti": False,
            "radiant_team": "Radiant",
            "dire_team": "Dire",
            "radiant_win": m.get("radiant_win"),
            "start_time": st,
            "duration": m.get("duration"),
            "radiant_score": m.get("radiant_score"),
            "dire_score": m.get("dire_score"),
            "picks": picks,
            "bans": bans,
            "answer": {"hero_id": last["hero_id"], "team": side(last["team"])},
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=900, help="how far back to pull")
    ap.add_argument("--window", type=int, default=21, help="window size in days")
    ap.add_argument("--pause", type=float, default=1.3, help="seconds between explorer calls")
    args = ap.parse_args()

    print("Loading patch calendar...")
    patches = load_patches()

    now = int(time.time())
    earliest = now - args.days * 86400
    step = args.window * 86400

    seen = set()
    corpus = []
    b = now
    while b > earliest:
        a = max(earliest, b - step)
        try:
            meta = window_meta(a, b)
            time.sleep(args.pause)
            pb = window_picks(a, b)
            time.sleep(args.pause)
        except Exception as e:  # noqa: BLE001
            print(f"  window {a}-{b} failed: {e}", file=sys.stderr)
            b = a
            continue
        recs = build(meta, pb, patches)
        added = 0
        for r in recs:
            if r["match_id"] in seen:
                continue
            seen.add(r["match_id"])
            corpus.append(r)
            added += 1
        d = dt.datetime.utcfromtimestamp(a).strftime("%Y-%m-%d")
        print(f"  {d}  +{added:4d}  (total {len(corpus)})")
        b = a

    corpus.sort(key=lambda m: m.get("start_time") or 0)
    path = os.path.join(DATA_DIR, "corpus.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False)
    print(f"\nWrote {len(corpus)} matches -> {path}")
    if corpus:
        yrs = sorted({m["year"] for m in corpus if m["year"]})
        print(f"Years: {yrs[0]}..{yrs[-1]}  | size {os.path.getsize(path)//1024} KB")


if __name__ == "__main__":
    main()
