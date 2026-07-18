#!/usr/bin/env python3
"""
Learn the pick-ranking weights (replaces hand-tuned WEIGHTS) + calibrate.

Pointwise learning-to-rank: for each LAST-pick decision in the pro corpus,
features per legal candidate = [need, syn, cnt, role, meta, combo] (min-max
normalized within the slate, exactly as analyze.py does at inference). The hero
actually picked = positive, sampled others = negatives. Logistic regression
gives interpretable additive weights; a softmax temperature is fit for honest
probabilities.

Honest time-split (train 80% old / test 20% new); synergy/counter built from
TRAIN ONLY. Writes data/model.json (consumed by analyze.py, stdlib-only).

Run: python3 train_ranker.py
"""
import json
import math
import os
import random
import itertools
from collections import defaultdict

import numpy as np

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
L = lambda f: json.load(open(os.path.join(DATA, f), encoding="utf-8"))

ATTRS = L("hero_attributes.json"); AXES = ATTRS["axes"]; H = ATTRS["heroes"]
POS = L("hero_positions.json")
COMBO = L("combos.json").get("combo", {})
corpus = L("corpus.json")
HERO_IDS = [int(i) for i in H]
FEATS = ["need", "syn", "cnt", "role", "meta", "combo"]

W_NEED = {"frontline":0.9,"initiation":1.0,"teamfight":1.0,"pickoff":0.8,"lockdown":0.7,
  "save_peel":0.8,"tower_pressure":0.7,"defense_waveclear":0.6,"scaling":0.9,"early_tempo":0.8,
  "mobility":0.5,"splitpush":0.5,"dmg_physical":0.7,"dmg_magical":0.7,"auras":0.4,"sustain":0.5,
  "map_control":0.6,"roshan":0.4}
TARGET = {"frontline":8,"initiation":8,"teamfight":9,"pickoff":5,"lockdown":7,"save_peel":6,
  "tower_pressure":5,"defense_waveclear":4,"scaling":8,"early_tempo":5,"mobility":5,"splitpush":3,
  "dmg_physical":7,"dmg_magical":7,"auras":3,"sustain":4,"map_control":6,"roshan":3}


def attrs(h):
    r = H.get(str(h)); return r["attrs"] if r else None

def coverage(ids):
    C = {}
    for ax in AXES:
        vals = sorted((attrs(i)[ax] if attrs(i) else 0) for i in ids); vals.reverse()
        c = 0.0; w = 1.0
        for v in vals: c += w*v; w *= 0.5
        C[ax] = c
    return C

def residual(ids):
    C = coverage(ids); return {ax: max(0.0, TARGET[ax]-C[ax]) for ax in AXES}

def needfit(h, R):
    a = attrs(h)
    return sum(min(a[ax], R[ax])*W_NEED[ax] for ax in AXES) if a else 0.0

def build_tables(train):
    games=defaultdict(int); wins=defaultdict(int); pg=defaultdict(int); pw=defaultdict(int)
    og=defaultdict(int); ow=defaultdict(int)
    for m in train:
        rw=m.get("radiant_win")
        if rw is None: continue
        R=sorted({p["hero_id"] for p in m["picks"] if p["team"]=="radiant"})
        D=sorted({p["hero_id"] for p in m["picks"] if p["team"]=="dire"})
        for h in R: games[h]+=1; wins[h]+=1 if rw else 0
        for h in D: games[h]+=1; wins[h]+=1 if not rw else 0
        for i in range(len(R)):
            for j in range(i+1,len(R)):
                k=(R[i],R[j]); pg[k]+=1; pw[k]+=1 if rw else 0
        for i in range(len(D)):
            for j in range(i+1,len(D)):
                k=(D[i],D[j]); pg[k]+=1; pw[k]+=1 if not rw else 0
        for a in R:
            for b in D:
                og[(a,b)]+=1; ow[(a,b)]+=1 if rw else 0
                og[(b,a)]+=1; ow[(b,a)]+=1 if not rw else 0
    base={h:(wins[h]/games[h]) if games[h] else .5 for h in games}
    syn=defaultdict(dict)
    for (a,b),g in pg.items():
        if g<20: continue
        adv=(pw[(a,b)]/g-(base.get(a,.5)+base.get(b,.5))/2)*(g/(g+40)); syn[a][b]=adv; syn[b][a]=adv
    cnt=defaultdict(dict)
    for (h,e),g in og.items():
        if g<20: continue
        cnt[h][e]=(ow[(h,e)]/g-base.get(h,.5))*(g/(g+400))
    return syn, cnt

def open_positions(ally_ids):
    cand=ally_ids[:5]; best=None; bs=-1
    for perm in itertools.permutations(range(1,6), len(cand)):
        s=sum((POS.get(str(h),{}).get("pos",{}).get(str(p),0) if POS.get(str(h)) else .2) for h,p in zip(cand,perm))
        if s>bs: bs=s; best=perm
    used=set(best or ()); return [p for p in range(1,6) if p not in used]

def rolefit(h, op):
    pr=POS.get(str(h)); return sum(pr["pos"].get(str(p),0) for p in op) if pr else 0.0

def cpair(h,a): return max(COMBO.get(str(h),{}).get(str(a),0), COMBO.get(str(a),{}).get(str(h),0))
def combo_score(h, allies): return sum(cpair(h,a) for a in allies)

def mm(d):  # min-max to [0,1] within slate
    if not d: return d
    v=list(d.values()); lo=min(v); hi=max(v); span=(hi-lo) or 1
    return {k:(x-lo)/span for k,x in d.items()}

