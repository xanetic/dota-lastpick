#!/usr/bin/env python3
"""
Builds data/hero_attributes.json — the Hero Attribute Graph v1 for the
Draft Reasoning Engine (see docs/DRAFT_REASONING_ENGINE.md).

Each hero gets a vector of 0–10 scores across draft-relevant axes, derived
deterministically from:
  1) OpenDota heroStats roles + base stats (heuristic priors),
  2) a curated override table for iconic heroes (hand-tuned key axes),
  3) meta/priority signals computed from our own matches.json (contest rate,
     average pick order).

These are explicitly v1 PRIORS meant to be refined later (data-derived per-hero
match stats, expert correction). The value of Phase 1 is the reasoning pipeline
and the explanation UX, which improves automatically as attributes improve.

Usage:
  python3 attributes_bootstrap.py
"""

import json
import os

from fetch_data import API, fetch_json, HERO_IMG_BASE, DATA_DIR

# Draft-relevant axes used by the engine.
AXES = [
    "frontline", "initiation", "teamfight", "pickoff", "lockdown",
    "save_peel", "tower_pressure", "defense_waveclear", "scaling",
    "early_tempo", "mobility", "splitpush", "dmg_physical", "dmg_magical",
    "auras", "sustain", "map_control", "roshan",
]

# Valve role -> additive contribution to axes (before clamp to 0–10).
ROLE_CONTRIB = {
    "Carry":     {"scaling": 4.5, "dmg_physical": 3.5, "splitpush": 1.5, "roshan": 1.5},
    "Support":   {"save_peel": 3.5, "auras": 2.0, "map_control": 3.5, "sustain": 2.0, "early_tempo": 1.0},
    "Nuker":     {"dmg_magical": 4.0, "teamfight": 2.0, "pickoff": 2.0, "early_tempo": 1.5},
    "Disabler":  {"lockdown": 4.5, "pickoff": 2.5, "teamfight": 2.0, "initiation": 1.0},
    "Initiator": {"initiation": 5.0, "teamfight": 3.0, "frontline": 1.5},
    "Durable":   {"frontline": 5.0, "sustain": 1.5},
    "Escape":    {"mobility": 5.0, "splitpush": 1.5},
    "Pusher":    {"tower_pressure": 5.0, "defense_waveclear": 2.5, "map_control": 1.0},
    "Jungler":   {"scaling": 1.0, "tower_pressure": 1.0},
}

