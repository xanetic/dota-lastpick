"use strict";
/*
 * Draft Reasoning Engine — client-side v1 (Phase 1).
 * See docs/DRAFT_REASONING_ENGINE.md.
 *
 * Given a finished pro draft, it reconstructs the state right before the last
 * pick (the answer team's 4 revealed heroes), detects what that draft still
 * needed, ranks candidate last picks WITHOUT winrate as the driver, and
 * explains why the actual pick made sense. The score is additive, so the
 * explanation is a faithful decomposition — not a post-hoc story.
 */
const Engine = (() => {
  let AXES = [];
  let H = {};                 // hero_id -> { name, attrs{}, contest, priority, img, primary_attr }
  let NAME2ID = {};
  let SYN = {};               // "idA|idB" -> { w, why }
  let AFF = {};               // hero_id -> { partner_id: affinity }  (teammate co-occurrence)
  let AXIS_MEAN = {};         // axis -> mean value across heroes (archetype de-bias)
  let STATES = [];            // historical pre-last-pick states for retrieval (doc §5)

  // ranking blend weights. Held-out testing (tune.js) shows exact last-pick
  // prediction is hard (~top5 8–11% / top10 ~20% any blend; a pure popularity
  // baseline is competitive). We deliberately do NOT chase that metric by
  // over-weighting popularity — the product's value is reasoning, so weights
  // favour need-fit / synergy / who-actually-pairs-with-these, keeping the
  // candidate list coherent with the explanation rather than a frequency table.
  let WEIGHTS = { hist: 0.32, needfit: 0.30, synergy: 0.16, meta: 0.16, priority: 0.06 };
  function setWeights(w) { WEIGHTS = Object.assign({}, WEIGHTS, w); }

  // importance of each need axis (0–1), tunable / learnable later
  const W_NEED = {
    frontline: 0.9, initiation: 1.0, teamfight: 1.0, pickoff: 0.8, lockdown: 0.7,
    save_peel: 0.8, tower_pressure: 0.7, defense_waveclear: 0.6, scaling: 0.9,
    early_tempo: 0.8, mobility: 0.5, splitpush: 0.5, dmg_physical: 0.7,
    dmg_magical: 0.7, auras: 0.4, sustain: 0.5, map_control: 0.6, roshan: 0.4,
  };

  // target coverage a "complete" draft wants per axis (0–10 on the aggregate scale)
  const TARGET = {
    frontline: 8, initiation: 8, teamfight: 9, pickoff: 5, lockdown: 7,
    save_peel: 6, tower_pressure: 5, defense_waveclear: 4, scaling: 8,
    early_tempo: 5, mobility: 5, splitpush: 3, dmg_physical: 7, dmg_magical: 7,
    auras: 3, sustain: 4, map_control: 6, roshan: 3,
  };

  // archetype prototypes (only the defining axes; rest 0)
  const ARCHETYPES = {
    "Teamfight":           { teamfight: 10, initiation: 9, frontline: 7, lockdown: 6 },
    "Deathball":           { tower_pressure: 9, early_tempo: 8, teamfight: 7, frontline: 6 },
    "Pickoff":             { pickoff: 10, lockdown: 7, mobility: 7, map_control: 6 },
    "Split Push":          { splitpush: 10, tower_pressure: 7, mobility: 6 },
    "Protect the Carry":   { scaling: 10, save_peel: 9, auras: 6, sustain: 5 },
    "High Ground Defense": { defense_waveclear: 9, teamfight: 7, save_peel: 6 },
    "Tempo":               { early_tempo: 9, mobility: 8, pickoff: 6 },
  };

  // curated synergies (setup → payoff / stacking control). Symmetric.
  const SYN_PAIRS = [
    ["Magnus", "Faceless Void", 3, "RP into Chronosphere — stacked teamfight lockdown"],
    ["Magnus", "Sven", 3, "RP groups enemies for Sven's cleave"],
    ["Magnus", "Phantom Assassin", 2.5, "RP sets up a melee carry's burst"],
    ["Magnus", "Luna", 2.5, "Empower + RP amplify Luna's AoE bounce"],
    ["Enigma", "Faceless Void", 3, "Chronosphere guarantees Black Hole"],
    ["Mars", "Phoenix", 3, "Arena traps targets inside Supernova"],
    ["Mars", "Disruptor", 2.5, "Arena + Static Storm — inescapable AoE"],
    ["Mars", "Sand King", 2.5, "Arena holds for Epicenter/Sandstorm"],
    ["Dark Seer", "Tidehunter", 3, "Vacuum + Wall clump targets for Ravage"],
    ["Dark Seer", "Enigma", 2.5, "Vacuum sets up Black Hole"],
    ["Tidehunter", "Sand King", 2.5, "Ravage + Epicenter overlap control"],
    ["Disruptor", "Faceless Void", 2.5, "Static Storm inside Chronosphere"],
    ["Io", "Spectre", 3, "Tether + Relocate enable Spectre's global presence"],
    ["Io", "Gyrocopter", 2.5, "Tether amplifies and saves the carry"],
    ["Beastmaster", "Drow Ranger", 2.5, "Aura stacking + early tower pressure"],
    ["Drow Ranger", "Visage", 2, "Precision aura on summons"],
    ["Earthshaker", "Tiny", 2.5, "Toss into Echo Slam combos"],
    ["Pudge", "Clockwerk", 2, "Hook + Hookshot double pickoff"],
    ["Kunkka", "Tidehunter", 2, "Torrent/Boat + Ravage chained control"],
    ["Invoker", "Mars", 2, "Cataclysm/Sun Strike payoff inside Arena"],
    ["Warlock", "Enigma", 2.5, "Two channel ults compound in one fight"],
    ["Shadow Fiend", "Magnus", 2.5, "RP enables Requiem of Souls"],
  ];

  // Russian explanations for the synergies above (keyed by the English text)
  const SYN_WHY_RU = {
    "RP into Chronosphere — stacked teamfight lockdown": "RP в Хроносферу — двойной контроль в тимфайте",
    "RP groups enemies for Sven's cleave": "RP собирает врагов под клив Свена",
    "RP sets up a melee carry's burst": "RP подаёт цель под бёрст ближнего кэрри",
    "Empower + RP amplify Luna's AoE bounce": "Empower + RP усиливают AoE-отскоки Луны",
    "Chronosphere guarantees Black Hole": "Хроносфера гарантирует Чёрную дыру",
    "Arena traps targets inside Supernova": "Арена запирает цели в Сверхновой",
    "Arena + Static Storm — inescapable AoE": "Арена + Static Storm — AoE без побега",
    "Arena holds for Epicenter/Sandstorm": "Арена держит цели под Эпицентр/Песчаную бурю",
    "Vacuum + Wall clump targets for Ravage": "Вакуум + Стена собирают цели под Ravage",
    "Vacuum sets up Black Hole": "Вакуум подаёт под Чёрную дыру",
    "Ravage + Epicenter overlap control": "Ravage + Эпицентр накладывают контроль",
    "Static Storm inside Chronosphere": "Static Storm внутри Хроносферы",
    "Tether + Relocate enable Spectre's global presence": "Tether + Relocate дают Спектре глобальное присутствие",
    "Tether amplifies and saves the carry": "Tether усиливает и спасает кэрри",
    "Aura stacking + early tower pressure": "Стак аур + раннее давление на вышки",
    "Precision aura on summons": "Аура точности на призывах",
    "Toss into Echo Slam combos": "Toss в Echo Slam — комбо",
    "Hook + Hookshot double pickoff": "Hook + Hookshot — двойной отлов",
    "Torrent/Boat + Ravage chained control": "Torrent/Boat + Ravage — цепочка контроля",
    "Cataclysm/Sun Strike payoff inside Arena": "Катаклизм/Sun Strike добивают в Арене",
    "Two channel ults compound in one fight": "Два канализируемых ульта складываются в одном бою",
    "RP enables Requiem of Souls": "RP включает Реквием душ",
  };

  const clamp01 = (x) => Math.max(0, Math.min(1, x));

  function init(data) {
    AXES = data.axes;
    H = data.heroes;
    NAME2ID = {};
    for (const id in H) NAME2ID[H[id].name] = +id;
    SYN = {};
    for (const [a, b, w, why] of SYN_PAIRS) {
      const ia = NAME2ID[a], ib = NAME2ID[b];
      if (ia == null || ib == null) continue;
      SYN[key(ia, ib)] = { w, why, whyRu: SYN_WHY_RU[why] || why };
    }
    setAffinity(data.affinity || {});
    // mean of each axis across all heroes — used to de-bias archetype matching
    AXIS_MEAN = {};
    const ids = Object.keys(H);
    for (const ax of AXES) {
      let s = 0;
      for (const id of ids) s += H[id].attrs[ax];
      AXIS_MEAN[ax] = s / (ids.length || 1);
    }
  }

  function setAffinity(raw) {
    AFF = {};
    for (const a in raw) {
      AFF[a] = {};
      for (const [b, s] of raw[a]) AFF[a][b] = s;
    }
  }

  function setStates(data) { STATES = (data && data.states) || []; }

  // historical teammate affinity of candidate with the known team heroes
  function historical(id, teamIds) {
    if (!teamIds.length) return 0;
    let s = 0;
    for (const t of teamIds) {
      const a = (AFF[id] && AFF[id][t]) || (AFF[t] && AFF[t][id]) || 0;
      s += a;
    }
    return s / teamIds.length;
  }

  const key = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`);
  const has = (id) => H[id] != null;
  const attrs = (id) => (H[id] ? H[id].attrs : null);

  // current coverage of an axis for a set of heroes: best provider counts most,
  // extra providers give diminishing help (a1 + 0.5*a2 + 0.25*a3 + ...)
  function coverage(ids) {
    const C = {};
    for (const ax of AXES) {
      const vals = ids.map((id) => (attrs(id) ? attrs(id)[ax] : 0)).sort((a, b) => b - a);
      let c = 0, w = 1;
      for (const v of vals) { c += w * v; w *= 0.5; }
      C[ax] = c;
    }
    return C;
  }

  // residual need vector R = relu(TARGET - C), modulated by the enemy draft
  function residual(ids, enemyIds) {
    const C = coverage(ids);
    const R = {};
    for (const ax of AXES) R[ax] = Math.max(0, TARGET[ax] - C[ax]);

    // enemy modulation: react to what the other team built
    if (enemyIds && enemyIds.length) {
      const E = coverage(enemyIds);
      R.pickoff += clampN((E.mobility - 6) * 0.5, 0, 3);            // mobile enemies -> need catch
      R.defense_waveclear += clampN((E.splitpush + E.tower_pressure * 0.5 - 6) * 0.35, 0, 3); // push -> need wave clear
      R.early_tempo += clampN((E.scaling - 7) * 0.4, 0, 2);         // greedy enemies -> close early
      R.lockdown += clampN((E.mobility - 6) * 0.3, 0, 2);
    }
    return R;
  }
  const clampN = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

  // how well hero h fills the residual need (also returns per-axis fills)
  function needFit(id, R) {
    const a = attrs(id);
    if (!a) return { score: 0, fills: [] };
    let s = 0;
    const fills = [];
    for (const ax of AXES) {
      const fill = Math.min(a[ax], R[ax]) * W_NEED[ax];
      if (fill > 0.01) fills.push({ axis: ax, fill });
      s += fill;
    }
    fills.sort((x, y) => y.fill - x.fill);
    return { score: s, fills };
  }

  function synergy(id, teamIds) {
    let s = 0;
    const partners = [];
    for (const t of teamIds) {
      const rec = SYN[key(id, t)];
      if (rec) { s += rec.w; partners.push({ with: t, why: rec.why, whyRu: rec.whyRu, w: rec.w }); }
    }
    partners.sort((a, b) => b.w - a.w);
    return { score: s, partners };
  }

  // rank all draftable candidates for a team's open slot
  function rank(teamIds, excluded, enemyIds) {
    const R = residual(teamIds, enemyIds);
    const ex = new Set(excluded);
    const rows = [];
    for (const id in H) {
      const hid = +id;
      if (ex.has(hid)) continue;
      const nf = needFit(hid, R);
      const sy = synergy(hid, teamIds);
      rows.push({
        id: hid,
        name: H[id].name,
        needfit: nf.score,
        fills: nf.fills,
        synergy: sy.score,
        partners: sy.partners,
        meta: H[id].contest,
        priority: H[id].priority,
        hist: historical(hid, teamIds),
      });
    }
    // normalize each component across the candidate pool, then weighted blend.
    // historical (who actually pairs with these heroes) and need-fit co-lead.
    norm(rows, "needfit"); norm(rows, "synergy"); norm(rows, "meta");
    norm(rows, "priority"); norm(rows, "hist");
    for (const r of rows) {
      r.score = WEIGHTS.hist * r._hist + WEIGHTS.needfit * r._needfit
              + WEIGHTS.synergy * r._synergy + WEIGHTS.meta * r._meta
              + WEIGHTS.priority * r._priority;
    }
    rows.sort((a, b) => b.score - a.score);
    return { rows, R };
  }

  // similar-draft retrieval (doc §5): historical pre-last-pick states most like
  // this one, and what those teams actually picked next.
  function similarDrafts(knownIds, excludeMid, K) {
    if (!STATES.length) return null;
    K = K || 60;
    // per-axis weighting by inverse mean de-emphasises axes that are high in
    // every draft (teamfight/frontline) so similarity reflects the distinctive
    // shape of the lineup, not its overall magnitude.
    const wax = AXES.map((ax) => 1 / ((AXIS_MEAN[ax] || 1)));
    const q = AXES.map((ax, i) => knownIds.reduce((s, id) => s + (attrs(id) ? attrs(id)[ax] : 0), 0) * wax[i]);
    const qn = Math.sqrt(q.reduce((s, x) => s + x * x, 0)) || 1;
    const scored = [];
    for (const st of STATES) {
      if (st.mid === excludeMid) continue;
      let dot = 0, vn = 0;
      for (let i = 0; i < q.length; i++) {
        const v = st.v[i] * wax[i];
        dot += q[i] * v; vn += v * v;
      }
      scored.push({ sim: dot / (qn * Math.sqrt(vn || 1)), t: st.t });
    }
    scored.sort((a, b) => b.sim - a.sim);
    const top = scored.slice(0, K);
    const tally = {};
    for (const s of top) tally[s.t] = (tally[s.t] || 0) + 1;
    const dist = Object.entries(tally)
      .map(([id, c]) => ({ id: +id, name: H[id] ? H[id].name : `#${id}`, count: c, pct: c / top.length }))
      .sort((a, b) => b.count - a.count);
    return { n: top.length, dist };
  }

  function norm(rows, field) {
    let lo = Infinity, hi = -Infinity;
    for (const r of rows) { lo = Math.min(lo, r[field]); hi = Math.max(hi, r[field]); }
    const span = hi - lo || 1;
    for (const r of rows) r["_" + field] = clamp01((r[field] - lo) / span);
  }

  function classifyArchetype(ids) {
    const C = coverage(ids);
    // relative profile: how much each axis stands out vs the average hero —
    // stops common axes (teamfight/frontline) from dominating every comp.
    const rel = {};
    for (const ax of AXES) rel[ax] = C[ax] / ((AXIS_MEAN[ax] || 1) * 5);
    let best = null, bestScore = -1, second = null;
    for (const name in ARCHETYPES) {
      const proto = ARCHETYPES[name];
      let dot = 0, np = 0, nc = 0;
      for (const ax of AXES) {
        const p = proto[ax] || 0;
        dot += p * rel[ax]; np += p * p; nc += rel[ax] * rel[ax];
      }
      const cos = dot / (Math.sqrt(np) * Math.sqrt(nc) || 1);
      if (cos > bestScore) { second = best; bestScore = cos; best = name; }
    }
    return { primary: best, confidence: Math.round(bestScore * 100) / 100, secondary: second };
  }

  const axisLabel = (ax) => ({
    frontline: "frontline", initiation: "initiation", teamfight: "teamfight",
    pickoff: "pick-off", lockdown: "lockdown / control", save_peel: "save / peel",
    tower_pressure: "tower pressure", defense_waveclear: "wave clear / anti-push",
    scaling: "late-game scaling", early_tempo: "early tempo", mobility: "mobility",
    splitpush: "split push", dmg_physical: "physical damage", dmg_magical: "magical damage",
    auras: "auras", sustain: "sustain", map_control: "map control / vision",
    roshan: "Roshan control",
  }[ax] || ax);

  // main entry: analyze a finished match, explain its last pick
  function analyze(match) {
    const ans = match.answer;
    const ownAll = match.picks.filter((p) => p.team === ans.team).map((p) => p.hero_id);
    const known = ownAll.filter((id) => id !== ans.hero_id);          // the 4 revealed
    if (!has(ans.hero_id) || known.some((id) => !has(id))) return null;

    const allPicked = match.picks.map((p) => p.hero_id);
    const banned = (match.bans || []).map((b) => b.hero_id);
    const excluded = allPicked.filter((id) => id !== ans.hero_id).concat(banned);
    const enemy = match.picks.filter((p) => p.team !== ans.team).map((p) => p.hero_id);

    const { rows, R } = rank(known, excluded, enemy);
    const answerRow = rows.find((r) => r.id === ans.hero_id);
    const answerRank = rows.findIndex((r) => r.id === ans.hero_id) + 1;

    // top needs of the draft (by weighted residual)
    const needs = AXES.map((ax) => ({ axis: ax, label: axisLabel(ax), v: R[ax] * W_NEED[ax] }))
      .filter((n) => n.v > 0.2).sort((a, b) => b.v - a.v).slice(0, 3);

    const arche = classifyArchetype(ownAll);
    const similar = similarDrafts(known, match.match_id, 60);

    // confidence: blends how high the model ranked the real pick with how much
    // similar historical drafts agreed on it.
    const rankPart = answerRank <= 3 ? 1 : answerRank <= 5 ? 0.7 : answerRank <= 10 ? 0.45 : answerRank <= 20 ? 0.25 : 0.1;
    let agreePart = 0;
    if (similar) {
      const hit = similar.dist.find((d) => d.id === ans.hero_id);
      const topHit = similar.dist.slice(0, 4).some((d) => d.id === ans.hero_id);
      agreePart = hit ? Math.min(1, hit.pct * 4) : 0;
      if (topHit) agreePart = Math.max(agreePart, 0.5);
    }
    const confidence = Math.round((0.55 * rankPart + 0.45 * agreePart) * 100) / 100;

    return {
      answer: { id: ans.hero_id, name: H[ans.hero_id].name },
      rank: answerRank,
      total: rows.length,
      needs,
      candidates: rows.slice(0, 5).map((r) => ({ id: r.id, name: r.name, score: r.score })),
      whyChosen: {
        fills: (answerRow ? answerRow.fills : []).slice(0, 3).map((f) => ({
          axis: f.axis, label: axisLabel(f.axis), strength: Math.round(f.fill * 10) / 10,
        })),
        partners: (answerRow ? answerRow.partners : []).slice(0, 2).map((p) => ({
          name: H[p.with].name, why: p.why, whyRu: p.whyRu,
        })),
        meta: answerRow ? answerRow.meta : 0,
      },
      archetype: arche,
      similar: similar ? { n: similar.n, top: similar.dist.slice(0, 4) } : null,
      confidence,
    };
  }

  // expose internals so the offline tuner (tune.js) can swap affinity/weights
  return { init, analyze, setWeights, setAffinity, setStates };
})();
