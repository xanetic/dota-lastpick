#!/usr/bin/env python3
"""
Builds data/builds.json (final item builds from pro matches) + data/items.json
(item_id -> {name, img}) for the "Guess the build" mode.

For every pick in data/matches.json we pull the player's final inventory
(item_0..5 + neutral) via OpenDota explorer, attach hero/player/league/win, and
keep builds that have enough real items to be guessable.

Usage: python3 build_builds.py
"""
import json
import os
import sys
import urllib.request

from fetch_explorer import explorer

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
UA = {"User-Agent": "Mozilla/5.0"}


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    matches = json.load(open(os.path.join(DATA, "matches.json"), encoding="utf-8"))
    mids = sorted({int(m["match_id"]) for m in matches})
    print(f"{len(matches)} matches")

    # (match_id, hero_id) -> {items:[...6], neutral, slot}
    inv = {}
    done = 0
    for ch in chunks(mids, 80):
        ids = ",".join(str(x) for x in ch)
        sql = ("SELECT match_id, hero_id, player_slot, item_0,item_1,item_2,item_3,"
               "item_4,item_5,item_neutral FROM player_matches "
               f"WHERE match_id IN ({ids})")
        for r in explorer(sql):
            mid, hid = r.get("match_id"), r.get("hero_id")
            if mid is None or hid is None:
                continue
            inv[(int(mid), int(hid))] = {
                "items": [r.get(f"item_{i}") or 0 for i in range(6)],
                "neutral": r.get("item_neutral") or 0,
                "slot": r.get("player_slot", 0),
            }
        done += len(ch)
        print(f"  ...{done}/{len(mids)}", file=sys.stderr)

    # item id -> {name, img}
    req = urllib.request.Request("https://api.opendota.com/api/constants/items", headers=UA)
    consts = json.load(urllib.request.urlopen(req, timeout=60))
    by_id = {}
    for key, v in consts.items():
        if "id" in v and v.get("img"):
            by_id[int(v["id"])] = {"name": v.get("dname") or key, "img": v["img"]}

    builds = []
    used_items = set()
    for m in matches:
        mid = int(m["match_id"])
        radiant_win = m.get("radiant_win")
        for p in m.get("picks", []):
            key = (mid, int(p["hero_id"]))
            d = inv.get(key)
            if not d:
                continue
            real = [i for i in d["items"] if i and i in by_id]
            if len(real) < 3:        # skip near-empty inventories (hard/pointless to guess)
                continue
            is_radiant = d["slot"] < 128
            win = bool(radiant_win) if is_radiant else (not radiant_win)
            builds.append({
                "match_id": mid,
                "hero_id": int(p["hero_id"]),
                "player": p.get("player"),
                "items": d["items"],
                "neutral": d["neutral"],
                "win": win,
                "league": m.get("league"),
                "year": m.get("year"),
                "patch": m.get("patch"),
            })
            for i in d["items"]:
                if i:
                    used_items.add(i)
            if d["neutral"]:
                used_items.add(d["neutral"])

    items = {str(i): by_id[i] for i in used_items if i in by_id}

    json.dump(builds, open(os.path.join(DATA, "builds.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(items, open(os.path.join(DATA, "items.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(builds)} builds, {len(items)} distinct items")


if __name__ == "__main__":
    main()
