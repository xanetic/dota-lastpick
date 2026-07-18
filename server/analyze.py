"""
Draft Reasoning Engine v2 — server-side analyzer.

Loads the pro-derived tables once (attributes, positions, signatures, synergy,
counter) and scores candidate last/next picks for a draft state. Validated
honestly (eval_v2.py / eval_signature.py): role-fit + meta dominate ranking
(top5 ~25% with no player, ~33% when the picking player is known); synergy /
counter are kept mainly for the explanation.

Pure stdlib. Used by server/app.py -> POST /api/analyze.
"""

import json
import math
import os
import random
import itertools
from collections import defaultdict

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_L = lambda f: json.load(open(os.path.join(DATA, f), encoding="utf-8"))

ATTRS = _L("hero_attributes.json")
AXES = ATTRS["axes"]
H = ATTRS["heroes"]                       # {id: {name, attrs, contest, ...}}
POS = _L("hero_positions.json")           # {id: {pos:{1..5}, flex, n}}
PLAYERS = _L("players.json")              # {acct: {name, team, by_hero, by_pos}}
SYN = _L("synergy.json")["syn"]           # {a: {b: adv}}
CNT = {k: v["vs"] for k, v in _L("counter.json").items()}  # {h: {e: adv}}

def _Lopt(f, default):
    try:
        return _L(f)
    except Exception:
        return default

_META = _Lopt("meta.json", {"heroes": {}})        # current-patch meta (fresh)
META = _META.get("heroes", {})
META_PATCH = _META.get("patch")
_CB = _Lopt("combos.json", {"combo": {}, "labels": {}})
COMBO = _CB.get("combo", {})                       # {a:{b:score}} teamfight combos
COMBO_LBL = _CB.get("labels", {})                  # {"a,b": type}
TAGS = _Lopt("ability_tags.json", {})              # {id: [init,fa,pierce,save,chain]}
W_COMBO = 0.16                                      # combo boost folded into synergy

# Blend STRATZ Divine/Immortal matchups (authoritative, current patch) on top of
# the pro-corpus synergy/counter tables — enriches every downstream signal.
_ST = _Lopt("stratz_matchups.json", {"syn": {}, "cnt": {}})
W_STRATZ = 1.0
for _a, _d in _ST.get("syn", {}).items():
    _t = SYN.setdefault(_a, {})
    for _b, _v in _d.items():
        _t[_b] = _t.get(_b, 0) + W_STRATZ * _v
for _a, _d in _ST.get("cnt", {}).items():
    _t = CNT.setdefault(_a, {})
    for _b, _v in _d.items():
        _t[_b] = _t.get(_b, 0) + W_STRATZ * _v
STRATZ_ON = bool(_ST.get("syn"))

NAME = {int(i): H[i]["name"] for i in H}
NAME_TO_ACCT = {}                          # nickname(lower) -> account_id
for acct, p in PLAYERS.items():
    if p.get("name"):
        NAME_TO_ACCT[p["name"].lower()] = acct

HERO_IDS = [int(i) for i in H]

W_NEED = {"frontline":0.9,"initiation":1.0,"teamfight":1.0,"pickoff":0.8,"lockdown":0.7,
  "save_peel":0.8,"tower_pressure":0.7,"defense_waveclear":0.6,"scaling":0.9,"early_tempo":0.8,
  "mobility":0.5,"splitpush":0.5,"dmg_physical":0.7,"dmg_magical":0.7,"auras":0.4,"sustain":0.5,
  "map_control":0.6,"roshan":0.4}
TARGET = {"frontline":8,"initiation":8,"teamfight":9,"pickoff":5,"lockdown":7,"save_peel":6,
  "tower_pressure":5,"defense_waveclear":4,"scaling":8,"early_tempo":5,"mobility":5,"splitpush":3,
  "dmg_physical":7,"dmg_magical":7,"auras":3,"sustain":4,"map_control":6,"roshan":3}
WEIGHTS = {"need":0.3, "syn":0.2, "cnt":0.2, "role":1.6, "meta":1.0}
W_SIG = 1.4
TEMP = 2.2  # softmax temperature for probabilities

