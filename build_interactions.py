#!/usr/bin/env python3
"""
Builds two interaction tables for Draft Reasoning Engine v2:

  data/counter.json  — hero-vs-hero counter advantage (how much hero H over/under-
                       performs its baseline when the ENEMY team has hero E).
                       Source: OpenDota /heroes/{id}/matchups (empirical vs-winrate).

  data/synergy.json  — same-team pair synergy advantage (how much a pair wins above
                       the average of their solo winrates). Source: our PRO corpus
                       (corpus.json) co-pick winrate. Pro-driven by design — pubs are
                       not trusted for "good draft" decisions.

Both use empirical-Bayes style shrinkage toward 0 for small samples.

Usage:
  python3 build_interactions.py
"""

import json
import os
import time
from collections import defaultdict

from fetch_data import API, DATA_DIR, fetch_json

UA_PAUSE = 1.0
COUNTER_K = 400      # shrinkage strength for counter (games)
SYNERGY_K = 40       # shrinkage strength for synergy (games together)


def build_counter():
    """counter[h]['vs'][e] = winrate(h when e is on the ENEMY team) - baseline_wr(h),
    shrunk by sample size. Directional, computed from the PRO corpus cross-team pairs
    (no API, pro-driven — consistent with the synergy table)."""
    corpus = json.load(open(os.path.join(DATA_DIR, "corpus.json"), encoding="utf-8"))
    games = defaultdict(int)
    wins = defaultdict(int)
    opp_g = defaultdict(int)   # (h, e) -> games where h faced e
    opp_w = defaultdict(int)   # (h, e) -> games h won facing e

    for m in corpus:
        rw = m.get("radiant_win")
        if rw is None:
            continue
        R = sorted({p["hero_id"] for p in m["picks"] if p["team"] == "radiant"})
        D = sorted({p["hero_id"] for p in m["picks"] if p["team"] == "dire"})
        for h in R:
            games[h] += 1; wins[h] += 1 if rw else 0
        for h in D:
            games[h] += 1; wins[h] += 1 if not rw else 0
        for a in R:
            for b in D:
                opp_g[(a, b)] += 1; opp_w[(a, b)] += 1 if rw else 0       # a faced b, a won if rw
                opp_g[(b, a)] += 1; opp_w[(b, a)] += 1 if not rw else 0   # b faced a

    base = {h: (wins[h] / games[h]) if games[h] else 0.5 for h in games}
    counter = {}
    rows = defaultdict(dict)
    for (h, e), g in opp_g.items():
        if g < 20:
            continue
        wr = opp_w[(h, e)] / g
        adv = (wr - base.get(h, 0.5)) * (g / (g + COUNTER_K))
        rows[h][str(e)] = round(adv, 4)
    for h in base:
        if str(h) in {str(x) for x in rows}:  # has at least one matchup row
            counter[str(h)] = {"base": round(base[h], 4), "vs": rows[h]}

    path = os.path.join(DATA_DIR, "counter.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(counter, f, ensure_ascii=False)
    pairs = sum(len(v["vs"]) for v in counter.values())
    print(f"Wrote counter for {len(counter)} heroes, {pairs} directed pairs -> {path}")


def build_synergy():
    """synergy[a][b] = winrate(a&b same team) - (wr[a]+wr[b])/2, shrunk."""
    corpus = json.load(open(os.path.join(DATA_DIR, "corpus.json"), encoding="utf-8"))
    games = defaultdict(int)          # hero -> games
    wins = defaultdict(int)           # hero -> wins
    pair_g = defaultdict(int)         # (a,b) -> games together
    pair_w = defaultdict(int)         # (a,b) -> wins together

    def key(a, b):
        return (a, b) if a < b else (b, a)

    for m in corpus:
        rw = m.get("radiant_win")
        if rw is None:
            continue
        for side in ("radiant", "dire"):
            won = rw if side == "radiant" else (not rw)
            team = sorted({p["hero_id"] for p in m["picks"] if p["team"] == side})
            for h in team:
                games[h] += 1
                wins[h] += 1 if won else 0
            for i in range(len(team)):
                for j in range(i + 1, len(team)):
                    k = key(team[i], team[j])
                    pair_g[k] += 1
                    pair_w[k] += 1 if won else 0

    wr = {h: (wins[h] / games[h]) if games[h] else 0.5 for h in games}
    synergy = defaultdict(dict)
    for (a, b), g in pair_g.items():
        if g < 20:
            continue
        pwr = pair_w[(a, b)] / g
        expected = (wr.get(a, 0.5) + wr.get(b, 0.5)) / 2
        adv = (pwr - expected) * (g / (g + SYNERGY_K))
        synergy[str(a)][str(b)] = round(adv, 4)
        synergy[str(b)][str(a)] = round(adv, 4)

    out = {"wr": {str(h): round(wr[h], 4) for h in wr}, "syn": synergy}
    path = os.path.join(DATA_DIR, "synergy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    pairs = sum(len(v) for v in synergy.values()) // 2
    print(f"Wrote synergy for {len(synergy)} heroes, {pairs} pairs -> {path}")


def main():
    print("Building synergy from PRO corpus (co-pick)...")
    build_synergy()
    print("Building counter from PRO corpus (cross-team)...")
    build_counter()


if __name__ == "__main__":
    main()
