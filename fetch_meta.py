#!/usr/bin/env python3
"""
data/meta.json — CURRENT-patch meta signal for the engine.

Priority = PRO drafts from the freshest patches in corpus.json (~80%); high-MMR
pubs (Divine+Immortal from /heroStats) fill sample for winrate (~20%). Gives a
per-hero `contest` (pick+ban priority now) and `winrate` (pro-weighted).

Usage: python3 fetch_meta.py [--days 160]
"""
import argparse
import json
import os
import urllib.request
from collections import defaultdict

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
UA = {"User-Agent": "Mozilla/5.0"}


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=160, help="recency window (days) for 'current' pro meta")
    args = ap.parse_args()

    corpus = json.load(open(os.path.join(DATA, "corpus.json"), encoding="utf-8"))
    tmax = max(m.get("start_time", 0) for m in corpus)
    cutoff = tmax - args.days * 86400
    recent = [m for m in corpus if m.get("start_time", 0) >= cutoff]
    patches = sorted({m.get("patch") for m in recent if m.get("patch")})
    print(f"corpus {len(corpus)} -> recent {len(recent)} matches, patches {patches}")

    pick = defaultdict(int); ban = defaultdict(int); win = defaultdict(int); games = defaultdict(int)
    for m in recent:
        rwin = m.get("radiant_win")
        for p in m.get("picks", []):
            h = int(p["hero_id"]); pick[h] += 1; games[h] += 1
            won = (p["team"] == "radiant") == bool(rwin)
            if won:
                win[h] += 1
        for b in m.get("bans", []):
            ban[int(b["hero_id"])] += 1

    # high-MMR pub winrate (Divine bracket 7 + Immortal 8) from live heroStats
    hs = get("https://api.opendota.com/api/heroStats")
    pub_w = {}; pub_p = {}
    for h in hs:
        hid = int(h["id"])
        hp = (h.get("7_pick") or 0) + (h.get("8_pick") or 0)
        hw = (h.get("7_win") or 0) + (h.get("8_win") or 0)
        pub_p[hid] = hp
        pub_w[hid] = (hw / hp) if hp else 0.5

    ids = [int(h["id"]) for h in hs]
    total_contest = sum(pick[h] + ban[h] for h in ids) or 1
    GP = sum(games.values()) / max(1, len(ids))  # avg games for shrink

    meta = {}
    for h in ids:
        g = games[h]
        pro_wr = (win[h] / g) if g else None
        # winrate: pro-dominant, pubs ~20% + shrink toward 0.5 for small samples
        pub_weight = 0.25 * max(g, 8)            # pubs contribute ~20%
        num = (pro_wr * g if pro_wr is not None else 0) + pub_w[h] * pub_weight + 0.5 * 8
        den = (g if pro_wr is not None else 0) + pub_weight + 8
        wr = num / den
        contest = (pick[h] + ban[h]) / total_contest
        meta[str(h)] = {
            "contest": round(contest, 5),
            "winrate": round(wr, 4),
            "pro_pick": pick[h], "pro_ban": ban[h], "pro_games": g,
            "pub_wr": round(pub_w[h], 4),
        }

    # normalize contest to 0..1 (relative to the most-contested hero)
    mx = max(v["contest"] for v in meta.values()) or 1
    for v in meta.values():
        v["contest"] = round(v["contest"] / mx, 4)

    out = {"patch": patches[-1] if patches else None, "window_days": args.days, "heroes": meta}
    json.dump(out, open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    top = sorted(meta.items(), key=lambda kv: -kv[1]["contest"])[:10]
    HN = {int(h["id"]): h["localized_name"] for h in hs}
    print("most contested now:", [(HN[int(k)], v["contest"], "wr", v["winrate"]) for k, v in top])
    print(f"wrote meta.json ({len(meta)} heroes)")


if __name__ == "__main__":
    main()
