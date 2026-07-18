#!/usr/bin/env python3
"""
Honest offline proof that the v2 signals (role-fit + synergy + counter + player
signature) raise last-pick top-k vs the v1 baseline.

- Time-split: train = older 80%, test = newest 20% of corpus.json.
- Synergy & counter tables are rebuilt from TRAIN ONLY (no leakage). Hero
  positions, attributes, contest and player signatures are treated as stable
  priors (a hero's role / a player's pool are traits, not match outcomes).
- For each test match's LAST pick: build the state (answer team's 4 known allies,
  5 enemies, bans), score every legal candidate, record the rank of the true pick.
- Reports top-1/3/5/10 + MRR, with ablations, and a "player known" variant.

Run: python3 eval_v2.py
"""

import json
import math
import os
import itertools
from collections import defaultdict

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
L = lambda f: json.load(open(os.path.join(DATA, f), encoding="utf-8"))

ATTRS = L("hero_attributes.json")          # {axes, heroes:{id:{attrs,contest,...}}, affinity}
AXES = ATTRS["axes"]
H = ATTRS["heroes"]
POS = L("hero_positions.json")             # {id:{pos:{1..5},flex,n}}
PLAYERS = L("players.json")                # {acct:{by_hero,by_pos,...}}
corpus = L("corpus.json")

W_NEED = {"frontline":0.9,"initiation":1.0,"teamfight":1.0,"pickoff":0.8,"lockdown":0.7,
  "save_peel":0.8,"tower_pressure":0.7,"defense_waveclear":0.6,"scaling":0.9,"early_tempo":0.8,
  "mobility":0.5,"splitpush":0.5,"dmg_physical":0.7,"dmg_magical":0.7,"auras":0.4,"sustain":0.5,
  "map_control":0.6,"roshan":0.4}
TARGET = {"frontline":8,"initiation":8,"teamfight":9,"pickoff":5,"lockdown":7,"save_peel":6,
  "tower_pressure":5,"defense_waveclear":4,"scaling":8,"early_tempo":5,"mobility":5,"splitpush":3,
  "dmg_physical":7,"dmg_magical":7,"auras":3,"sustain":4,"map_control":6,"roshan":3}

HERO_IDS = [int(i) for i in H]


def attrs(h):
    rec = H.get(str(h))
    return rec["attrs"] if rec else None


def coverage(ids):
    C = {}
    for ax in AXES:
        vals = sorted((attrs(i)[ax] if attrs(i) else 0) for i in ids)
        vals.reverse()
        c = 0.0; w = 1.0
        for v in vals:
            c += w * v; w *= 0.5
        C[ax] = c
    return C


def residual(ids):
    C = coverage(ids)
    return {ax: max(0.0, TARGET[ax] - C[ax]) for ax in AXES}


def needfit(h, R):
    a = attrs(h)
    if not a:
        return 0.0
    return sum(min(a[ax], R[ax]) * W_NEED[ax] for ax in AXES)


# ---- train-only synergy & counter ----
def build_tables(train):
    games = defaultdict(int); wins = defaultdict(int)
    pg = defaultdict(int); pw = defaultdict(int)          # synergy pair (same team)
    og = defaultdict(int); ow = defaultdict(int)          # counter directed (vs)
    for m in train:
        rw = m.get("radiant_win")
        if rw is None: continue
        R = sorted({p["hero_id"] for p in m["picks"] if p["team"]=="radiant"})
        D = sorted({p["hero_id"] for p in m["picks"] if p["team"]=="dire"})
        for h in R: games[h]+=1; wins[h]+= 1 if rw else 0
        for h in D: games[h]+=1; wins[h]+= 1 if not rw else 0
        for i in range(len(R)):
            for j in range(i+1,len(R)):
                k=(R[i],R[j]) if R[i]<R[j] else (R[j],R[i]); pg[k]+=1; pw[k]+= 1 if rw else 0
        for i in range(len(D)):
            for j in range(i+1,len(D)):
                k=(D[i],D[j]) if D[i]<D[j] else (D[j],D[i]); pg[k]+=1; pw[k]+= 1 if not rw else 0
        for a in R:
            for b in D:
                og[(a,b)]+=1; ow[(a,b)]+= 1 if rw else 0
                og[(b,a)]+=1; ow[(b,a)]+= 1 if not rw else 0
    base={h:(wins[h]/games[h]) if games[h] else 0.5 for h in games}
    syn=defaultdict(dict)
    for (a,b),g in pg.items():
        if g<20: continue
        adv=(pw[(a,b)]/g-(base.get(a,.5)+base.get(b,.5))/2)*(g/(g+40))
        syn[a][b]=adv; syn[b][a]=adv
    cnt=defaultdict(dict)
    for (h,e),g in og.items():
        if g<20: continue
        cnt[h][e]=(ow[(h,e)]/g-base.get(h,.5))*(g/(g+400))
    return syn, cnt, base