POS_LABEL = {1:"carry (pos 1)", 2:"mid (pos 2)", 3:"offlane (pos 3)", 4:"pos 4", 5:"pos 5"}

# archetype prototypes over axes (same as engine.js)
ARCHETYPES = {
  "Teamfight": {"teamfight":10,"initiation":9,"frontline":7,"lockdown":6},
  "Deathball": {"tower_pressure":9,"early_tempo":8,"teamfight":7,"frontline":6},
  "Pickoff": {"pickoff":10,"lockdown":7,"mobility":7,"map_control":6},
  "Split Push": {"splitpush":10,"tower_pressure":7,"mobility":6},
  "Protect the Carry": {"scaling":10,"save_peel":9,"auras":6,"sustain":5},
  "High Ground Defense": {"defense_waveclear":9,"teamfight":7,"save_peel":6},
  "Tempo": {"early_tempo":9,"mobility":8,"pickoff":6},
}
AXIS_MEAN = {ax: (sum(H[i]["attrs"][ax] for i in H)/len(H)) for ax in AXES}


def attrs(h):
    r = H.get(str(h))
    return r["attrs"] if r else None


def meta_contest(h):
    m = META.get(str(h))
    return m.get("contest", 0) if m else H[str(h)].get("contest", 0)


def meta_wr(h):
    m = META.get(str(h))
    return m.get("winrate") if m else None


def hero_tags(h):
    return TAGS.get(str(h), [])


def _cpair(h, a):
    """Combo is mutual: a follow-up hero benefits from an initiator ally and
    vice-versa, so take the stronger of both directions."""
    return max(COMBO.get(str(h), {}).get(str(a), 0), COMBO.get(str(a), {}).get(str(h), 0))


def combo_score(h, allies):
    return sum(_cpair(h, a) for a in allies)


def combos_for(h, allies):
    out = []
    for a in allies:
        s = _cpair(h, a)
        if s > 0:
            out.append({"id": a, "name": NAME.get(a), "score": s,
                        "type": COMBO_LBL.get(f"{h},{a}") or COMBO_LBL.get(f"{a},{h}") or "setup"})
    out.sort(key=lambda x: -x["score"])
    return out[:3]


def team_concept(ids, enemy_ids=None):
    """The win-condition checklist: does the draft have the pieces to win a fight?"""
    ids = [int(h) for h in ids if attrs(h)]
    tagged = lambda t: any(t in hero_tags(h) for h in ids)
    cov = coverage(ids)
    have = {
        "initiation": tagged("init") or cov["initiation"] >= 8,
        "followup":   tagged("fa") or cov["dmg_magical"] >= 9,
        "save":       tagged("save") or cov["save_peel"] >= 7,
        "pierce":     tagged("pierce"),
        "frontline":  cov["frontline"] >= 8,
        "lockdown":   tagged("init") or cov["lockdown"] >= 8,
    }
    missing = [k for k, v in have.items() if not v]
    return {"have": have, "missing": missing}


def coverage(ids):
    C = {}
    for ax in AXES:
        vals = sorted(((attrs(i)[ax] if attrs(i) else 0) for i in ids), reverse=True)
        c = 0.0; w = 1.0
        for v in vals:
            c += w*v; w *= 0.5
        C[ax] = c
    return C


def residual(ids):
    C = coverage(ids)
    return {ax: max(0.0, TARGET[ax]-C[ax]) for ax in AXES}


def needfit(h, R):
    a = attrs(h)
    if not a: return 0.0, []
    fills = []
    s = 0.0
    for ax in AXES:
        f = min(a[ax], R[ax]) * W_NEED[ax]
        if f > 0.01: fills.append((ax, f))
        s += f
    fills.sort(key=lambda x:-x[1])
    return s, fills


def player_posdist(acct):
    """Normalized career position distribution for an account, or None."""
    pl = PLAYERS.get(str(acct)) if acct else None
    if not pl or not pl.get("by_pos"): return None
    tot = sum(sum(d.values()) for d in pl["by_pos"].values())
    if not tot: return None
    return {int(p): sum(d.values())/tot for p, d in pl["by_pos"].items()}


