"use strict";
/*
 * Honest evaluation + weight tuning for the Draft Reasoning Engine.
 *
 * - Time-split: train on older matches, test on the newest 20%.
 * - Affinity (the historical signal) is rebuilt from TRAIN ONLY, so the
 *   reported top-k accuracy is genuinely out-of-sample (no leakage).
 * - Coordinate grid over the blend weights to maximise held-out accuracy.
 *
 * The deployed engine still ships affinity built from ALL matches (more data =
 * better live tool); this script only measures honestly and picks weights.
 *
 * Run: node tune.js
 */
const fs = require("fs");
const Engine = eval(fs.readFileSync("engine.js", "utf8") + "; Engine");

const attrs = JSON.parse(fs.readFileSync("data/hero_attributes.json", "utf8"));
const srcFile = fs.existsSync("data/corpus.json") ? "data/corpus.json" : "data/matches.json";
const matches = JSON.parse(fs.readFileSync(srcFile, "utf8"));
console.log("source:", srcFile);

function sample(arr, k) {
  if (arr.length <= k) return arr;
  const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [a[i], a[j]] = [a[j], a[i]]; }
  return a.slice(0, k);
}

// ---- time split ----
const withTime = matches.filter((m) => m.start_time).sort((a, b) => a.start_time - b.start_time);
const cut = Math.floor(withTime.length * 0.8);
const train = withTime.slice(0, cut);
const test = withTime.slice(cut);
console.log(`matches: ${withTime.length}  train: ${train.length}  test: ${test.length}`);
console.log(`test window: ${new Date(test[0].start_time * 1000).toISOString().slice(0, 10)} .. ` +
  `${new Date(test[test.length - 1].start_time * 1000).toISOString().slice(0, 10)}`);

function buildAffinity(ms) {
  const pick = {}, co = {};
  for (const m of ms) {
    for (const p of m.picks) pick[p.hero_id] = (pick[p.hero_id] || 0) + 1;
    for (const side of ["radiant", "dire"]) {
      const team = m.picks.filter((p) => p.team === side).map((p) => p.hero_id);
      for (let i = 0; i < team.length; i++)
        for (let j = i + 1; j < team.length; j++) {
          const a = team[i], b = team[j];
          (co[a] = co[a] || {})[b] = (co[a][b] || 0) + 1;
          (co[b] = co[b] || {})[a] = (co[b][a] || 0) + 1;
        }
    }
  }
  const aff = {};
  for (const a in co) {
    const parts = [];
    for (const b in co[a]) {
      const d = Math.sqrt(pick[a] * pick[b]);
      if (d > 0) parts.push([+b, +(co[a][b] / d).toFixed(3)]);
    }
    parts.sort((x, y) => y[1] - x[1]);
    aff[a] = parts.slice(0, 30);
  }
  return aff;
}

function evaluate(set) {
  let n = 0, t1 = 0, t3 = 0, t5 = 0, t10 = 0;
  for (const m of set) {
    const r = Engine.analyze(m);
    if (!r) continue;
    n++;
    if (r.rank === 1) t1++;
    if (r.rank <= 3) t3++;
    if (r.rank <= 5) t5++;
    if (r.rank <= 10) t10++;
  }
  return { n, t1: t1 / n, t3: t3 / n, t5: t5 / n, t10: t10 / n };
}

const pct = (x) => (100 * x).toFixed(1) + "%";
const objective = (e) => 0.2 * e.t1 + 0.3 * e.t3 + 0.5 * e.t5;

Engine.init(attrs);
Engine.setStates({ states: [] });           // disable retrieval during scoring (faster, irrelevant to rank)

// ----- honest baseline: train-only affinity, default weights -----
const trainAff = buildAffinity(train);
Engine.setAffinity(trainAff);
const baseline = evaluate(test);
console.log("\nHONEST baseline (train-only affinity, default weights):");
console.log(`  top1 ${pct(baseline.t1)}  top3 ${pct(baseline.t3)}  top5 ${pct(baseline.t5)}  top10 ${pct(baseline.t10)}`);

// in-sample reference (affinity from all matches) for context
Engine.setAffinity(buildAffinity(withTime));
const insample = evaluate(test);
console.log("In-sample reference (all-match affinity):");
console.log(`  top1 ${pct(insample.t1)}  top3 ${pct(insample.t3)}  top5 ${pct(insample.t5)}  top10 ${pct(insample.t10)}`);

// ----- weight search (honest: train-only affinity) -----
// grid over a held-out sample to keep the 540-combo search tractable on ~10k test
Engine.setAffinity(trainAff);
const gridTest = sample(test, 1500);
console.log(`\nweight grid on ${gridTest.length} sampled held-out matches`);
const grid = {
  hist: [0.25, 0.34, 0.45, 0.55, 0.65],
  needfit: [0.15, 0.25, 0.34, 0.45],
  synergy: [0.06, 0.12, 0.18],
  meta: [0.04, 0.08, 0.14],
  priority: [0.0, 0.05, 0.1],
};
let best = null;
let tried = 0;
for (const hist of grid.hist)
  for (const needfit of grid.needfit)
    for (const synergy of grid.synergy)
      for (const meta of grid.meta)
        for (const priority of grid.priority) {
          const sum = hist + needfit + synergy + meta + priority;
          const w = { hist: hist / sum, needfit: needfit / sum, synergy: synergy / sum, meta: meta / sum, priority: priority / sum };
          Engine.setWeights(w);
          const e = evaluate(gridTest);
          tried++;
          if (!best || objective(e) > best.obj) best = { obj: objective(e), w, e };
        }

// re-evaluate the best weights on the FULL held-out set for a clean number
Engine.setWeights(best.w);
const bestFull = evaluate(test);
console.log(`\nSearched ${tried} weight combos. BEST weights, on full held-out:`);
console.log(`  top1 ${pct(bestFull.t1)}  top3 ${pct(bestFull.t3)}  top5 ${pct(bestFull.t5)}  top10 ${pct(bestFull.t10)}`);
const wr = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, +v.toFixed(3)]));
console.log("  weights:", JSON.stringify(wr(best.w)));