def slate_features(m, syn, cnt):
    ans=m["answer"]; team=ans["team"]
    allies=[p["hero_id"] for p in m["picks"] if p["team"]==team and p["hero_id"]!=ans["hero_id"]]
    if len(allies)!=4: return None
    enemies=[p["hero_id"] for p in m["picks"] if p["team"]!=team]
    excluded=set([p["hero_id"] for p in m["picks"] if p["hero_id"]!=ans["hero_id"]]+[b["hero_id"] for b in m.get("bans",[])])
    R=residual(allies); op=open_positions(allies)
    raw={f:{} for f in FEATS}
    for h in HERO_IDS:
        if h in excluded or not attrs(h): continue
        raw["need"][h]=needfit(h,R)
        raw["syn"][h]=sum(syn.get(h,{}).get(a,0) for a in allies)
        raw["cnt"][h]=sum(cnt.get(h,{}).get(e,0) for e in enemies)
        raw["role"][h]=rolefit(h,op)
        raw["meta"][h]=H[str(h)].get("contest",0)
        raw["combo"][h]=combo_score(h,allies)
    nz={f:mm(raw[f]) for f in FEATS}
    cands=list(raw["need"].keys())
    if ans["hero_id"] not in cands: return None
    return nz, cands, ans["hero_id"]


def main():
    random.seed(1); np.random.seed(1)
    cm=[m for m in corpus if m.get("start_time") and m.get("answer")]
    cm.sort(key=lambda m:m["start_time"])
    cut=int(len(cm)*0.8); train=cm[:cut]; test=cm[cut:]
    print(f"corpus {len(cm)} train {len(train)} test {len(test)}")
    syn,cnt=build_tables(train)

    # ---- build training rows (positive + sampled negatives) ----
    tr=[m for m in train if m.get("answer")]
    random.shuffle(tr); tr=tr[:7000]
    X=[]; Y=[]; NEG=15
    for m in tr:
        sf=slate_features(m,syn,cnt)
        if not sf: continue
        nz,cands,ans=sf
        negs=[h for h in cands if h!=ans]
        random.shuffle(negs); negs=negs[:NEG]
        for h,lab in [(ans,1)]+[(n,0) for n in negs]:
            X.append([nz[f].get(h,0) for f in FEATS]); Y.append(lab)
    X=np.array(X,float); Y=np.array(Y,float)
    print(f"train rows {len(Y)} ({int(Y.sum())} pos)")

    # ---- logistic regression (GD + L2) ----
    w=np.zeros(len(FEATS)); b=0.0; lr=0.5; lam=1e-3
    posw=(len(Y)-Y.sum())/max(1,Y.sum())   # upweight the rare positives
    sw=np.where(Y==1, posw, 1.0)
    for it in range(600):
        z=X@w+b; p=1/(1+np.exp(-z)); g=(p-Y)*sw
        gw=X.T@g/len(Y)+lam*w; gb=g.mean()
        w-=lr*gw; b-=lr*gb
    weights={f:round(float(w[i]),4) for i,f in enumerate(FEATS)}
    print("learned weights:", weights)

    # ---- eval helper ----
    def metrics(W):
        n=t1=t3=t5=t10=0; mrr=0.0
        for m in test:
            sf=slate_features(m,syn,cnt)
            if not sf: continue
            nz,cands,ans=sf
            score={h:sum(W[f]*nz[f].get(h,0) for f in FEATS) for h in cands}
            order=sorted(score,key=lambda h:-score[h])
            r=order.index(ans)+1; n+=1; mrr+=1/r
            t1+=r==1; t3+=r<=3; t5+=r<=5; t10+=r<=10
        return dict(n=n,t1=t1/n,t3=t3/n,t5=t5/n,t10=t10/n,mrr=mrr/n)

    hand={"need":0.3,"syn":0.2,"cnt":0.2,"role":1.6,"meta":1.0,"combo":0.0}
    mh=metrics(hand); ml=metrics(weights)
    pc=lambda x:f"{100*x:.1f}%"
    print(f"HAND    top1 {pc(mh['t1'])} top3 {pc(mh['t3'])} top5 {pc(mh['t5'])} top10 {pc(mh['t10'])} mrr {mh['mrr']:.3f}")
    print(f"LEARNED top1 {pc(ml['t1'])} top3 {pc(ml['t3'])} top5 {pc(ml['t5'])} top10 {pc(ml['t10'])} mrr {ml['mrr']:.3f}  (n={ml['n']})")

    # ---- temperature calibration: match mean top-prob to top1 accuracy ----
    tops=[]
    for m in test:
        sf=slate_features(m,syn,cnt)
        if not sf: continue
        nz,cands,ans=sf
        s=np.array([sum(weights[f]*nz[f].get(h,0) for f in FEATS) for h in cands])
        tops.append(s)
    def mean_top_prob(T):
        acc=0.0
        for s in tops:
            e=np.exp((s-s.max())/T); acc+=(e/e.sum()).max()
        return acc/len(tops)
    target=ml["t1"]; bestT=2.0; bestd=9
    for T in [x/10 for x in range(3,60)]:
        d=abs(mean_top_prob(T)-target)
        if d<bestd: bestd=d; bestT=T
    print(f"calibrated temperature {bestT:.1f} (mean top-prob {mean_top_prob(bestT):.3f} vs top1 {target:.3f})")

    model={"features":FEATS,"weights":weights,"temp":round(bestT,3),
           "uplift":{"hand":mh,"learned":ml},"note":"pointwise LTR, time-split"}
    json.dump(model, open(os.path.join(DATA,"model.json"),"w"), separators=(",",":"))
    print("wrote data/model.json")


if __name__ == "__main__":
    main()