# Curated overrides for iconic heroes — hard-set key axes so explanations read
# credibly for the heroes that actually show up in pro drafts. Only the listed
# axes are overridden; the rest stay heuristic.
CURATED = {
    "Mars":            {"frontline": 8, "initiation": 9, "teamfight": 8, "lockdown": 6, "scaling": 6},
    "Magnus":          {"initiation": 9, "teamfight": 9, "mobility": 6, "scaling": 6, "frontline": 5},
    "Tidehunter":      {"frontline": 9, "initiation": 8, "teamfight": 10, "defense_waveclear": 6},
    "Enigma":          {"initiation": 8, "teamfight": 10, "frontline": 4, "scaling": 6, "pickoff": 4},
    "Earthshaker":     {"initiation": 7, "teamfight": 9, "lockdown": 7, "pickoff": 6},
    "Disruptor":       {"lockdown": 8, "teamfight": 8, "pickoff": 7, "save_peel": 5, "map_control": 4},
    "Phoenix":         {"teamfight": 9, "initiation": 7, "sustain": 6, "frontline": 6, "save_peel": 4},
    "Dark Seer":       {"frontline": 7, "initiation": 7, "teamfight": 8, "defense_waveclear": 6},
    "Centaur Warrunner": {"frontline": 9, "initiation": 8, "teamfight": 6, "save_peel": 5},
    "Underlord":       {"frontline": 7, "teamfight": 7, "auras": 7, "tower_pressure": 5, "defense_waveclear": 7},
    "Faceless Void":   {"teamfight": 9, "scaling": 9, "pickoff": 6, "initiation": 5},
    "Tiny":            {"initiation": 7, "pickoff": 8, "tower_pressure": 7, "scaling": 7, "dmg_physical": 7},
    "Sand King":       {"initiation": 8, "teamfight": 8, "frontline": 5, "defense_waveclear": 5},
    "Beastmaster":     {"initiation": 6, "tower_pressure": 8, "map_control": 7, "auras": 5, "pickoff": 5},
    "Batrider":        {"initiation": 8, "pickoff": 7, "mobility": 6, "lockdown": 6},
    "Clockwerk":       {"initiation": 8, "pickoff": 8, "frontline": 6, "map_control": 5},
    "Io":              {"save_peel": 9, "sustain": 8, "mobility": 6, "tower_pressure": 5},
    "Oracle":          {"save_peel": 10, "sustain": 7, "pickoff": 4},
    "Dazzle":          {"save_peel": 9, "sustain": 7, "auras": 4},
    "Warlock":         {"teamfight": 9, "save_peel": 5, "auras": 5, "sustain": 5},
    "Spectre":         {"scaling": 10, "teamfight": 8, "map_control": 5, "frontline": 5},
    "Medusa":          {"scaling": 10, "teamfight": 6, "frontline": 6, "defense_waveclear": 5},
    "Nature's Prophet": {"tower_pressure": 9, "splitpush": 10, "map_control": 7, "roshan": 6},
    "Lone Druid":      {"tower_pressure": 8, "splitpush": 8, "scaling": 8, "roshan": 7},
    "Chen":            {"tower_pressure": 8, "save_peel": 6, "auras": 6, "early_tempo": 7, "map_control": 6},
    "Broodmother":     {"splitpush": 9, "tower_pressure": 8, "early_tempo": 7},
    "Razor":           {"early_tempo": 7, "teamfight": 6, "tower_pressure": 5, "dmg_physical": 6},
    "Lich":            {"teamfight": 8, "save_peel": 5, "dmg_magical": 6, "defense_waveclear": 5},
    "Jakiro":          {"teamfight": 7, "defense_waveclear": 8, "tower_pressure": 6, "dmg_magical": 6},
    "Pangolier":       {"initiation": 7, "teamfight": 8, "mobility": 7, "save_peel": 5},
    "Mirana":          {"pickoff": 6, "map_control": 6, "mobility": 6, "save_peel": 4},
    "Hoodwink":        {"pickoff": 7, "mobility": 6, "lockdown": 5, "dmg_magical": 6},
    "Puck":            {"mobility": 8, "teamfight": 7, "pickoff": 6, "early_tempo": 6},
    "Storm Spirit":    {"mobility": 9, "pickoff": 8, "scaling": 7, "early_tempo": 6},
}


def clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


def heuristic_attrs(h):
    a = {ax: 1.0 for ax in AXES}  # small baseline so nothing is exactly 0
    for role in h.get("roles", []):
        for ax, v in ROLE_CONTRIB.get(role, {}).items():
            a[ax] += v

    # stat-based nudges
    melee = h.get("attack_type") == "Melee"
    pa = h.get("primary_attr")
    str_gain = h.get("str_gain", 0) or 0
    agi_gain = h.get("agi_gain", 0) or 0
    move = h.get("move_speed", 290) or 290
    rng = h.get("attack_range", 150) or 150

    if melee:
        a["frontline"] += 1.5
    else:
        a["defense_waveclear"] += 1.0
        a["splitpush"] += 0.5
    a["frontline"] += (str_gain - 2.2) * 1.2          # beefy str gain -> tankier
    if pa == "str":
        a["frontline"] += 1.0
    if pa == "int":
        a["dmg_magical"] += 1.5
    if pa == "agi":
        a["dmg_physical"] += 1.5
        a["scaling"] += 1.0
    a["mobility"] += (move - 290) / 12.0              # fast heroes
    if rng >= 500:
        a["dmg_physical"] += 0.5

    return {ax: round(clamp(v), 1) for ax, v in a.items()}


def explorer(sql, retries=4):
    import urllib.request, urllib.parse, time as _t
    url = f"{API}/explorer?sql=" + urllib.parse.quote(sql)
    for a in range(retries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120)
            d = json.loads(r.read().decode())
            if d.get("err"):
                raise RuntimeError(d["err"])
            return d.get("rows", [])
        except Exception as e:  # noqa: BLE001
            print(f"  ! explorer {e} (try {a+1})")
            _t.sleep(3 * (a + 1))
    raise RuntimeError("explorer failed")