def slot_posdist(hid, acct):
    """Position distribution for an ally slot: prefer the REAL player's role
    (career by_pos) over the hero prior — a Lone Druid on an offlaner sits at
    pos 3, not carry. Falls back to the hero's pos prior, then uniform."""
    pd = player_posdist(acct)
    if pd: return pd
    pr = POS.get(str(hid))
    if pr: return {int(p): v for p, v in pr["pos"].items()}
    return {p: 0.2 for p in range(1, 6)}


def open_positions(ally_ids, ally_accounts=None):
    cand = ally_ids[:5]
    accts = (list(ally_accounts) + [None]*len(cand))[:len(cand)] if ally_accounts else [None]*len(cand)
    dists = [slot_posdist(h, a) for h, a in zip(cand, accts)]
    best=None; bestscore=-1
    for perm in itertools.permutations(range(1,6), len(cand)):
        s=sum(dists[i].get(p,0) for i,p in enumerate(perm))
        if s>bestscore: bestscore=s; best=perm
    used=set(best or ())
    return [p for p in range(1,6) if p not in used]


def rolefit(h, openpos):
    pr=POS.get(str(h))
    if not pr: return 0.0
    return sum(pr["pos"].get(str(p),0) for p in openpos)


def signature(h, acct, openpos):
    pl = PLAYERS.get(str(acct)) if acct else None
    if not pl: return 0.0
    best=0.0
    for p in openpos:
        d = pl["by_pos"].get(str(p))
        if d:
            t=sum(d.values())
            if t: best=max(best, d.get(str(h),0)/t)
    if best==0.0:
        d=pl["by_hero"]; t=sum(d.values())
        if t: best=d.get(str(h),0)/t
    return best


def _znorm(d):
    if not d: return {}
    vals=list(d.values()); lo=min(vals); hi=max(vals); span=(hi-lo) or 1
    return {k:(v-lo)/span for k,v in d.items()}


def classify_archetype(ids):
    C = coverage(ids)
    rel = {ax: C[ax]/((AXIS_MEAN[ax] or 1)*5) for ax in AXES}
    best=None; bs=-1; second=None
    for name, proto in ARCHETYPES.items():
        dot=np=nc=0.0
        for ax in AXES:
            p=proto.get(ax,0); dot+=p*rel[ax]; np+=p*p; nc+=rel[ax]*rel[ax]
        cos=dot/((math.sqrt(np)*math.sqrt(nc)) or 1)
        if cos>bs: second=best; bs=cos; best=name
    return {"primary":best, "secondary":second}


def resolve_player(allies_state, answer_hero, picker):
    """picker may be an account_id (int/str) or a nickname; return account_id or None."""
    if picker is None: return None
    s=str(picker)
    if s.isdigit() and s in PLAYERS: return s
    a=NAME_TO_ACCT.get(s.lower())
    return a