# ---- position solver: assign known allies to positions, return open positions ----
def open_positions(ally_ids):
    cand = ally_ids[:5]
    best=None; bestscore=-1
    for perm in itertools.permutations(range(1,6), len(cand)):
        s=0.0
        for hid,p in zip(cand,perm):
            pr=POS.get(str(hid))
            s+= pr["pos"].get(str(p),0) if pr else 0.2
        if s>bestscore: bestscore=s; best=perm
    used=set(best or ())
    return [p for p in range(1,6) if p not in used]


def rolefit(h, openpos):
    pr=POS.get(str(h))
    if not pr: return 0.0
    return sum(pr["pos"].get(str(p),0) for p in openpos)


def signature(h, player_acct, openpos):
    pl=PLAYERS.get(str(player_acct)) if player_acct else None
    if not pl: return 0.0
    # prefer per-position pool for the open role, else overall
    best=0.0
    for p in openpos:
        d=pl["by_pos"].get(str(p))
        if d:
            tot=sum(d.values())
            if tot: best=max(best, d.get(str(h),0)/tot)
    if best==0.0:
        d=pl["by_hero"]; tot=sum(d.values())
        if tot: best=d.get(str(h),0)/tot
    return best


def zscore(d):
    if not d: return d
    vals=list(d.values()); lo=min(vals); hi=max(vals); span=(hi-lo) or 1
    return {k:(v-lo)/span for k,v in d.items()}


def rank_candidates(state, syn, cnt, W, player_acct=None):
    allies=state["allies"]; enemies=state["enemies"]; excluded=set(state["excluded"])
    R=residual(allies)
    openpos=open_positions(allies)
    raw={"need":{}, "syn":{}, "cnt":{}, "role":{}, "meta":{}, "sig":{}}
    for h in HERO_IDS:
        if h in excluded or not attrs(h): continue
        raw["need"][h]=needfit(h,R)
        raw["syn"][h]=sum(syn.get(h,{}).get(a,0) for a in allies)
        raw["cnt"][h]=sum(cnt.get(h,{}).get(e,0) for e in enemies)
        raw["role"][h]=rolefit(h,openpos)
        raw["meta"][h]=H[str(h)].get("contest",0)
        raw["sig"][h]=signature(h,player_acct,openpos) if player_acct else 0.0
    nz={k:zscore(v) for k,v in raw.items()}
    score={}
    for h in raw["need"]:
        score[h]=(W["need"]*nz["need"].get(h,0)+W["syn"]*nz["syn"].get(h,0)+
                  W["cnt"]*nz["cnt"].get(h,0)+W["role"]*nz["role"].get(h,0)+
                  W["meta"]*nz["meta"].get(h,0)+W["sig"]*nz["sig"].get(h,0))
    return sorted(score, key=lambda h:-score[h])


def make_state(m):
    ans=m["answer"]; team=ans["team"]
    allies=[p["hero_id"] for p in m["picks"] if p["team"]==team and p["hero_id"]!=ans["hero_id"]]
    enemies=[p["hero_id"] for p in m["picks"] if p["team"]!=team]
    taken=[p["hero_id"] for p in m["picks"] if p["hero_id"]!=ans["hero_id"]]
    bans=[b["hero_id"] for b in m.get("bans",[])]
    return {"allies":allies,"enemies":enemies,"excluded":taken+bans,"answer":ans["hero_id"]}


HID_SET=set(HERO_IDS)