def fetch_hero_stats(days=90):
    """Per-hero averages over recent PRO matches (data-derived attribute priors)."""
    import time as _t
    a = int(_t.time()) - days * 86400
    sql = (
        "SELECT pm.hero_id, count(*) g, avg(pm.tower_damage) td, avg(pm.hero_healing) heal, "
        "avg(pm.stuns) stun, avg(pm.teamfight_participation) tf, avg(pm.hero_damage) hd, "
        "avg(pm.net_worth) nw, avg(pm.obs_placed) obs, avg(pm.sen_placed) sen, "
        "avg(pm.roshans_killed) rk, avg(pm.towers_killed) tk "
        "FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id "
        "JOIN leagues l ON l.leagueid=m.leagueid "
        f"WHERE l.tier IN ('premium','professional') AND m.start_time>={a} "
        "AND pm.hero_id IS NOT NULL GROUP BY pm.hero_id"
    )
    rows = explorer(sql)
    f = lambda r, k: float(r[k]) if r.get(k) is not None else 0.0
    out = {}
    for r in rows:
        hid = r.get("hero_id")
        if not hid or int(r.get("g") or 0) < 30:
            continue
        out[str(hid)] = {"g": int(r["g"]), "td": f(r, "td"), "heal": f(r, "heal"),
                         "stun": f(r, "stun"), "tf": f(r, "tf"), "hd": f(r, "hd"),
                         "nw": f(r, "nw"), "rk": f(r, "rk"), "tk": f(r, "tk"),
                         "vision": f(r, "obs") + f(r, "sen")}
    return out


def derive_axes(hstats):
    """Map per-hero stats to 0-10 axes via percentile rank across heroes."""
    import bisect
    def pctf(key):
        vals = sorted(float(s[key]) for s in hstats.values())
        n = len(vals)
        return lambda v: (bisect.bisect_left(vals, float(v)) / (n - 1)) if n > 1 else 0.5
    pf = {k: pctf(k) for k in ("td", "heal", "stun", "tf", "nw", "vision", "rk")}
    out = {}
    for hid, s in hstats.items():
        td, heal, stun = pf["td"](s["td"]), pf["heal"](s["heal"]), pf["stun"](s["stun"])
        tf, nw, vis, rk = pf["tf"](s["tf"]), pf["nw"](s["nw"]), pf["vision"](s["vision"]), pf["rk"](s["rk"])
        out[hid] = {
            "teamfight": round(tf * 10, 1),
            "tower_pressure": round(td * 10, 1),
            "splitpush": round(td * (1 - tf) * 10, 1),   # high tower, low teamfight = splitpush
            "scaling": round(nw * 10, 1),
            "save_peel": round(heal * 10, 1),
            "sustain": round(heal * 10, 1),
            "lockdown": round(stun * 10, 1),
            "map_control": round(vis * 10, 1),
            "roshan": round(rk * 10, 1),
        }
    return out