def analyze(allies, enemies, bans, answer=None, picker=None, ally_accounts=None):
    # keep heroes and their accounts aligned BEFORE filtering invalids
    pairs=[(int(h), (ally_accounts[i] if ally_accounts and i < len(ally_accounts) else None))
           for i, h in enumerate(allies) if attrs(h)]
    allies=[h for h,_ in pairs]
    ally_acc=[a for _,a in pairs]
    enemies=[int(x) for x in enemies if x]
    bans=[int(x) for x in bans if x]
    excluded=set(allies)|set(enemies)|set(bans)
    if answer: excluded.discard(int(answer))  # answer itself is the target, not excluded as candidate

    R=residual(allies)
    # Position Solver anchored to the REAL ally players' career roles (not hero
    # priors): if the offlaner is on Lone Druid, carry stays open for the picker.
    openpos=open_positions(allies, ally_acc)
    acct=resolve_player(allies, answer, picker)
    # If we also KNOW the picker and the solver left several slots open, narrow to
    # the picker's dominant position when it's among the open ones.
    if acct and len(openpos) > 1:
        pd = player_posdist(acct)
        if pd:
            dom = int(max(pd, key=pd.get))
            if dom in openpos: openpos = [dom]

    raw={"need":{}, "syn":{}, "cnt":{}, "role":{}, "meta":{}, "sig":{}}
    fills_by={}
    for h in HERO_IDS:
        if h in excluded or not attrs(h): continue
        nf, fills = needfit(h, R)
        raw["need"][h]=nf; fills_by[h]=fills
        raw["syn"][h]=sum(SYN.get(str(h),{}).get(str(a),0) for a in allies)+W_COMBO*combo_score(h, allies)
        raw["cnt"][h]=sum(CNT.get(str(h),{}).get(str(e),0) for e in enemies)
        raw["role"][h]=rolefit(h, openpos)
        raw["meta"][h]=meta_contest(h)
        raw["sig"][h]=signature(h, acct, openpos) if acct else 0.0
    nz={k:_znorm(v) for k,v in raw.items()}
    score={}
    for h in raw["need"]:
        s=(WEIGHTS["need"]*nz["need"].get(h,0)+WEIGHTS["syn"]*nz["syn"].get(h,0)+
           WEIGHTS["cnt"]*nz["cnt"].get(h,0)+WEIGHTS["role"]*nz["role"].get(h,0)+
           WEIGHTS["meta"]*nz["meta"].get(h,0))
        if acct: s+=W_SIG*nz["sig"].get(h,0)
        score[h]=s
    order=sorted(score, key=lambda h:-score[h])

    # softmax probabilities (temperature)
    mx=max(score.values()) if score else 0
    exps={h:math.exp((score[h]-mx)/TEMP) for h in score}
    Z=sum(exps.values()) or 1
    prob={h:exps[h]/Z for h in score}

    def hero(h): return {"id":h, "name":NAME.get(h, f"#{h}"), "prob":round(prob[h],4)}
    candidates=[hero(h) for h in order[:8]]

    needs=[{"axis":ax, "v":R[ax]*W_NEED[ax]} for ax in AXES]
    needs=[n for n in needs if n["v"]>0.2]
    needs.sort(key=lambda x:-x["v"]); needs=needs[:4]

    out={
        "open_positions":[{"pos":p, "label":POS_LABEL[p]} for p in openpos],
        "needs":needs,
        "candidates":candidates,
        "archetype":classify_archetype(allies+([int(answer)] if answer else [])),
        "player_known":bool(acct),
    }

    if answer:
        ans=int(answer)
        rank=order.index(ans)+1 if ans in order else None
        # decomposition for the actual pick
        syns=sorted(((a, SYN.get(str(ans),{}).get(str(a),0)) for a in allies),
                    key=lambda x:-x[1])
        syns=[{"id":a, "name":NAME.get(a), "adv":round(v,3)} for a,v in syns if v>0.005][:3]
        cnts=sorted(((e, CNT.get(str(ans),{}).get(str(e),0)) for e in enemies),
                    key=lambda x:-x[1])
        cnts=[{"id":e, "name":NAME.get(e), "adv":round(v,3)} for e,v in cnts if v>0.005][:3]
        sig_note=None
        if acct:
            pl=PLAYERS.get(acct)
            tot=sum(pl["by_hero"].values()) or 1
            g=pl["by_hero"].get(str(ans),0)
            share=g/tot
            # only call it a "signature" when it's actually a comfort pick for them,
            # not any hero they've touched a couple of times
            if g>=10 and share>=0.06:
                sig_note={"name":pl.get("name"), "games":g, "share":round(share,3)}
        out["answer"]={
            "id":ans, "name":NAME.get(ans), "rank":rank, "total":len(order),
            "prob":round(prob.get(ans,0),4),
            # only claim "fills X" where the hero is genuinely strong on that axis
            "fills":[{"axis":ax} for ax,_ in fills_by.get(ans,[]) if (attrs(ans) or {}).get(ax,0) >= 4.5][:3],
            "synergies":syns, "counters":cnts, "signature":sig_note,
            "combos":combos_for(ans, allies),                 # teamfight "buttons" with allies
            "meta":round(meta_contest(ans),3),
            "winrate":meta_wr(ans),
            "tags":hero_tags(ans),
            "fits_open_role":round(rolefit(ans, openpos),3),
        }
        out["concept"]=team_concept(allies+[ans], enemies)    # win-condition checklist
        # confidence = calibrated-ish prob the pick is in top of distribution
        top_prob=prob[order[0]] if order else 0
        out["confidence"]=round(prob.get(ans,0)/ (top_prob or 1), 3)
    else:
        out["confidence"]=round(prob[order[0]],3) if order else 0.0

    return out


