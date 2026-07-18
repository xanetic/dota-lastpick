#!/usr/bin/env python3
"""
data/stratz_matchups.json — authoritative current-patch synergy (with) & counter
(vs) from STRATZ at Divine/Immortal. `synergy` is STRATZ's win-rate advantage in
percentage points; we shrink by sample and store as a fraction.

Token via env STRATZ_TOKEN. Usage: STRATZ_TOKEN=... python3 fetch_stratz.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TOK = os.environ.get("STRATZ_TOKEN", "")
if not TOK:  # fallback to saved token file
    _tf = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".stratz_token")
    if os.path.exists(_tf):
        TOK = open(_tf).read().strip()
H = json.load(open(os.path.join(DATA, "heroes.json"), encoding="utf-8"))
IDS = sorted(int(k) for k in H)
NAME = {int(k): v["name"] for k, v in H.items()}
K = 60  # shrink constant for matchup sample


def gql(q, retries=5):
    body = json.dumps({"query": q}).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request("https://api.stratz.com/graphql", data=body,
                headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json",
                         "User-Agent": "STRATZ_API"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            if d.get("errors"):
                raise RuntimeError(str(d["errors"])[:200])
            return d["data"]
        except urllib.error.HTTPError as e:
            wait = 5 * (att + 1) * (4 if e.code == 429 else 1)
            print(f"  ! HTTP {e.code} (try {att+1}); wait {wait}s", file=sys.stderr); time.sleep(wait)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {e} (try {att+1})", file=sys.stderr); time.sleep(4 * (att + 1))
    raise RuntimeError("gql failed")


def main():
    if not TOK:
        print("set STRATZ_TOKEN"); sys.exit(1)
    syn = {}; cnt = {}
    for i, hid in enumerate(IDS):
        q = ('{ heroStats { matchUp(heroId:%d, bracketBasicIds:[DIVINE_IMMORTAL], take:260) '
             '{ vs { heroId2 matchCount synergy } with { heroId2 matchCount synergy } } } }') % hid
        d = gql(q)
        mu = d["heroStats"]["matchUp"]
        if not mu:
            continue
        mu = mu[0]
        sd = {}; cd = {}
        for w in mu.get("with", []):
            mc = w["matchCount"] or 0
            if mc < 20:
                continue
            sd[str(w["heroId2"])] = round((w["synergy"] / 100.0) * mc / (mc + K), 4)
        for v in mu.get("vs", []):
            mc = v["matchCount"] or 0
            if mc < 20:
                continue
            cd[str(v["heroId2"])] = round((v["synergy"] / 100.0) * mc / (mc + K), 4)
        if sd:
            syn[str(hid)] = sd
        if cd:
            cnt[str(hid)] = cd
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(IDS)}", file=sys.stderr)
        time.sleep(0.3)

    out = {"syn": syn, "cnt": cnt, "bracket": "DIVINE_IMMORTAL"}
    json.dump(out, open(os.path.join(DATA, "stratz_matchups.json"), "w"), separators=(",", ":"))
    npairs = sum(len(v) for v in syn.values()) + sum(len(v) for v in cnt.values())
    print(f"done: {len(syn)} heroes synergy, {len(cnt)} counter, {npairs} pairs")
    # spot check
    am = cnt.get("1", {})
    top = sorted(am.items(), key=lambda kv: -kv[1])[:4]
    print("Anti-Mage strong vs:", [(NAME[int(b)], v) for b, v in top])


if __name__ == "__main__":
    main()