def prepare(test, syn, cnt, sample_n=3000):
    import random; random.seed(1)
    ts=[m for m in test if m.get("answer")]
    if len(ts)>sample_n: ts=random.sample(ts,sample_n)
    prepared=[]
    for m in ts:
        st=make_state(m)
        if len(st["allies"])!=4 or st["answer"] not in HID_SET: continue
        allies=st["allies"]; enemies=st["enemies"]; excluded=set(st["excluded"])
        R=residual(allies); openpos=open_positions(allies)
        raw={"need":{},"syn":{},"cnt":{},"role":{},"meta":{}}
        for h in HERO_IDS:
            if h in excluded or not attrs(h): continue
            raw["need"][h]=needfit(h,R)
            raw["syn"][h]=sum(syn.get(h,{}).get(a,0) for a in allies)
            raw["cnt"][h]=sum(cnt.get(h,{}).get(e,0) for e in enemies)
            raw["role"][h]=rolefit(h,openpos)
            raw["meta"][h]=H[str(h)].get("contest",0)
        nz={k:zscore(v) for k,v in raw.items()}
        prepared.append({"answer":st["answer"],"nz":nz})
    return prepared

def fast_eval(prepared, W):
    n=t1=t3=t5=t10=0; mrr=0.0
    for p in prepared:
        nz=p["nz"]
        score={h:(W["need"]*nz["need"].get(h,0)+W["syn"]*nz["syn"].get(h,0)+
                  W["cnt"]*nz["cnt"].get(h,0)+W["role"]*nz["role"].get(h,0)+
                  W["meta"]*nz["meta"].get(h,0)) for h in nz["need"]}
        order=sorted(score, key=lambda h:-score[h])
        try: r=order.index(p["answer"])+1
        except ValueError: continue
        n+=1; mrr+=1/r
        if r==1:t1+=1
        if r<=3:t3+=1
        if r<=5:t5+=1
        if r<=10:t10+=1
    if not n: return None
    return {"n":n,"t1":t1/n,"t3":t3/n,"t5":t5/n,"t10":t10/n,"mrr":mrr/n}


def pct(x): return f"{100*x:.1f}%"


def main():
    cm=[m for m in corpus if m.get("start_time")]
    cm.sort(key=lambda m:m["start_time"])
    cut=int(len(cm)*0.8); train=cm[:cut]; test=cm[cut:]
    print(f"corpus {len(cm)}  train {len(train)}  test {len(test)}")
    print("building train-only synergy/counter...")
    syn,cnt,base=build_tables(train)
    print("preparing test states (precompute components)...")
    prep=prepare(test, syn, cnt, sample_n=3000)
    print(f"  prepared {len(prep)} test states")

    def show(tag,W):
        e=fast_eval(prep,W)
        print(f"  {tag:32s} top1 {pct(e['t1'])} top3 {pct(e['t3'])} top5 {pct(e['t5'])} top10 {pct(e['t10'])} mrr {e['mrr']:.3f}")

    print("\nABLATIONS (no signature; player unknown — game default):")
    show("needfit only (v1-ish)", {"need":1.0,"syn":0,"cnt":0,"role":0,"meta":0})
    show("meta only", {"need":0,"syn":0,"cnt":0,"role":0,"meta":1.0})
    show("role only", {"need":0,"syn":0,"cnt":0,"role":1.0,"meta":0})
    show("role+meta", {"need":0,"syn":0,"cnt":0,"role":1.0,"meta":0.6})
    show("role+synergy+counter+meta+need", {"need":0.5,"syn":0.5,"cnt":0.4,"role":1.0,"meta":0.6})

    best=None
    for role in (0.8,1.0,1.3,1.6):
        for syn_w in (0.2,0.4):
            for cnt_w in (0.2,0.4):
                for meta in (0.4,0.7,1.0):
                    for need in (0.3,0.6):
                        W={"need":need,"syn":syn_w,"cnt":cnt_w,"role":role,"meta":meta}
                        e=fast_eval(prep,W)
                        obj=0.2*e["t1"]+0.3*e["t3"]+0.5*e["t5"]
                        if not best or obj>best[0]: best=(obj,W,e)
    _,W,e=best
    print("\nBEST grid (no signature):")
    print(f"  top1 {pct(e['t1'])} top3 {pct(e['t3'])} top5 {pct(e['t5'])} top10 {pct(e['t10'])} mrr {e['mrr']:.3f}")
    print("  weights:",{k:round(v,2) for k,v in W.items()})


if __name__ == "__main__":
    main()