# ===================================================================== vs-AI
def _score_picks(allies, enemies, bans):
    """Rank every available hero for the team that is about to pick.
    Same components/weights as analyze() (role/synergy/counter/need/meta),
    no player signatures (the AI has no fixed player)."""
    excluded=set(allies)|set(enemies)|set(bans)
    R=residual(allies)
    openpos=open_positions(allies)
    raw={"need":{}, "syn":{}, "cnt":{}, "role":{}, "meta":{}}
    for h in HERO_IDS:
        if h in excluded or not attrs(h): continue
        nf,_=needfit(h,R)
        raw["need"][h]=nf
        raw["syn"][h]=sum(SYN.get(str(h),{}).get(str(a),0) for a in allies)+W_COMBO*combo_score(h, allies)
        raw["cnt"][h]=sum(CNT.get(str(h),{}).get(str(e),0) for e in enemies)
        raw["role"][h]=rolefit(h, openpos)
        raw["meta"][h]=meta_contest(h)
    nz={k:_znorm(v) for k,v in raw.items()}
    score={}
    for h in raw["need"]:
        score[h]=(WEIGHTS["need"]*nz["need"].get(h,0)+WEIGHTS["syn"]*nz["syn"].get(h,0)+
                  WEIGHTS["cnt"]*nz["cnt"].get(h,0)+WEIGHTS["role"]*nz["role"].get(h,0)+
                  WEIGHTS["meta"]*nz["meta"].get(h,0))
    return score


def ai_pick(ai_team, my_team, bans, difficulty="medium"):
    ai_team=[int(x) for x in ai_team if attrs(x)]
    my_team=[int(x) for x in my_team if x]
    bans=[int(x) for x in bans if x]
    score=_score_picks(ai_team, my_team, bans)
    order=sorted(score, key=lambda h:-score[h])
    if not order: return None
    if difficulty=="hard":
        pick=order[0]                               # optimal: best role/synergy/counter
    elif difficulty=="easy":
        pick=random.choice(order[:50])              # weak: any half-decent hero
    else:                                           # medium: softmax over the top
        pool=order[:15]; mx=score[pool[0]]
        ws=[math.exp((score[h]-mx)/0.15) for h in pool]
        r=random.random()*sum(ws); acc=0.0; pick=pool[0]
        for h,w in zip(pool,ws):
            acc+=w
            if r<=acc: pick=h; break
    return {"hero_id":pick, "name":NAME.get(pick)}


def ai_ban(ai_team, my_team, bans, difficulty="medium"):
    """Captains-Mode ban: deny the hero that is currently strongest FOR THE PLAYER
    (or high-meta early). Scored from the player's perspective."""
    ai_team=[int(x) for x in ai_team if x]
    my_team=[int(x) for x in my_team if x]
    bans=[int(x) for x in bans if x]
    score=_score_picks(my_team, ai_team, bans)   # value of each hero to the player
    order=sorted(score, key=lambda h:-score[h])
    if not order: return None
    if difficulty=="hard":
        pick=order[0]
    elif difficulty=="easy":
        pick=random.choice(order[:50])
    else:
        pick=random.choice(order[:12])
    return {"hero_id":pick, "name":NAME.get(pick)}


EVAL_W = {"roles":1.5,"synergy":1.0,"counter":1.2,"teamfight":0.8,
          "control":0.7,"scaling":0.7,"balance":0.8,"meta":0.7}


