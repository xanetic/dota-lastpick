#!/usr/bin/env python3
"""
Enriches an existing data/matches.json (built by fetch_data.py) with extra fields
WITHOUT re-downloading every match detail:

  + start_time, duration, radiant_score, dire_score   (from per-league match lists)
  + patch                                              (computed from start_time)

Only ~31 league-list calls + 1 patch-constants call, so it's fast.

Usage:
  python3 augment_data.py
"""

import datetime as dt
import json
import os
import time
import urllib.request

from fetch_data import API, USER_AGENT, INTERNATIONALS, OTHER_LEAGUES, fetch_json, DATA_DIR


def load_patches():
    """Return list of (epoch_seconds, name) sorted ascending by date."""
    data = fetch_json(f"{API}/constants/patch")
    out = []
    for p in data:
        iso = p["date"].replace("Z", "+00:00")
        epoch = dt.datetime.fromisoformat(iso).timestamp()
        out.append((epoch, p["name"]))
    out.sort(key=lambda x: x[0])
    return out


def patch_for(ts, patches):
    if not ts:
        return None
    name = None
    for epoch, nm in patches:
        if ts >= epoch:
            name = nm
        else:
            break
    return name


def main():
    print("Loading patch constants...")
    patches = load_patches()
    print(f"  patches: {len(patches)} (latest: {patches[-1][1]})")

    # match_id -> extra fields, from every league's match list
    extra = {}
    leagues = {**INTERNATIONALS, **OTHER_LEAGUES}
    for i, (leagueid, name) in enumerate(leagues.items(), 1):
        print(f"[{i}/{len(leagues)}] {name} (league {leagueid})...")
        try:
            lst = fetch_json(f"{API}/leagues/{leagueid}/matches")
        except RuntimeError as e:
            print(f"  skip: {e}")
            continue
        for m in lst:
            extra[m["match_id"]] = {
                "start_time": m.get("start_time"),
                "duration": m.get("duration"),
                "radiant_score": m.get("radiant_score"),
                "dire_score": m.get("dire_score"),
            }
        time.sleep(0.6)

    path = os.path.join(DATA_DIR, "matches.json")
    matches = json.load(open(path, encoding="utf-8"))
    filled = 0
    for mt in matches:
        e = extra.get(mt["match_id"])
        if e:
            mt["start_time"] = e["start_time"]
            mt["duration"] = e["duration"]
            mt["radiant_score"] = e["radiant_score"]
            mt["dire_score"] = e["dire_score"]
            filled += 1
        mt["patch"] = patch_for(mt.get("start_time"), patches)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=0)

    import collections
    by_patch = collections.Counter(m.get("patch") for m in matches)
    print(f"\nDone. Enriched {filled}/{len(matches)} matches.")
    print("By patch:", dict(sorted((str(k), v) for k, v in by_patch.items())))


if __name__ == "__main__":
    main()
