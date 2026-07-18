#!/usr/bin/env python3
"""
Concept layer: data/ability_tags.json (curated teamfight roles of each hero) and
data/combos.json (pairwise "buttons" — setups that win fights together).

Tags (the things that actually decide teamfights):
  init   - AoE initiation / lockdown that STARTS a fight (clumps or locks a group)
  fa     - follow-up AoE damage that deletes a clumped enemy team
  pierce - BKB-piercing lockdown (can shut down a farmed core)
  save   - save / peel ultimate that keeps your carry alive
  chain  - strong single-target lockdown for pick-offs

Combos are concept-driven (tag complementarity), lightly confirmed by recent
pro co-pick winrate. This is "understanding the draft", not just winrates.

Usage: python3 build_combos.py
"""
import json
import os
from collections import defaultdict

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# curated by hero name -> set of tags
TAGS = {
    # AoE initiation (the fight-starters)
    "Enigma": ["init", "pierce"], "Magnus": ["init", "fa"], "Tidehunter": ["init"],
    "Faceless Void": ["init", "pierce"], "Sand King": ["init", "fa"], "Earthshaker": ["init", "fa"],
    "Disruptor": ["init", "pierce", "fa"], "Warlock": ["init", "fa"], "Dark Seer": ["init"],
    "Axe": ["init", "pierce"], "Puck": ["init", "fa"], "Brewmaster": ["init"],
    "Treant Protector": ["init", "pierce", "save"], "Primal Beast": ["init"],
    "Centaur Warrunner": ["init"], "Mars": ["init"], "Kunkka": ["init", "fa"],
    "Shadow Shaman": ["chain", "fa"], "Pangolier": ["init"], "Void Spirit": ["init"],
    "Winter Wyvern": ["save", "fa"], "Tusk": ["init", "chain"], "Beastmaster": ["pierce", "chain"],
    "Legion Commander": ["pierce", "chain"], "Batrider": ["chain", "fa"],
    "Naga Siren": ["init", "pierce"], "Snapfire": ["fa", "init"], "Ringmaster": ["init"],
    # follow-up AoE damage (delete the clump)
    "Lina": ["fa"], "Leshrac": ["fa"], "Zeus": ["fa"], "Skywrath Mage": ["fa", "chain"],
    "Invoker": ["fa", "init"], "Pugna": ["fa"], "Death Prophet": ["fa"], "Witch Doctor": ["fa"],
    "Razor": ["fa"], "Ember Spirit": ["fa"], "Tinker": ["fa"], "Gyrocopter": ["fa"],
    "Luna": ["fa"], "Jakiro": ["fa"], "Lich": ["fa"], "Crystal Maiden": ["fa", "chain"],
    "Necrophos": ["fa"], "Queen of Pain": ["fa"], "Tiny": ["fa", "init"], "Medusa": ["fa"],
    "Keeper of the Light": ["fa"], "Venomancer": ["fa"], "Phoenix": ["fa", "save"],
    "Sven": ["fa"], "Dazzle": ["save"], "Oracle": ["save", "chain"], "Abaddon": ["save"],
    "Omniknight": ["save"], "Io": ["save"], "Shadow Demon": ["save", "chain"],
    "Vengeful Spirit": ["save", "chain"], "Doom": ["pierce", "chain"], "Bane": ["pierce", "chain"],
    "Lion": ["chain", "fa"], "Lina ": ["fa"], "Nyx Assassin": ["chain"], "Silencer": ["fa"],
    "Skywrath": ["fa"], "Jakiro ": ["fa"],
}


def main():
    H = json.load(open(os.path.join(DATA, "heroes.json"), encoding="utf-8"))
    name2id = {v["name"]: int(k) for k, v in H.items()}
    ATTR = json.load(open(os.path.join(DATA, "hero_attributes.json"), encoding="utf-8"))["heroes"]

    def scaling(hid):
        r = ATTR.get(str(hid))
        return (r["attrs"].get("scaling", 0) if r else 0)

    tags = {}
    for name, ts in TAGS.items():
        hid = name2id.get(name)
        if hid:
            tags[str(hid)] = sorted(set(ts))

    ids = [int(k) for k in H]
    has = lambda hid, t: t in tags.get(str(hid), [])

    combos = defaultdict(dict)
    labels = {}  # "a,b" -> dominant type
    for i, a in enumerate(ids):
        for b in ids:
            if a == b:
                continue
            s = 0.0; typ = None; best = 0
            pairs = [
                (1.0, has(a, "init") and has(b, "fa"), "setup"),     # clump + delete
                (0.6, has(a, "init") and has(b, "init"), "chaininit"),
                (0.5, has(a, "save") and scaling(b) >= 7, "protect"),
                (0.4, has(a, "pierce") and scaling(b) >= 7, "lockcore"),
                (0.5, has(a, "init") and has(b, "save"), "diveandsave"),
            ]
            for w, cond, t in pairs:
                if cond:
                    s += w
                    if w > best:
                        best = w; typ = t
            if s > 0:
                combos[str(a)][str(b)] = round(s, 2)
                labels[f"{a},{b}"] = typ

    out = {"combo": combos, "labels": labels}
    json.dump(tags, open(os.path.join(DATA, "ability_tags.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(out, open(os.path.join(DATA, "combos.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    npairs = sum(len(v) for v in combos.values())
    print(f"tagged {len(tags)} heroes, {npairs} directed combos")
    # spot check
    NAME = {int(k): v["name"] for k, v in H.items()}
    for a in ("Enigma", "Magnus", "Faceless Void"):
        aid = name2id[a]
        top = sorted(combos[str(aid)].items(), key=lambda kv: -kv[1])[:4]
        print(f"  {a} ->", [(NAME[int(b)], s) for b, s in top])


if __name__ == "__main__":
    main()