def solve_assignment(ids, accounts=None):
    """Assign heroes to positions 1..5 (max-fit permutation, player-anchored if
    accounts given). Returns {hero_id: pos}."""
    cand=[int(h) for h in ids][:5]
    accts=(list(accounts)+[None]*len(cand))[:len(cand)] if accounts else [None]*len(cand)
    dists=[slot_posdist(h,a) for h,a in zip(cand,accts)]
    best=None; bs=-1
    for perm in itertools.permutations(range(1,6), len(cand)):
        s=sum(dists[i].get(p,0) for i,p in enumerate(perm))
        if s>bs: bs=s; best=perm
    return {cand[i]:best[i] for i in range(len(cand))} if best else {}


def _team_raw(ids, pos_map, enemy_ids):
    ids=[int(h) for h in ids if attrs(h)]
    enemy_ids=[int(e) for e in enemy_ids if e]
    syn=0.0
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            syn+=SYN.get(str(a),{}).get(str(b),0)+SYN.get(str(b),{}).get(str(a),0)
    cnt=sum(CNT.get(str(h),{}).get(str(e),0) for h in ids for e in enemy_ids)
    meta=sum(H[str(h)].get("contest",0) for h in ids if str(h) in H)
    C=coverage(ids)
    phys=sum(attrs(h)["dmg_physical"] for h in ids if attrs(h))
    mag =sum(attrs(h)["dmg_magical"] for h in ids if attrs(h))
    balance=1-abs(phys-mag)/((phys+mag) or 1)
    roles=0.0
    if pos_map:
        for h in ids:
            p=pos_map.get(h, pos_map.get(str(h)))
            if p:
                pr=POS.get(str(h))
                roles += pr["pos"].get(str(int(p)),0) if pr else 0.2
        used={int(p) for p in pos_map.values()}
        roles *= (len(used)/5.0)        # punish duplicate / missing positions
    return {"roles":roles,"synergy":syn,"counter":cnt,"teamfight":C["teamfight"],
            "control":C["lockdown"],"scaling":C["scaling"],"balance":balance,"meta":meta}


def _role_scores(allies, enemies, exclude, pos, extra=None):
    """Score every hero that can play `pos` (forcing `extra` into the pool),
    same components/weights as the engine, role fixed to [pos]."""
    R=residual(allies)
    pool=set(HERO_IDS)-set(exclude)
    if extra is not None: pool.add(int(extra))
    raw={"need":{}, "syn":{}, "cnt":{}, "role":{}, "meta":{}}
    for h in pool:
        if not attrs(h): continue
        rf=rolefit(h,[pos])
        if rf<=0 and h!=extra: continue          # only heroes who actually play this role
        nf,_=needfit(h,R)
        raw["need"][h]=nf
        raw["syn"][h]=sum(SYN.get(str(h),{}).get(str(a),0) for a in allies)+W_COMBO*combo_score(h, allies)
        raw["cnt"][h]=sum(CNT.get(str(h),{}).get(str(e),0) for e in enemies)
        raw["role"][h]=rf
        raw["meta"][h]=meta_contest(h)
    nz={k:_znorm(v) for k,v in raw.items()}
    score={}
    for h in raw["need"]:
        score[h]=(WEIGHTS["need"]*nz["need"].get(h,0)+WEIGHTS["syn"]*nz["syn"].get(h,0)+
                  WEIGHTS["cnt"]*nz["cnt"].get(h,0)+WEIGHTS["role"]*nz["role"].get(h,0)+
                  WEIGHTS["meta"]*nz["meta"].get(h,0))
    return score


