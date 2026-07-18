#!/usr/bin/env python3
"""
Enriches data/matches.json picks with `account_id` (who actually played each hero),
so the reasoning engine can anchor positions to the REAL player roles instead of
hero priors. One OpenDota explorer pull (chunked) over player_matches.

Mapping key: (match_id, hero_id) -> account_id  [+ side sanity via player_slot].
Idempotent: re-running just refreshes account_id on each pick.

Usage: python3 enrich_accounts.py
"""
import json
import os
import sys

from fetch_explorer import explorer

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MJ = os.path.join(DATA, "matches.json")


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    matches = json.load(open(MJ, encoding="utf-8"))
    mids = sorted({int(m["match_id"]) for m in matches})
    print(f"{len(matches)} matches, {len(mids)} unique ids")

    acc = {}  # (match_id, hero_id) -> account_id
    side = {}  # (match_id, hero_id) -> 'radiant'/'dire'
    done = 0
    for ch in chunks(mids, 80):
        ids = ",".join(str(x) for x in ch)
        sql = (
            "SELECT match_id, account_id, hero_id, player_slot "
            f"FROM player_matches WHERE match_id IN ({ids})"
        )
        rows = explorer(sql)
        for r in rows:
            mid = r.get("match_id"); hid = r.get("hero_id")
            if mid is None or hid is None:
                continue
            acc[(int(mid), int(hid))] = r.get("account_id")
            side[(int(mid), int(hid))] = "radiant" if (r.get("player_slot", 0) < 128) else "dire"
        done += len(ch)
        print(f"  ...{done}/{len(mids)} ids, {len(acc)} player rows", file=sys.stderr)

    hit = 0; miss = 0
    for m in matches:
        mid = int(m["match_id"])
        for p in m.get("picks", []):
            key = (mid, int(p["hero_id"]))
            a = acc.get(key)
            p["account_id"] = a
            if a is not None:
                hit += 1
            else:
                miss += 1

    json.dump(matches, open(MJ, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"done: {hit} picks got account_id, {miss} missing. wrote {MJ}")


if __name__ == "__main__":
    main()
