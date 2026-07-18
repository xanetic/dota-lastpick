#!/usr/bin/env python3
"""
Proves the player-signature uplift: when the picking player is KNOWN (after Hint 2
/ in analysis), conditioning on that player's hero pool for the open role sharply
improves last-pick top-k.

Fetches account_id per pick for a slice of the newest test matches (windowed
explorer), then compares ranking WITHOUT vs WITH the signature feature.

Run: python3 eval_signature.py
"""

import json, os, time, urllib.parse, urllib.request, datetime as dt
from collections import defaultdict
from eval_v2 import (H, HERO_IDS, HID_SET, attrs, residual, needfit, rolefit,
                     open_positions, zscore, build_tables, POS, PLAYERS, make_state)

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
UA = {"User-Agent": "Mozilla/5.0 (compatible; lastpick-engine/1.0)"}
W = {"need": 0.3, "syn": 0.2, "cnt": 0.2, "role": 1.6, "meta": 1.0}  # best no-sig weights
W_SIG = 1.4


def explorer(sql, retries=5):
    url = f"https://api.opendota.com/api/explorer?sql=" + urllib.parse.quote(sql)
    for a in range(retries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120)
            d = json.loads(r.read().decode());
            if d.get("err"): raise RuntimeError(d["err"])
            return d.get("rows", [])
        except Exception as e:
            time.sleep(3*(a+1))
    return []


def signature(h, acct, openpos):
    pl = PLAYERS.get(str(acct))
    if not pl: return 0.0
    best = 0.0
    for p in openpos:
        d = pl["by_pos"].get(str(p))
        if d:
            t = sum(d.values())
            if t: best = max(best, d.get(str(h), 0)/t)
    if best == 0.0:
        d = pl["by_hero"]; t = sum(d.values())
        if t: best = d.get(str(h), 0)/t
    return best


def main():
    corpus = json.load(open(os.path.join(DATA, "corpus.json")))
    cm = [m for m in corpus if m.get("start_time")]; cm.sort(key=lambda m: m["start_time"])
    cut = int(len(cm)*0.8); train, test = cm[:cut], cm[cut:]
    sub = test[-1500:]  # newest test matches
    lo = min(m["start_time"] for m in sub); hi = max(m["start_time"] for m in sub)
    print(f"signature eval on {len(sub)} newest test matches "
          f"({dt.datetime.utcfromtimestamp(lo).date()}..{dt.datetime.utcfromtimestamp(hi).date()})")

    # fetch account per (match, hero) over the slice window
    acc = {}  # (match_id, hero_id) -> account_id
    b = hi + 86400
    step = 14*86400
    while b > lo:
        a = b - step
        rows = explorer("SELECT pm.match_id, pm.hero_id, pm.account_id FROM player_matches pm "
                        "JOIN matches m ON m.match_id=pm.match_id JOIN leagues l ON l.leagueid=m.leagueid "
                        f"WHERE l.tier IN ('premium','professional') AND m.start_time>={a} AND m.start_time<{b} "
                        "AND pm.account_id IS NOT NULL")
        for r in rows:
            acc[(r["match_id"], r["hero_id"])] = r["account_id"]
        time.sleep(1.2); b = a
    print(f"  fetched accounts for {len(acc)} (match,hero) rows")

    print("building train-only synergy/counter...")
    syn, cnt, base = build_tables(train)

    def components(m):
        st = make_state(m)
        if len(st["allies"]) != 4 or st["answer"] not in HID_SET: return None
        allies, enemies, excluded = st["allies"], st["enemies"], set(st["excluded"])
        R = residual(allies); openpos = open_positions(allies)
        raw = {"need":{}, "syn":{}, "cnt":{}, "role":{}, "meta":{}}
        for h in HERO_IDS:
            if h in excluded or not attrs(h): continue
            raw["need"][h]=needfit(h,R); raw["syn"][h]=sum(syn.get(h,{}).get(x,0) for x in allies)
            raw["cnt"][h]=sum(cnt.get(h,{}).get(e,0) for e in enemies); raw["role"][h]=rolefit(h,openpos)
            raw["meta"][h]=H[str(h)].get("contest",0)
        nz={k:zscore(v) for k,v in raw.items()}
        return st, openpos, nz

    n=0; base_hit=[0,0,0,0]; sig_hit=[0,0,0,0]; base_mrr=sig_mrr=0.0
    for m in sub:
        acct = acc.get((m["match_id"], m["answer"]["hero_id"]))
        if not acct: continue
        c = components(m)
        if not c: continue
        st, openpos, nz = c
        sig = {h: signature(h, acct, openpos) for h in nz["need"]}
        nzsig = zscore(sig)
        def order(withsig):
            sc={}
            for h in nz["need"]:
                s=(W["need"]*nz["need"].get(h,0)+W["syn"]*nz["syn"].get(h,0)+W["cnt"]*nz["cnt"].get(h,0)+
                   W["role"]*nz["role"].get(h,0)+W["meta"]*nz["meta"].get(h,0))
                if withsig: s+=W_SIG*nzsig.get(h,0)
                sc[h]=s
            return sorted(sc, key=lambda h:-sc[h])
        ans=st["answer"]
        try:
            rb=order(False).index(ans)+1; rs=order(True).index(ans)+1
        except ValueError:
            continue
        n+=1; base_mrr+=1/rb; sig_mrr+=1/rs
        for i,k in enumerate((1,3,5,10)):
            if rb<=k: base_hit[i]+=1
            if rs<=k: sig_hit[i]+=1
    if not n:
        print("no matches with account data"); return
    p=lambda x:f"{100*x/n:.1f}%"
    print(f"\nmatches with known player: {n}")
    print(f"  WITHOUT signature: top1 {p(base_hit[0])} top3 {p(base_hit[1])} top5 {p(base_hit[2])} top10 {p(base_hit[3])} mrr {base_mrr/n:.3f}")
    print(f"  WITH signature:    top1 {p(sig_hit[0])} top3 {p(sig_hit[1])} top5 {p(sig_hit[2])} top10 {p(sig_hit[3])} mrr {sig_mrr/n:.3f}")


if __name__ == "__main__":
    main()