def draft_coach(my_team, my_positions, ai_team, bans=None):
    """For each of the player's picks, is there a hero that fits the SAME role
    better against this enemy team? Returns teaching suggestions with reasons."""
    my_team=[int(h) for h in my_team if attrs(h)]
    ai_team=[int(e) for e in ai_team if e]
    bans=set(int(b) for b in (bans or []) if b)
    my_pos={int(k):int(v) for k,v in (my_positions or {}).items()}
    base=set(my_team)|set(ai_team)|bans          # never suggest a banned/taken hero
    out=[]
    for h in my_team:
        p=my_pos.get(h)
        if not p: continue
        allies=[x for x in my_team if x!=h]
        exclude=(base-{h})                       # other picks + enemies stay locked; h is the slot to reconsider
        score=_role_scores(allies, ai_team, exclude, p, extra=h)
        if h not in score: continue
        best=max(score, key=score.get)
        if best==h: continue
        gain=score[best]-score[h]
        if gain<0.25: continue                   # only suggest meaningful upgrades
        reasons=[]
        cvs=sorted(((e,CNT.get(str(best),{}).get(str(e),0)) for e in ai_team), key=lambda x:-x[1])
        if cvs and cvs[0][1]>0.02: reasons.append({"type":"counter","name":NAME.get(cvs[0][0])})
        cmb=sorted(((a,_cpair(best,a)) for a in allies), key=lambda x:-x[1])
        if cmb and cmb[0][1]>=0.6: reasons.append({"type":"combo","name":NAME.get(cmb[0][0])})
        svs=sorted(((a,SYN.get(str(best),{}).get(str(a),0)) for a in allies), key=lambda x:-x[1])
        if svs and svs[0][1]>0.01: reasons.append({"type":"synergy","name":NAME.get(svs[0][0])})
        if H[str(best)].get("contest",0)-H[str(h)].get("contest",0)>0.1: reasons.append({"type":"meta"})
        if rolefit(best,[p])-rolefit(h,[p])>0.15: reasons.append({"type":"role"})
        if not reasons: reasons.append({"type":"overall"})
        out.append({"pos":p, "your":{"id":h,"name":NAME.get(h)},
                    "better":{"id":best,"name":NAME.get(best)},
                    "gain":round(gain,3), "reasons":reasons[:3]})
    out.sort(key=lambda x:-x["gain"])
    return out[:3]


def draft_eval(my_team, my_positions, ai_team, bans=None):
    my_pos={int(k):int(v) for k,v in (my_positions or {}).items()}
    ai_pos=solve_assignment(ai_team)
    mine=_team_raw(my_team, my_pos, ai_team)
    ai  =_team_raw(ai_team, ai_pos, my_team)
    axes=list(EVAL_W.keys())
    sc={"mine":{}, "ai":{}}
    for ax in axes:
        m=mine[ax]; a=ai[ax]
        lo=min(m,a,0.0); hi=max(m,a); span=(hi-lo) or 1.0
        sc["mine"][ax]=round((m-lo)/span*100)
        sc["ai"][ax]  =round((a-lo)/span*100)
    sw=sum(EVAL_W.values())*100 or 1
    mscore=round(sum(EVAL_W[ax]*sc["mine"][ax] for ax in axes)/sw*100)
    ascore=round(sum(EVAL_W[ax]*sc["ai"][ax]   for ax in axes)/sw*100)
    diff=mscore-ascore
    winner="mine" if diff>3 else "ai" if diff<-3 else "tie"
    gaps=sorted(axes, key=lambda ax: (sc["mine"][ax]-sc["ai"][ax]))
    pros=[ax for ax in reversed(gaps) if sc["mine"][ax]-sc["ai"][ax]>=15][:3]
    cons=[ax for ax in gaps          if sc["ai"][ax]-sc["mine"][ax]>=15][:3]
    return {
        "mine":{"score":mscore,"axes":sc["mine"],
                "archetype":classify_archetype([int(x) for x in my_team])["primary"],
                "concept":team_concept(my_team, ai_team),
                "positions":{str(k):v for k,v in my_pos.items()}},
        "ai":{"score":ascore,"axes":sc["ai"],
              "archetype":classify_archetype([int(x) for x in ai_team])["primary"],
              "concept":team_concept(ai_team, my_team),
              "positions":{str(k):v for k,v in ai_pos.items()}},
        "winner":winner, "diff":diff, "pros":pros, "cons":cons,
        "coach":draft_coach(my_team, my_positions, ai_team, bans),
    }