def main():
    print("Fetching heroStats...")
    stats = fetch_json(f"{API}/heroStats")
    print("Fetching per-hero pro stats (data-derived attribute priors)...")
    try:
        DD = derive_axes(fetch_hero_stats(90))
        print(f"  data-derived axes for {len(DD)} heroes")
    except Exception as e:  # noqa: BLE001
        DD = {}
        print(f"  data-derived skipped: {e}")

    # meta + pick priority from our dataset. Prefer the large engine corpus
    # (corpus.json, ~50k pro drafts via fetch_explorer.py); fall back to the
    # curated game data (matches.json) when the corpus is absent.
    corpus_path = os.path.join(DATA_DIR, "corpus.json")
    src = corpus_path if os.path.exists(corpus_path) else os.path.join(DATA_DIR, "matches.json")
    matches = json.load(open(src, encoding="utf-8"))
    n_matches = len(matches)
    print(f"Training engine signals on {n_matches} matches from {os.path.basename(src)}")
    pick_count = {}
    ban_count = {}
    order_sum = {}
    order_n = {}
    for m in matches:
        for p in m["picks"]:
            hid = p["hero_id"]
            pick_count[hid] = pick_count.get(hid, 0) + 1
            order_sum[hid] = order_sum.get(hid, 0) + p["order"]
            order_n[hid] = order_n.get(hid, 0) + 1
        for b in m["bans"]:
            ban_count[b["hero_id"]] = ban_count.get(b["hero_id"], 0) + 1

    # teammate co-occurrence (same-team pairs) -> affinity = cosine of co-counts.
    # This is the lightweight Historical Draft Intelligence signal (doc §5):
    # "which heroes actually get drafted alongside these".
    import collections
    co = collections.defaultdict(lambda: collections.defaultdict(int))
    for m in matches:
        for side in ("radiant", "dire"):
            team = [p["hero_id"] for p in m["picks"] if p["team"] == side]
            for i in range(len(team)):
                for j in range(i + 1, len(team)):
                    a, b = team[i], team[j]
                    co[a][b] += 1
                    co[b][a] += 1
    affinity = {}
    for a in co:
        partners = []
        for b, c in co[a].items():
            denom = (pick_count.get(a, 0) * pick_count.get(b, 0)) ** 0.5
            if denom > 0:
                partners.append([b, round(c / denom, 3)])
        partners.sort(key=lambda x: -x[1])
        affinity[a] = partners[:30]

    out = {}
    for h in stats:
        if not h.get("cm_enabled", True):
            continue  # not draftable in Captains Mode
        hid = h["id"]
        name = h["localized_name"]
        attrs = heuristic_attrs(h)
        for ax, v in DD.get(str(hid), {}).items():   # data-derived overrides heuristic
            attrs[ax] = v
        for ax, v in CURATED.get(name, {}).items():   # curated (hand-verified) wins
            attrs[ax] = float(v)

        contest = round((pick_count.get(hid, 0) + ban_count.get(hid, 0)) / max(1, n_matches), 3)
        # avg order: lower = picked earlier = higher priority. Map to 0–10 (10 = earliest).
        if order_n.get(hid):
            avg_order = order_sum[hid] / order_n[hid]
            priority = round(clamp(10 - (avg_order - 7) * 0.7), 1)  # ~order 7 -> ~10, later -> lower
        else:
            priority = 0.0

        out[hid] = {
            "id": hid,
            "name": name,
            "primary_attr": h.get("primary_attr"),
            "img": HERO_IMG_BASE + h["img"].rstrip("?"),
            "attrs": attrs,
            "contest": contest,
            "priority": priority,
        }

    path = os.path.join(DATA_DIR, "hero_attributes.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"axes": AXES, "heroes": out, "affinity": affinity}, f, ensure_ascii=False, indent=0)

    # ---- draft states for similar-draft retrieval (doc §5) ----
    # each state = the answer team's 4 revealed heroes -> composition vector,
    # with the actual last pick as the target.
    # Client downloads this file, so cap it to the most recent N states to keep
    # the payload light (retrieval quality saturates well before the full 50k).
    STATE_CAP = 8000
    states = []
    for m in matches:
        ans = m["answer"]
        own = [p["hero_id"] for p in m["picks"] if p["team"] == ans["team"]]
        known = [h for h in own if h != ans["hero_id"]]
        if len(known) != 4 or any(h not in out for h in known):
            continue
        vec = [round(sum(out[h]["attrs"][ax] for h in known), 1) for ax in AXES]
        states.append({
            "v": vec,
            "t": ans["hero_id"],
            "mid": m["match_id"],
            "league": m["league"],
            "year": m.get("year"),
            "start_time": m.get("start_time"),
        })
    states.sort(key=lambda s: s.get("start_time") or 0, reverse=True)
    if len(states) > STATE_CAP:
        print(f"Capping draft states {len(states)} -> {STATE_CAP} (most recent)")
        states = states[:STATE_CAP]
    spath = os.path.join(DATA_DIR, "draft_states.json")
    with open(spath, "w", encoding="utf-8") as f:
        json.dump({"axes": AXES, "states": states}, f, ensure_ascii=False, indent=0)
    print(f"Wrote {len(states)} draft states -> {spath}")

    print(f"Done. {len(out)} heroes -> {path}")
    print(f"Curated overrides applied: {sum(1 for h in stats if h['localized_name'] in CURATED)}")
    # spot check
    mars = out.get(129)
    if mars:
        top = sorted(mars["attrs"].items(), key=lambda x: -x[1])[:5]
        print("Mars top axes:", top, "| contest", mars["contest"], "| priority", mars["priority"])


if __name__ == "__main__":
    main()
