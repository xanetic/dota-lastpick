"use strict";

// ============================================================ state
let HEROES = {};
let MATCHES = [];
let ENGINE_READY = false;
let MODE = "casual";

const $ = (s) => document.querySelector(s);
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
const T = (k, v) => I18N.t(k, v);
function normalize(s) { return (s || "").toLowerCase().replace(/[^a-z0-9]/gi, ""); }

// ============================================================ data load
async function loadData() {
  const V = "?v=20260629a";
  // reasoning is now server-side (/api/analyze); the client only needs heroes + matches.
  const [hRes, mRes] = await Promise.all([
    fetch("data/heroes.json" + V),
    fetch("data/matches.json" + V),
  ]);
  if (!hRes.ok || !mRes.ok) throw new Error("Could not load heroes.json / matches.json");
  HEROES = await hRes.json();
  MATCHES = await mRes.json();
}

// ============================================================ shared BOARD
// One #board element, moved between mode slots. Renders from a normalized match:
//   { picks:[{team,order,hero_id|null,hidden,player?}], bans:[{team,hero_id}],
//     answerHeroId?, answered, correct, guessHeroId }
const Board = (() => {
  let state = null;   // current normalized match
  let opts = {};      // { showTeamNames, radiantName, direName, showPlayers, onPick }

  function moveTo(slotId) { $("#" + slotId).appendChild($("#board")); }

  function set(match, options) { state = match; opts = options || {}; render(); }
  function setOpts(patch) { Object.assign(opts, patch); render(); }
  function get() { return state; }

  function render() {
    if (!state) return;
    renderNames();
    renderDrafts();
    renderBans();
    renderGrid();
    applySearch($("#search").value || "");
  }

  function renderNames() {
    const rn = $("#radiantName"), dn = $("#direName");
    if (opts.showTeamNames) {
      rn.textContent = opts.radiantName || "Radiant"; dn.textContent = opts.direName || "Dire";
      rn.classList.remove("hidden-name"); dn.classList.remove("hidden-name");
    } else {
      rn.textContent = "???"; dn.textContent = "???";
      rn.classList.add("hidden-name"); dn.classList.add("hidden-name");
    }
  }

  function renderDrafts() {
    for (const side of ["radiant", "dire"]) {
      const box = $(side === "radiant" ? "#radiantPicks" : "#direPicks");
      box.innerHTML = "";
      const picks = state.picks.filter((p) => p.team === side).sort((a, b) => a.order - b.order);
      for (const p of picks) box.appendChild(pickRow(p));
    }
  }

  function pickRow(p) {
    const row = el("div", "pick");
    const revealed = state.answered;
    if (p.hidden && !revealed) {
      row.classList.add("is-answer");
      const q = el("div", "qmark"); q.textContent = "?"; row.appendChild(q);
    } else {
      const hero = HEROES[p.hero_id];
      const img = el("img", "portrait");
      img.src = hero ? hero.img : ""; img.alt = hero ? hero.name : "?"; img.loading = "lazy";
      row.appendChild(img);
      if (p.hidden && revealed) row.classList.add(state.correct ? "revealed-correct" : "revealed-wrong");
    }
    const meta = el("div", "pick-meta");
    const name = el("div", "hero-name");
    const hero = HEROES[p.hero_id];
    name.textContent = (p.hidden && !revealed) ? "—" : (hero ? hero.name : `#${p.hero_id}`);
    meta.appendChild(name);
    const pl = el("div", "player-name");
    pl.textContent = opts.showPlayers ? (p.player || "—") : "";
    meta.appendChild(pl);
    row.appendChild(meta);
    return row;
  }

  function renderBans() {
    for (const side of ["radiant", "dire"]) {
      const box = $(side === "radiant" ? "#radiantBans" : "#direBans");
      box.innerHTML = ""; box.classList.remove("empty-note");
      const bans = (state.bans || []).filter((b) => b.team === side);
      if (!bans.length) { box.classList.add("empty-note"); box.textContent = "—"; continue; }
      for (const b of bans) {
        const hero = HEROES[b.hero_id];
        const cell = el("div", "ban");
        const img = el("img"); img.src = hero ? hero.img : ""; img.alt = hero ? hero.name : "?"; img.loading = "lazy";
        const tip = el("div", "ban-tip"); tip.textContent = hero ? hero.name : `#${b.hero_id}`;
        cell.appendChild(img); cell.appendChild(tip); box.appendChild(cell);
      }
    }
  }

  function lockedIds() {
    const s = new Set();
    for (const p of state.picks) if (!p.hidden && p.hero_id != null) s.add(p.hero_id);
    for (const b of (state.bans || [])) s.add(b.hero_id);
    return s;
  }

  const ATTR_ORDER = [
    { key: "str", label: "Strength" }, { key: "agi", label: "Agility" },
    { key: "int", label: "Intelligence" }, { key: "all", label: "Universal" },
  ];

  function renderGrid() {
    const grid = $("#heroGrid"); grid.innerHTML = "";
    const used = lockedIds();
    const banned = new Set((state.bans || []).map((b) => b.hero_id));
    for (const { key, label } of ATTR_ORDER) {
      const list = Object.values(HEROES).filter((h) => h.attr === key).sort((a, b) => a.name.localeCompare(b.name));
      const row = el("div", `attr-row attr-${key}`);
      const title = el("div", "attr-title");
      const dot = el("span", "attr-dot"); title.appendChild(dot); title.appendChild(document.createTextNode(label));
      row.appendChild(title);
      const wrap = el("div", "heroes");
      for (const h of list) {
        const card = el("div", "hero");
        card.dataset.name = normalize(h.name); card.dataset.id = String(h.id);
        const img = el("img"); img.src = h.img; img.alt = h.name; img.loading = "lazy";
        const cap = el("div", "cap"); cap.textContent = h.name;
        card.appendChild(img); card.appendChild(cap);
        if (banned.has(h.id)) { card.classList.add("banned"); }
        else if (used.has(h.id)) { card.classList.add("used"); }
        else if (!state.answered) { card.addEventListener("click", () => opts.onPick && opts.onPick(h.id, card)); }
        // post-answer highlights
        if (state.answered) {
          if (h.id === state.answerHeroId) card.style.borderColor = "var(--ok)";
          else if (h.id === state.guessHeroId && !state.correct) card.style.borderColor = "var(--bad)";
        }
        wrap.appendChild(card);
      }
      row.appendChild(wrap); grid.appendChild(row);
    }
  }

  function applySearch(q) {
    const nq = normalize(q);
    document.querySelectorAll(".hero").forEach((c) => {
      c.classList.toggle("dim", !(!nq || c.dataset.name.includes(nq)));
    });
    document.querySelectorAll(".attr-row").forEach((row) => {
      const any = [...row.querySelectorAll(".hero")].some((c) => !c.classList.contains("dim"));
      row.classList.toggle("empty", !any);
    });
  }

  function setRevealed(answerHeroId, guessHeroId, correct) {
    state.answered = true; state.answerHeroId = answerHeroId;
    state.guessHeroId = guessHeroId; state.correct = correct;
    // fill the hidden pick's hero so it renders
    const hp = state.picks.find((p) => p.hidden);
    if (hp && hp.hero_id == null) hp.hero_id = answerHeroId;
    render();
  }

  return { moveTo, set, setOpts, get, render, applySearch, setRevealed };
})();

// ============================================================ REASONING (shared, movable like Board)
const Reasoning = (() => {
  let last = null;
  function moveTo(slotId) { $("#" + slotId).appendChild($("#reasoning")); }
  function hide() { $("#reasoning").classList.add("hidden"); }

  function paint(a) {
    last = a;
    const panel = $("#reasoning");
    $("#archeBadge").textContent = T("reason.archeBadge", { a: I18N.archetype(a.archetype.primary) });
    const cv = a.confidence, lvl = cv >= 0.6 ? "high" : cv >= 0.35 ? "mid" : "low";
    const conf = $("#confBadge");
    conf.textContent = T("reason.conf", { lvl: T("reason.conf." + lvl), p: Math.round(cv * 100) });
    conf.className = "conf-badge " + lvl;

    const orEl = $("#openRole");
    if (a.open_positions && a.open_positions.length) {
      orEl.textContent = T("reason.openRole", { role: a.open_positions.map((p) => I18N.role(p.pos)).join(", ") });
      orEl.classList.remove("hidden");
    } else { orEl.textContent = ""; orEl.classList.add("hidden"); }

    const needList = $("#needList"); needList.innerHTML = "";
    if (a.needs && a.needs.length) for (const n of a.needs) { const c = el("span", "chip"); c.textContent = I18N.axisLabel(n.axis); needList.appendChild(c); }
    else needList.textContent = T("reason.wellRounded");

    const candList = $("#candList"); candList.innerHTML = "";
    const tot = a.candidates.reduce((s, c) => s + c.prob, 0) || 1;
    for (const c of a.candidates) {
      const li = el("li"); if (c.id === a.answer.id) li.classList.add("is-answer");
      const hero = HEROES[c.id];
      if (hero) { const img = el("img"); img.src = hero.img; img.alt = c.name; img.loading = "lazy"; li.appendChild(img); }
      const nm = el("span", "cand-name"); nm.textContent = c.name; li.appendChild(nm);
      const share = Math.round((c.prob / tot) * 100);
      const bar = el("span", "cand-bar"); const fill = el("span"); fill.style.width = share + "%"; bar.appendChild(fill); li.appendChild(bar);
      const pct = el("span", "cand-pct"); pct.textContent = share + "%"; li.appendChild(pct);
      candList.appendChild(li);
    }
    $("#rankNote").textContent = T("reason.rankNote2", { hero: a.answer.name, rank: a.answer.rank, total: a.answer.total });

    $("#whyHead").textContent = T("reason.whyHero", { hero: a.answer.name });
    const why = $("#whyBody"); why.innerHTML = ""; const w = a.answer;
    if (a.open_positions && a.open_positions.length && w.fits_open_role > 0.2) {
      const r = el("div", "why-row"); r.innerHTML = `<span class="why-k">${T("reason.roleFit", { role: a.open_positions.map((p) => I18N.role(p.pos)).join(", ") })}</span>`; why.appendChild(r);
    }
    if (w.fills && w.fills.length) { const r = el("div", "why-row"); r.innerHTML = `<span class="why-k">${T("reason.fills")}</span> ` + w.fills.map((f) => `<b>${I18N.axisLabel(f.axis)}</b>`).join(", "); why.appendChild(r); }
    if (w.combos && w.combos.length) { const r = el("div", "why-row combo-row"); r.innerHTML = `<span class="why-k">${T("reason.combos")}</span> ` + w.combos.map((c) => `<b>${c.name}</b> <i>(${I18N.comboType(c.type)})</i>`).join(", "); why.appendChild(r); }
    for (const s of (w.synergies || [])) { const r = el("div", "why-row"); r.innerHTML = `<span class="why-k">${T("reason.synergyWith", { name: s.name })}</span> +${Math.round(s.adv * 100)}% wr`; why.appendChild(r); }
    if (w.counters && w.counters.length) { const r = el("div", "why-row"); r.innerHTML = `<span class="why-k">${T("reason.countersHead")}</span> ` + w.counters.map((c) => `<b>${c.name}</b>`).join(", "); why.appendChild(r); }
    if (w.signature) { const r = el("div", "why-row sig-row"); r.innerHTML = T("reason.signature", { name: w.signature.name || "—", games: w.signature.games, pct: Math.round(w.signature.share * 100) }); why.appendChild(r); }
    if (w.winrate != null) { const r = el("div", "why-row"); r.innerHTML = `<span class="why-k">${T("reason.metaWr", { p: Math.round(w.winrate * 100) })}</span>`; why.appendChild(r); }
    else if (w.meta >= 0.15) { const r = el("div", "why-row"); r.innerHTML = `<span class="why-k">${T("reason.metaShort", { p: Math.round(w.meta * 100) })}</span>`; why.appendChild(r); }
    if (!why.children.length) why.appendChild(document.createTextNode(T("reason.flex")));

    // win-condition checklist for the whole draft
    const conc = $("#conceptBox");
    if (conc) {
      conc.innerHTML = "";
      if (a.concept && a.concept.have) {
        const have = Object.keys(a.concept.have).filter((k) => a.concept.have[k]);
        const miss = a.concept.missing || [];
        if (have.length) { const d = el("div", "concept-line"); d.innerHTML = `<span class="cc-k ok">${T("reason.canDo")}</span> ` + have.map((k) => `<span class="cc-tag ok">${I18N.conceptLabel(k)}</span>`).join(""); conc.appendChild(d); }
        if (miss.length) { const d = el("div", "concept-line"); d.innerHTML = `<span class="cc-k bad">${T("reason.lacks")}</span> ` + miss.map((k) => `<span class="cc-tag bad">${I18N.conceptLabel(k)}</span>`).join(""); conc.appendChild(d); }
      }
    }

    panel.classList.remove("hidden");
  }

  function refresh() { if (last && !$("#reasoning").classList.contains("hidden")) paint(last); }
  return { moveTo, paint, hide, refresh };
})();

// ============================================================ CASUAL
const Casual = (() => {
  let current = null, answered = false;
  let LATEST_PATCH = null;

  function addOption(sel, value, label) { const o = el("option"); o.value = value; o.textContent = label; sel.appendChild(o); }

  function setupFilters() {
    const ps = $("#patchFilter"); const prevP = ps.value; ps.innerHTML = "";
    const info = new Map();
    for (const m of MATCHES) { if (!m.patch) continue; if (!info.has(m.patch)) info.set(m.patch, { count: 0, t: 0 }); const e = info.get(m.patch); e.count++; e.t = Math.max(e.t, m.start_time || 0); }
    const ordered = [...info.entries()].sort((a, b) => b[1].t - a[1].t);
    LATEST_PATCH = ordered.length ? ordered[0][0] : null;
    addOption(ps, "all", `${T("filter.patch")} · all (${MATCHES.length})`);
    if (LATEST_PATCH) addOption(ps, "current", `Current · ${LATEST_PATCH} (${info.get(LATEST_PATCH).count})`);
    for (const [p, e] of ordered) addOption(ps, `patch:${p}`, `${p} (${e.count})`);
    ps.onchange = newGame;

    const ts = $("#tourFilter"); const prevT = ts.value; ts.innerHTML = "";
    addOption(ts, "all", `${T("filter.tour")} · all`);
    const tiCount = MATCHES.filter((m) => m.is_ti).length;
    if (tiCount) addOption(ts, "ti", `All Internationals (${tiCount})`);
    const byLeague = new Map();
    for (const m of MATCHES) { if (!byLeague.has(m.league)) byLeague.set(m.league, { count: 0, year: m.year || 0 }); const e = byLeague.get(m.league); e.count++; e.year = Math.max(e.year, m.year || 0); }
    for (const [name, e] of [...byLeague.entries()].sort((a, b) => b[1].year - a[1].year)) addOption(ts, `league:${name}`, `${name} (${e.count})`);
    ts.onchange = newGame;
    // keep the player's current selection across a relabel / language switch
    if (prevP && [...ps.options].some((o) => o.value === prevP)) ps.value = prevP;
    if (prevT && [...ts.options].some((o) => o.value === prevT)) ts.value = prevT;
  }

  function pool() {
    let res = MATCHES;
    const pv = $("#patchFilter").value;
    if (pv === "current") res = res.filter((m) => m.patch === LATEST_PATCH);
    else if (pv.startsWith("patch:")) res = res.filter((m) => m.patch === pv.slice(6));
    const tv = $("#tourFilter").value;
    if (tv === "ti") res = res.filter((m) => m.is_ti);
    else if (tv.startsWith("league:")) res = res.filter((m) => m.league === tv.slice(7));
    return res;
  }

  function toBoard(m) {
    const ans = m.answer;
    return {
      picks: m.picks.map((p) => ({ team: p.team, order: p.order, hero_id: p.hero_id, player: p.player,
        hidden: p.hero_id === ans.hero_id && p.team === ans.team })),
      bans: m.bans || [], answerHeroId: ans.hero_id, answered: false, correct: null, guessHeroId: null,
    };
  }

  function newGame() {
    Board.moveTo("slot-casual");
    $("#outcome").classList.add("hidden"); Reasoning.hide();
    const p = pool();
    if (!p.length) {
      $("#tournament").textContent = T("noMatches"); $("#seriesMeta").textContent = T("noMatchesHint");
      current = null; return;
    }
    current = p[Math.floor(Math.random() * p.length)]; answered = false;
    $("#tournament").textContent = current.league || "The International";
    $("#seriesMeta").textContent = [current.year, current.patch ? `Patch ${current.patch}` : null].filter(Boolean).join(" · ");
    $("#result").textContent = ""; $("#result").className = "result";
    $("#hint1Btn").disabled = false; $("#hint2Btn").disabled = false;
    Board.set(toBoard(current), {
      showTeamNames: false, radiantName: current.radiant_team, direName: current.dire_team,
      showPlayers: false, onPick: guess,
    });
    $("#search").value = "";  // no autofocus: avoids popping the mobile keyboard / cursor jump
  }

  function guess(heroId) {
    if (answered) return; answered = true;
    const correct = heroId === current.answer.hero_id;
    current._wasCorrect = correct;
    const answerHero = HEROES[current.answer.hero_id], guessHero = HEROES[heroId];
    const res = $("#result");
    if (correct) { res.textContent = T("result.correct", { hero: answerHero.name }); res.className = "result ok"; }
    else { res.textContent = T("result.wrong", { guess: guessHero.name, hero: answerHero.name }); res.className = "result bad"; }
    $("#hint1Btn").disabled = true; $("#hint2Btn").disabled = true;
    // reveal team names + players, lock the grid
    Board.setOpts({ showTeamNames: true, showPlayers: true, onPick: null });
    Board.setRevealed(current.answer.hero_id, heroId, correct);
    showOutcome(); renderReasoning();
  }

  function fmtDuration(sec) { if (sec == null) return ""; const m = Math.floor(sec / 60), s = sec % 60; return `${m}:${String(s).padStart(2, "0")}`; }

  function showOutcome() {
    const out = $("#outcome"); const radWin = current.radiant_win;
    const w = $("#outcomeWinner");
    w.textContent = T("outcome.won", { team: radWin ? current.radiant_team : current.dire_team });
    w.className = "outcome-winner " + (radWin ? "radiant" : "dire");
    const rs = current.radiant_score, ds = current.dire_score;
    $("#outcomeScore").textContent = (rs != null && ds != null && !(rs === 0 && ds === 0)) ? T("outcome.score", { r: rs, d: ds }) : "";
    const dur = fmtDuration(current.duration); $("#outcomeDuration").textContent = dur ? `⏱ ${dur}` : "";
    $("#dotabuffLink").href = `https://www.dotabuff.com/matches/${current.match_id}`;
    out.classList.remove("hidden");
  }

  async function renderReasoning() {
    if (!current) { Reasoning.hide(); return; }
    const ans = current.answer;
    const allyPicks = current.picks.filter((p) => p.team === ans.team && p.hero_id !== ans.hero_id);
    const allies = allyPicks.map((p) => p.hero_id);
    const allyAccounts = allyPicks.map((p) => (p.account_id != null ? p.account_id : null));  // anchor roles to real players
    const enemies = current.picks.filter((p) => p.team !== ans.team).map((p) => p.hero_id);
    const bans = (current.bans || []).map((b) => b.hero_id);
    const ansPick = current.picks.find((p) => p.hero_id === ans.hero_id && p.team === ans.team);
    const picker = ansPick && ansPick.account_id != null ? ansPick.account_id : null;  // account_id -> reliable signature/role
    let a;
    try { a = await API.analyze({ allies, allyAccounts, enemies, bans, answer: ans.hero_id, picker }); }
    catch (e) { Reasoning.hide(); return; }
    if (!a || !a.answer) { Reasoning.hide(); return; }
    Reasoning.moveTo("reason-slot-casual");
    Reasoning.paint(a);
  }

  function hint1() { Board.setOpts({ showTeamNames: true }); $("#hint1Btn").disabled = true; }
  function hint2() { Board.setOpts({ showPlayers: true }); $("#hint2Btn").disabled = true; }

  function enter() { Board.moveTo("slot-casual"); if (!current) newGame(); else Board.render(); }
  function init() { setupFilters(); $("#newGameBtn").onclick = newGame; $("#hint1Btn").onclick = hint1; $("#hint2Btn").onclick = hint2; }
  function relabel() { setupFilters(); }
  function refreshReasoning() { Reasoning.refresh(); }
  return { init, enter, newGame, relabel, refreshReasoning };
})();

// ============================================================ RANKED SOLO
const Ranked = (() => {
  let session = null, idx = 0, total = 5, score = 0, lastResult = null;

  function show(id) { ["rankedGate", "rankedIntro", "rankedPlay", "rankedResult"].forEach((x) => $("#" + x).classList.add("hidden")); $("#" + id).classList.remove("hidden"); }

  // ---- persistence (resume a run after a page refresh) ----
  const RK = "ranked_state";
  function saveR(round) { try { localStorage.setItem(RK, JSON.stringify({ session, idx, score, total, round })); } catch (e) {} }
  function clearR() { try { localStorage.removeItem(RK); } catch (e) {} }
  function loadR() { try { return JSON.parse(localStorage.getItem(RK) || "null"); } catch (e) { return null; } }

  function enter() {
    if (!API.isAuthed()) { show("rankedGate"); return; }
    if (session) { show("rankedPlay"); Board.moveTo("slot-ranked"); Board.render(); return; }
    const s = loadR();
    if (s && s.session && s.round) {                 // resume after refresh
      session = s.session; idx = s.idx; score = s.score; total = s.total;
      show("rankedPlay"); Board.moveTo("slot-ranked"); loadRound(s.round); return;
    }
    show("rankedIntro");
  }

  async function start() {
    clearR();
    try {
      const r = await API.solo.start();
      session = r.session; total = r.round.total; score = 0;
      show("rankedPlay"); Board.moveTo("slot-ranked");
      loadRound(r.round); updateBar(0);
    } catch (e) { alert(e.message); }
  }

  function toBoard(match) {
    return { picks: match.picks.map((p) => ({ ...p })), bans: match.bans, answerHeroId: null, answered: false, correct: null, guessHeroId: null };
  }

  function loadRound(round) {
    idx = round.idx;
    $("#rankedFeedback").textContent = ""; $("#rankedFeedback").className = "feedback";
    $("#rankedReveal").classList.add("hidden"); Reasoning.hide();
    Board.set(toBoard(round.match), { showTeamNames: false, showPlayers: false, onPick: onPick });
    $("#search").value = "";  // no autofocus: avoids popping the mobile keyboard / cursor jump
    updateBar();
    saveR(round);             // persist the active round for refresh-resume
  }

  function fmtDur(sec) { if (sec == null) return ""; const m = Math.floor(sec / 60), s = sec % 60; return `${m}:${String(s).padStart(2, "0")}`; }

  function updateBar() {
    $("#rankedRound").textContent = T("ranked.round", { i: idx, n: total });
    $("#rankedScore").textContent = T("ranked.score", { s: score });
    $("#rankedProgress").style.width = Math.round(((idx - 1) / total) * 100) + "%";
  }

  async function onPick(heroId) {
    if (Board.get().answered) return;
    let r;
    try { r = await API.solo.guess(session, heroId); }
    catch (e) { clearR(); alert(e.message); show("rankedIntro"); return; }   // stale session after server restart
    score = r.round_score;
    // server already advanced; persist next round (or drop if finished) so a
    // refresh on the reveal screen stays in sync
    if (r.finished) clearR(); else saveR(r.next);
    Board.setRevealed(r.reveal.hero_id, heroId, r.correct);
    renderReveal(r);
  }

  function renderReveal(r) {
    const rev = r.reveal;
    const fb = $("#rankedFeedback");
    const pts = r.points != null ? r.points : (r.correct ? 60 : -10);
    if (r.correct) { fb.textContent = T("ranked.correct", { hero: rev.hero_name, pts: pts }); fb.className = "feedback ok"; }
    else { fb.textContent = T("ranked.wrong", { hero: rev.hero_name, pts: pts }); fb.className = "feedback bad"; }
    $("#rankedScore").textContent = T("ranked.score", { s: score });
    $("#rankedProgress").style.width = Math.round((idx / total) * 100) + "%";

    const rv = $("#rrVerdict");
    rv.textContent = r.correct ? T("ranked.verdictRight", { hero: rev.hero_name }) : T("ranked.verdictWrong", { hero: rev.hero_name });
    rv.className = "rr-verdict " + (r.correct ? "ok" : "bad");

    $("#rrTournament").textContent = rev.league || "—";
    $("#rrSeries").textContent = [rev.year, rev.patch ? "Patch " + rev.patch : null].filter(Boolean).join(" · ");

    const radWin = rev.radiant_win;
    const w = $("#rrWinner");
    w.textContent = T("outcome.won", { team: radWin ? rev.radiant_team : rev.dire_team });
    w.className = "outcome-winner " + (radWin ? "radiant" : "dire");
    const rs = rev.radiant_score, ds = rev.dire_score;
    $("#rrScore").textContent = (rs != null && ds != null && !(rs === 0 && ds === 0)) ? T("outcome.score", { r: rs, d: ds }) : "";
    const dur = fmtDur(rev.duration); $("#rrDuration").textContent = dur ? `⏱ ${dur}` : "";
    $("#rrDotabuff").href = `https://www.dotabuff.com/matches/${rev.match_id}`;

    if (r.analysis && r.analysis.answer) { Reasoning.moveTo("reason-slot-ranked"); Reasoning.paint(r.analysis); }
    else Reasoning.hide();

    const cont = $("#rrContinue");
    cont.textContent = r.finished ? T("ranked.finishView") : T("ranked.next");
    cont.onclick = () => { if (r.finished) finish(r); else loadRound(r.next); };

    if (r.finished) lastResult = r;
    $("#rankedReveal").classList.remove("hidden");
  }

  function finish(r) {
    session = null; clearR();
    show("rankedResult");
    const u = r.user;
    $("#rankedMedal").innerHTML = medalChip(u.medal, true);
    $("#rsScore").textContent = r.total_score;
    $("#rsRating").textContent = u.rating;
    $("#rsCorrect").textContent = `${r.correct_count} / ${total}`;
    const d = $("#rsDelta"); const delta = r.delta;
    d.textContent = T("ranked.delta", { d: (delta >= 0 ? "+" : "") + delta });
    d.className = "rs-delta " + (delta >= 0 ? "ok" : "bad");
    Auth.refreshWidget(u);
  }

  function init() {
    $("#rankedStartBtn").onclick = start;
    $("#rankedAgainBtn").onclick = start;
  }
  return { init, enter, start };
})();

// ============================================================ MULTIPLAYER
const MP = (() => {
  let ws = null, code = null, isHost = false, total = 5, idx = 0, score = 0, finished = false;
  let pendingRound = null, revealOpen = false;  // buffer next round while the breakdown is shown
  let mpMode = "guess";                          // chosen at create; lobby reports it for joiners
  let dHostId = null, dMyPicks = [], mpPos = {}; // draft-duel state

  function show(id) { ["mpGate", "mpSetup", "mpLobby", "mpPlay", "mpDraft", "mpResult"].forEach((x) => $("#" + x).classList.add("hidden")); $("#" + id).classList.remove("hidden"); }
  function fmtDur(sec) { if (sec == null) return ""; const m = Math.floor(sec / 60), s = sec % 60; return `${m}:${String(s).padStart(2, "0")}`; }

  function enter() {
    if (!API.isAuthed()) { show("mpGate"); return; }
    if (ws && code) { /* stay */ } else show("mpSetup");
  }

  async function create() {
    try { const r = await API.mpCreate(mpMode); isHost = true; connect(r.code); }
    catch (e) { setErr(e.message); }
  }
  function join() {
    const c = ($("#mpCodeInput").value || "").trim().toUpperCase();
    if (c.length !== 5) { setErr(T("mp.codePh")); return; }
    isHost = false; connect(c);
  }
  function setErr(m) { const e = $("#mpSetupErr"); e.textContent = m; e.className = "feedback bad"; }

  function connect(c) {
    code = c; finished = false;
    ws = new WebSocket(API.wsUrl(c));
    ws.onmessage = onMsg;
    ws.onclose = () => { /* handled by peer_left / leave */ };
    ws.onerror = () => setErr("connection error");
  }

  function leave() {
    if (ws) { try { ws.close(); } catch (e) {} ws = null; }
    code = null; show("mpSetup"); enter();
  }

  function onMsg(ev) {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === "error") { setErr(m.error); if (ws) { ws.close(); ws = null; } return; }
    if (m.type === "lobby") {
      if (m.started) return; // match already running — never bounce back to the lobby view
      show("mpLobby");
      $("#mpCodeShow").textContent = code;
      const box = $("#mpPlayers"); box.innerHTML = "";
      for (const p of m.players) {
        const chip = el("div", "lobby-player");
        chip.textContent = p.name + (p.is_host ? ` (${T("mp.host")})` : "");
        box.appendChild(chip);
      }
      const startBtn = $("#mpStartBtn");
      startBtn.classList.toggle("hidden", !isHost);
      startBtn.disabled = m.players.length < 2;
      $("#mpLobbyMsg").textContent = m.players.length < 2 ? T("mp.waiting") : "";
    }
    else if (m.type === "begin") { total = m.total; score = 0; idx = 0; finished = false; pendingRound = null; revealOpen = false; Board.moveTo("slot-mp"); show("mpPlay"); }
    else if (m.type === "round") { if (revealOpen) pendingRound = m; else loadRound(m); }  // buffer next round until "continue"
    else if (m.type === "reveal") { renderReveal(m); }
    else if (m.type === "progress") {
      $("#mpProgress").style.width = Math.round((m.you.idx / total) * 100) + "%";
      const opp = m.opponents && m.opponents[0];
      $("#mpOppBar").textContent = opp ? (opp.done ? T("mp.oppDone", { name: opp.name }) : T("mp.oppRound", { name: opp.name, i: Math.min(opp.idx + 1, total) })) : "";
    }
    else if (m.type === "result") { result(m); }
    else if (m.type === "draft_begin") { dHostId = m.host_id; dMyPicks = []; $("#mpDraftPos").classList.add("hidden"); $("#mpDraftResult").classList.add("hidden"); Board.moveTo("slot-mp-draft"); show("mpDraft"); }
    else if (m.type === "draft_state") { renderDraft(m); }
    else if (m.type === "draft_positions") { showDraftPositions(); }
    else if (m.type === "draft_result") { renderDraftResult(m); }
    else if (m.type === "peer_left") { $("#mpLobbyMsg").textContent = T("mp.peerLeft"); }
  }

  // ---------- draft duel ----------
  function onDraftPick(heroId) { if (ws) ws.send(JSON.stringify({ type: "draft_act", hero_id: heroId })); }

  function renderDraft(m) {
    const myside = isHost ? "radiant" : "dire";
    dMyPicks = m.picks.filter((p) => p.team === myside).map((p) => p.hero_id);
    const myTurn = m.turn_uid != null && ((m.turn_uid === m.host_id) === isHost);
    Board.set({ picks: m.picks.map((p) => ({ ...p })), bans: m.bans.map((b) => ({ ...b })), answered: false, answerHeroId: null, correct: null, guessHeroId: null },
      { showTeamNames: true, radiantName: isHost ? T("vsai.you") : T("mp.opp"), direName: isHost ? T("mp.opp") : T("vsai.you"),
        showPlayers: false, onPick: myTurn ? onDraftPick : null });
    const turn = $("#mpDraftTurn");
    if (m.step >= m.total) { turn.textContent = T("vsai.draftDone"); turn.className = "run-round"; }
    else if (myTurn) { turn.textContent = m.act === "pick" ? T("mp.yourPick") : T("mp.yourBan"); turn.className = "run-round " + (m.act === "ban" ? "is-ban" : "is-pick"); }
    else { turn.textContent = m.act === "pick" ? T("mp.oppPick") : T("mp.oppBan"); turn.className = "run-round"; }
  }

  function showDraftPositions() {
    $("#mpDraftPos").classList.remove("hidden"); $("#mpDraftPosBtn").disabled = false; $("#mpDraftPosWait").textContent = "";
    const my = dMyPicks.slice(); mpPos = {}; my.forEach((h, i) => { mpPos[h] = i + 1; });
    renderMpPosList(my);
  }
  function renderMpPosList(my) {
    const box = $("#mpDraftPosList"); box.innerHTML = "";
    my.forEach((hid) => {
      const hero = HEROES[hid]; const row = el("div", "pos-row");
      const img = el("img", "pos-portrait"); img.src = hero ? hero.img : ""; img.alt = "";
      const nm = el("span", "pos-hero"); nm.textContent = hero ? hero.name : ("#" + hid);
      const sel = el("select", "pos-select");
      for (let p = 1; p <= 5; p++) { const o = el("option"); o.value = String(p); o.textContent = I18N.role(p); if (mpPos[hid] === p) o.selected = true; sel.appendChild(o); }
      sel.addEventListener("change", () => setMpPos(hid, parseInt(sel.value, 10), my));
      row.appendChild(img); row.appendChild(nm); row.appendChild(sel); box.appendChild(row);
    });
  }
  function setMpPos(hid, pos, my) {
    const prev = mpPos[hid]; const other = Object.keys(mpPos).find((k) => mpPos[k] === pos && Number(k) !== hid);
    if (other !== undefined) mpPos[other] = prev;
    mpPos[hid] = pos; renderMpPosList(my);
  }
  function submitDraftPos() {
    if (!ws) return;
    const pos = {}; dMyPicks.forEach((h) => { pos[h] = mpPos[h] || 0; });
    ws.send(JSON.stringify({ type: "draft_pos", positions: pos }));
    $("#mpDraftPosBtn").disabled = true; $("#mpDraftPosWait").textContent = T("mp.posWait");
  }

  function renderDraftResult(m) {
    $("#mpDraftPos").classList.add("hidden"); $("#mpDraftResult").classList.remove("hidden");
    const mine = isHost ? m.host : m.guest, opp = isHost ? m.guest : m.host;
    const draw = m.winner == null, iWon = !draw && m.winner === mine.id;
    const v = $("#mpDraftVerdict"); v.className = "verdict " + (draw ? "tie" : iWon ? "win" : "lose");
    v.innerHTML = `<div class="verdict-title">${draw ? T("mp.draftDraw") : iWon ? T("mp.draftWin") : T("mp.draftLose")}</div>
      <div class="verdict-score">${T("vsai.scoreLine", { me: mine.eval.mine.score, ai: opp.eval.mine.score })}</div>
      <div class="verdict-arche"><span class="arche mine">${I18N.archetype(mine.eval.mine.archetype)}</span><span class="arche-vs">vs</span><span class="arche ai">${I18N.archetype(opp.eval.mine.archetype)}</span></div>`;
    const cmp = $("#mpDraftCompare"); cmp.innerHTML = "";
    const A = mine.eval.mine.axes, B = opp.eval.mine.axes;
    for (const ax of Object.keys(A)) {
      const mv = A[ax], av = B[ax]; const row = el("div", "cmp-row");
      row.innerHTML = `<span class="cmp-half mine"><b class="cmp-val">${mv}</b><span class="track"><i style="width:${mv}%"></i></span></span>` +
        `<span class="cmp-axis">${I18N.evalAxis(ax)}</span>` +
        `<span class="cmp-half ai"><span class="track"><i style="width:${av}%"></i></span><b class="cmp-val">${av}</b></span>`;
      cmp.appendChild(row);
    }
    renderMpCoach(mine.coach || []);
  }
  function mpReason(rs) {
    if (rs.type === "counter") return T("coach.counter", { name: rs.name });
    if (rs.type === "combo") return T("coach.combo", { name: rs.name });
    if (rs.type === "synergy") return T("coach.synergy", { name: rs.name });
    if (rs.type === "meta") return T("coach.meta");
    if (rs.type === "role") return T("coach.role");
    return T("coach.overall");
  }
  function renderMpCoach(coach) {
    const box = $("#mpDraftCoach"); box.innerHTML = "";
    const head = el("div", "coach-head"); head.textContent = T("vsai.coachTitle"); box.appendChild(head);
    if (!coach.length) { const p = el("div", "coach-none"); p.textContent = T("vsai.coachNone"); box.appendChild(p); return; }
    for (const c of coach) {
      const row = el("div", "coach-row"); const yourH = HEROES[c.your.id], betterH = HEROES[c.better.id];
      row.innerHTML = `<span class="coach-role">${I18N.role(c.pos)}</span>` +
        `<span class="coach-swap"><img class="coach-hero bad" src="${yourH ? yourH.img : ""}" title="${c.your.name}"><span class="coach-arrow">→</span><img class="coach-hero good" src="${betterH ? betterH.img : ""}" title="${c.better.name}"><b class="coach-better">${c.better.name}</b></span>` +
        `<span class="coach-why">${c.reasons.map(mpReason).join(", ")}</span>`;
      box.appendChild(row);
    }
  }

  let lastGuess = null;
  function loadRound(m) {
    idx = m.idx;
    revealOpen = false; pendingRound = null;
    $("#mpReveal").classList.add("hidden"); Reasoning.hide();
    $("#mpFeedback").textContent = ""; $("#mpFeedback").className = "feedback";
    $("#mpRound").textContent = T("ranked.round", { i: idx, n: total });
    $("#mpScore").textContent = T("ranked.score", { s: score });
    Board.set({ picks: m.match.picks.map((p) => ({ ...p })), bans: m.match.bans, answerHeroId: null, answered: false, correct: null, guessHeroId: null },
      { showTeamNames: false, showPlayers: false, onPick: onPick });
    $("#search").value = "";  // no autofocus: avoids popping the mobile keyboard / cursor jump
  }

  function renderReveal(m) {
    score = m.round_score;
    revealOpen = true;
    Board.setRevealed(m.reveal.hero_id, lastGuess, m.correct);
    const rev = m.reveal;
    const fb = $("#mpFeedback");
    fb.textContent = m.correct ? T("ranked.correct", { hero: rev.hero_name, pts: 60 }) : T("ranked.wrong", { hero: rev.hero_name, pts: -10 });
    fb.className = "feedback " + (m.correct ? "ok" : "bad");
    $("#mpScore").textContent = T("ranked.score", { s: score });

    const rv = $("#mpRvVerdict");
    rv.textContent = m.correct ? T("ranked.verdictRight", { hero: rev.hero_name }) : T("ranked.verdictWrong", { hero: rev.hero_name });
    rv.className = "rr-verdict " + (m.correct ? "ok" : "bad");

    $("#mpRvTournament").textContent = rev.league || "—";
    $("#mpRvSeries").textContent = [rev.year, rev.patch ? "Patch " + rev.patch : null].filter(Boolean).join(" · ");

    const radWin = rev.radiant_win;
    const w = $("#mpRvWinner");
    w.textContent = T("outcome.won", { team: radWin ? rev.radiant_team : rev.dire_team });
    w.className = "outcome-winner " + (radWin ? "radiant" : "dire");
    const rs = rev.radiant_score, ds = rev.dire_score;
    $("#mpRvScore").textContent = (rs != null && ds != null && !(rs === 0 && ds === 0)) ? T("outcome.score", { r: rs, d: ds }) : "";
    const dur = fmtDur(rev.duration); $("#mpRvDuration").textContent = dur ? `⏱ ${dur}` : "";
    $("#mpRvDotabuff").href = `https://www.dotabuff.com/matches/${rev.match_id}`;

    if (m.analysis && m.analysis.answer) { Reasoning.moveTo("reason-slot-mp"); Reasoning.paint(m.analysis); }
    else Reasoning.hide();

    const cont = $("#mpRvContinue"); const wait = $("#mpRvWait");
    if (m.idx < total) {            // more rounds for me — show continue
      cont.textContent = T("ranked.next"); cont.classList.remove("hidden");
      cont.onclick = () => { if (pendingRound) loadRound(pendingRound); };
      wait.textContent = "";
    } else {                        // my last round — wait for the result/opponent
      cont.classList.add("hidden");
      wait.textContent = T("mp.waitResult");
    }
    $("#mpReveal").classList.remove("hidden");
  }

  function onPick(heroId) {
    if (!ws || Board.get().answered) return;
    lastGuess = heroId;
    ws.send(JSON.stringify({ type: "guess", hero_id: heroId }));
  }

  function start() { if (ws && isHost) ws.send(JSON.stringify({ type: "start" })); }

  function result(m) {
    finished = true; show("mpResult");
    const me = API.getUser();
    const mine = m.players.find((p) => p.name === (me && me.username)) || m.players[0];
    const title = $("#mpResultTitle");
    if (m.draw) { title.textContent = T("mp.draw"); title.className = ""; }
    else if (mine.winner) { title.textContent = T("mp.youWon"); title.className = "win"; }
    else { title.textContent = T("mp.youLost"); title.className = "lose"; }
    const body = $("#mpResultBody"); body.innerHTML = "";
    for (const p of m.players) {
      const row = el("div", "mp-res-row" + (p.winner ? " winner" : ""));
      row.innerHTML = `<span class="mp-res-name">${p.name}</span>` +
        `<span class="mp-res-score">${p.score} (${p.correct}/${total})</span>` +
        `<span class="mp-res-delta ${p.delta >= 0 ? "ok" : "bad"}">${p.delta >= 0 ? "+" : ""}${p.delta}</span>` +
        `<span class="mp-res-medal">${medalChip(p.medal, false)}</span>`;
      body.appendChild(row);
    }
    if (mine) Auth.refreshWidget(Object.assign({}, me, { rating: mine.rating, medal: mine.medal }));
    if (ws) { try { ws.close(); } catch (e) {} ws = null; }
  }

  function backToSetup() { if (ws) { try { ws.close(); } catch (e) {} ws = null; } code = null; show("mpSetup"); }

  function init() {
    document.querySelectorAll("#mpModeRow .diff-btn").forEach((b) => {
      b.onclick = () => { mpMode = b.dataset.mpmode; document.querySelectorAll("#mpModeRow .diff-btn").forEach((x) => x.classList.toggle("active", x === b)); };
    });
    $("#mpCreateBtn").onclick = create;
    $("#mpJoinBtn").onclick = join;
    $("#mpStartBtn").onclick = start;
    $("#mpLeaveBtn").onclick = leave;
    $("#mpDraftPosBtn").onclick = submitDraftPos;
    $("#mpDraftAgain").onclick = backToSetup;
    $("#mpRematchBtn").onclick = () => { code = null; show("mpSetup"); };
  }
  return { init, enter };
})();

// ============================================================ LEADERBOARD
const Leaderboard = (() => {
  let board = "ranked";

  async function render() {
    const head = $("#lbHead"), body = $("#lbBody"); body.innerHTML = "";
    const meName = API.getUser() && API.getUser().username;
    try {
      if (board === "ranked") {
        head.innerHTML = `<tr><th>${T("lb.rank")}</th><th>${T("lb.player")}</th><th>${T("lb.medal")}</th><th>${T("lb.rating")}</th><th>${T("lb.games")}</th><th>${T("lb.wins")}</th></tr>`;
        const r = await API.leaderboard();
        $("#lbEmpty").classList.toggle("hidden", r.top.length > 0);
        for (const row of r.top) {
          const tr = el("tr"); if (row.username === meName) tr.className = "me";
          tr.innerHTML = `<td>${row.rank}</td><td>${row.username}</td><td>${medalChip(row.medal, false)}</td>` +
            `<td class="num">${row.rating}</td><td class="num">${row.games}</td><td class="num">${row.wins}</td>`;
          body.appendChild(tr);
        }
      } else {
        head.innerHTML = `<tr><th>${T("lb.rank")}</th><th>${T("lb.player")}</th><th>${T("lb.correct")}</th><th>${T("lb.played")}</th><th>${T("lb.winrate")}</th></tr>`;
        const r = await API.leaderboardBuilds();
        $("#lbEmpty").classList.toggle("hidden", r.top.length > 0);
        for (const row of r.top) {
          const tr = el("tr"); if (row.username === meName) tr.className = "me";
          tr.innerHTML = `<td>${row.rank}</td><td>${row.username}</td><td class="num">${row.correct}</td>` +
            `<td class="num">${row.played}</td><td class="num">${Math.round(row.winrate * 100)}%</td>`;
          body.appendChild(tr);
        }
      }
    } catch (e) { console.warn(e); }
  }
  function enter() { render(); }
  function init() {
    document.querySelectorAll("#lbTabs .diff-btn").forEach((b) => {
      b.onclick = () => { board = b.dataset.lb; document.querySelectorAll("#lbTabs .diff-btn").forEach((x) => x.classList.toggle("active", x === b)); render(); };
    });
  }
  return { init, enter };
})();

// ============================================================ medal chip
function medalTierClass(tier) { return "m-" + tier.toLowerCase(); }
const MEDAL_ICON = { Herald: 1, Guardian: 2, Crusader: 3, Archon: 4, Legend: 5, Ancient: 6, Divine: 7, Immortal: 8 };
function medalChip(m, big) {
  if (!m) return "";
  const n = MEDAL_ICON[m.tier] || 0;
  const star = (m.tier !== "Immortal" && m.star) ? `<img class="medal-star" src="medals/rank_star_${m.star}.png" alt="">` : "";
  const icon = n ? `<span class="medal-icon"><img src="medals/rank_icon_${n}.png" alt="">${star}</span>` : "";
  return `<span class="medal-chip ${medalTierClass(m.tier)} ${big ? "big" : ""}">${icon}<span class="medal-lbl">${I18N.medalLabel(m)}</span></span>`;
}

// ============================================================ AUTH UI
const Auth = (() => {
  let tab = "login";

  function widget() {
    const w = $("#authWidget"); w.innerHTML = "";
    const u = API.getUser();
    if (u) {
      const chip = el("div", "user-chip");
      chip.innerHTML = `<span class="uc-name">${u.username}</span>${medalChip(u.medal, false)}<span class="uc-rating">${u.rating}</span>`;
      const out = el("button", "btn btn-sm"); out.textContent = T("auth.logout");
      out.onclick = async () => { await API.logout(); widget(); switchMode(MODE); };
      w.appendChild(chip); w.appendChild(out);
    } else {
      const b = el("button", "btn"); b.textContent = T("auth.login"); b.onclick = openAuth; w.appendChild(b);
    }
  }
  function refreshWidget(u) { if (u) { const cur = API.getUser(); if (cur) { cur.rating = u.rating; cur.medal = u.medal; } } widget(); }

  function open() { tab = "login"; setTab(); $("#authErr").textContent = ""; $("#authUser").value = ""; $("#authPass").value = ""; $("#authModal").classList.remove("hidden"); $("#authUser").focus(); }
  function close() { $("#authModal").classList.add("hidden"); }
  function setTab() {
    $("#authTabLogin").classList.toggle("active", tab === "login");
    $("#authTabReg").classList.toggle("active", tab === "register");
    $("#authSubmit").textContent = tab === "login" ? T("auth.signin") : T("auth.create");
  }
  async function submit() {
    const u = $("#authUser").value.trim(), p = $("#authPass").value;
    const err = $("#authErr"); err.textContent = "";
    try {
      if (tab === "login") await API.login(u, p); else await API.register(u, p);
      close(); widget(); switchMode(MODE);
    } catch (e) { err.textContent = e.message; err.className = "feedback bad"; }
  }
  function init() {
    $("#authTabLogin").onclick = () => { tab = "login"; setTab(); };
    $("#authTabReg").onclick = () => { tab = "register"; setTab(); };
    $("#authSubmit").onclick = submit;
    $("#authPass").addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    $("#authModal").addEventListener("click", (e) => { if (e.target.id === "authModal") close(); });
    widget();
  }
  return { init, widget, refreshWidget, open, close };
})();
function openAuth() { Auth.open(); }
function closeAuth() { Auth.close(); }

// ============================================================ GUESS THE BUILD
const Builds = (() => {
  const V = "?v=20260629a";
  const CDN = "https://cdn.cloudflare.steamstatic.com";
  let ITEMS = null, current = null, answered = false, busy = false;
  let sPlayed = 0, sCorrect = 0;        // this-session counter
  let acct = null;                       // {played, correct, winrate} from server (if logged in)

  async function ensureItems() {
    if (ITEMS) return true;
    try { const i = await fetch("data/items.json" + V); if (!i.ok) return false; ITEMS = await i.json(); return true; }
    catch (e) { return false; }
  }

  async function enter() {
    Board.moveTo("slot-builds");
    if (!await ensureItems()) { $("#buildFeedback").textContent = T("builds.loadErr"); return; }
    const u = API.getUser();
    if (u) acct = { played: u.builds_played || 0, correct: u.builds_correct || 0, winrate: u.builds_wr || 0 };
    renderStats();
    if (!current) newRound(); else { renderItems(); Board.render(); }
  }

  async function newRound() {
    answered = false; busy = false;
    $("#buildReveal").classList.add("hidden");
    $("#buildFeedback").textContent = T("builds.loading"); $("#buildFeedback").className = "result";
    try { current = await API.builds.next(); }
    catch (e) { $("#buildFeedback").textContent = T("builds.loadErr"); return; }
    $("#buildFeedback").textContent = "";
    renderItems();
    Board.set({ picks: [], bans: [], answered: false, answerHeroId: null, correct: null, guessHeroId: null },
      { showTeamNames: false, onPick: guess });
    $("#search").value = "";
  }

  function itemImg(id) { const it = ITEMS[String(id)]; return it ? (CDN + it.img) : null; }

  function renderItems() {
    const box = $("#buildItems"); box.innerHTML = "";
    const cell = (id, cls) => {
      const c = el("div", "build-item" + (cls ? " " + cls : ""));
      const it = id && ITEMS[String(id)];
      if (it) { const img = el("img"); img.src = itemImg(id); img.alt = it.name; img.title = it.name; img.loading = "lazy"; c.appendChild(img); }
      else c.classList.add("empty");
      return c;
    };
    for (const id of (current.items || [])) box.appendChild(cell(id));
    if (current.neutral && ITEMS[String(current.neutral)]) box.appendChild(cell(current.neutral, "neutral"));
  }

  function renderStats() {
    const box = $("#buildStats"); if (!box) return;
    let html = `<span class="bs-session">${T("builds.session", { c: sCorrect, n: sPlayed })}</span>`;
    if (acct) html += `<span class="bs-acct">${T("builds.account", { c: acct.correct, n: acct.played, wr: Math.round((acct.winrate || 0) * 100) })}</span>`;
    box.innerHTML = html;
  }

  async function guess(heroId) {
    if (answered || busy || !current) return;
    busy = true;
    let r;
    try { r = await API.builds.guess({ id: current.id, hero_id: heroId }); }
    catch (e) { busy = false; return; }
    answered = true;
    const b = r.answer;
    sPlayed++; if (r.correct) sCorrect++;
    if (r.stats) acct = { played: r.stats.played, correct: r.stats.correct, winrate: r.stats.winrate };
    renderStats();
    Board.setRevealed(b.hero_id, heroId, r.correct);
    const hero = HEROES[b.hero_id], guessH = HEROES[heroId];
    const fb = $("#buildFeedback");
    if (r.correct) { fb.textContent = T("result.correct", { hero: hero ? hero.name : b.hero_name }); fb.className = "result ok"; }
    else { fb.textContent = T("result.wrong", { guess: guessH ? guessH.name : "?", hero: hero ? hero.name : b.hero_name }); fb.className = "result bad"; }
    renderReveal(b, r.correct);
  }

  function renderReveal(b, correct) {
    const hero = HEROES[b.hero_id];
    const rv = $("#bRvVerdict");
    rv.textContent = correct ? T("ranked.verdictRight", { hero: b.hero_name }) : T("ranked.verdictWrong", { hero: b.hero_name });
    rv.className = "rr-verdict " + (correct ? "ok" : "bad");
    $("#bRvHero").innerHTML = `<img src="${hero ? hero.img : ""}" alt=""><span>${b.hero_name}</span>`;
    $("#bRvWho").textContent = b.player ? T("builds.who", { player: b.player, res: b.win ? T("builds.won") : T("builds.lost") }) : "";
    $("#bRvTournament").textContent = b.league || "—";
    $("#bRvSeries").textContent = [b.year, b.patch ? "Patch " + b.patch : null].filter(Boolean).join(" · ");
    $("#bRvDotabuff").href = `https://www.dotabuff.com/matches/${b.match_id}`;
    $("#buildReveal").classList.remove("hidden");
  }

  function init() { $("#buildNewBtn").onclick = newRound; $("#bRvContinue").onclick = newRound; }
  return { init, enter };
})();

// ============================================================ VS AI DRAFT
const VsAI = (() => {
  const MY = "radiant", AI = "dire";
  // Current Dota 2 Captains Mode order (7 bans + 5 picks per team). T1 = you, T2 = AI.
  const B = (who) => ({ who, act: "ban" }), P = (who) => ({ who, act: "pick" });
  const CM = [
    B("my"), B("ai"), B("my"), B("ai"),                       // ban phase 1
    P("my"), P("ai"), P("ai"), P("my"),                       // pick phase 1
    B("my"), B("ai"), B("my"), B("ai"), B("my"), B("ai"),     // ban phase 2
    P("my"), P("ai"), P("ai"), P("my"),                       // pick phase 2
    B("my"), B("ai"), B("my"), B("ai"),                       // ban phase 3
    P("my"), P("ai"),                                         // last picks
  ];
  let diff = "medium";
  let picks = [];     // {team, order, hero_id}
  let bans = [];      // {team, hero_id}
  let step = 0;
  let myPos = {};     // hero_id -> position 1..5
  let busy = false;

  function show(id) {
    ["vsaiSetup", "vsaiDraft", "vsaiPositions", "vsaiResult"].forEach((x) => $("#" + x).classList.add("hidden"));
    $("#" + id).classList.remove("hidden");
  }

  function reset() { picks = []; bans = []; step = 0; myPos = {}; busy = false; }

  // ---- persistence (survive a page refresh mid-draft) ----
  const SKEY = "vsai_state";
  function save() {
    try { localStorage.setItem(SKEY, JSON.stringify({ diff, picks, bans, step, myPos })); } catch (e) {}
  }
  function clearSaved() { try { localStorage.removeItem(SKEY); } catch (e) {} }
  function loadSaved() {
    try { return JSON.parse(localStorage.getItem(SKEY) || "null"); } catch (e) { return null; }
  }

  function enter() {
    const s = loadSaved();
    if (s && s.picks && s.step > 0 && s.step <= CM.length) {    // resume an unfinished/just-finished draft
      diff = s.diff || "medium"; picks = s.picks; bans = s.bans || []; step = s.step; myPos = s.myPos || {};
      document.querySelectorAll("#vsaiDiffRow .diff-btn").forEach((x) => x.classList.toggle("active", x.dataset.diff === diff));
      show("vsaiDraft"); Board.moveTo("slot-vsai");
      $("#vsaiDiffTag").textContent = T("vsai.diffTag", { d: I18N.diffName(diff) });
      $("#vsaiToPos").classList.add("hidden");
      busy = false; advance();
      return;
    }
    reset(); show("vsaiSetup");
  }

  const cnt = (arr, team) => arr.filter((x) => x.team === team).length;

  function renderBoard(interactive) {
    Board.set({
      picks: picks.map((p) => ({ ...p })),
      bans: bans.map((b) => ({ ...b })),
      answered: false, answerHeroId: null, correct: null, guessHeroId: null,
    }, { showTeamNames: true, radiantName: T("vsai.you"), direName: T("vsai.ai"), showPlayers: false, onPick: interactive ? onAction : null });
  }

  function turnLabel() {
    const c = CM[step];
    if (c.who === "my") {
      $("#vsaiTurn").textContent = c.act === "pick"
        ? T("vsai.turnPickYou", { i: cnt(picks, MY) + 1 })
        : T("vsai.turnBanYou", { i: cnt(bans, MY) + 1 });
    } else {
      $("#vsaiTurn").textContent = c.act === "pick"
        ? T("vsai.turnPickAi", { i: cnt(picks, AI) + 1 })
        : T("vsai.turnBanAi", { i: cnt(bans, AI) + 1 });
    }
    $("#vsaiTurn").className = "run-round " + (c.act === "ban" ? "is-ban" : "is-pick");
  }

  function start() {
    reset(); clearSaved(); $("#vsaiToPos").classList.add("hidden");
    show("vsaiDraft"); Board.moveTo("slot-vsai");
    $("#vsaiDiffTag").textContent = T("vsai.diffTag", { d: I18N.diffName(diff) });
    advance();
  }

  function advance() {
    save();
    if (step >= CM.length) { draftComplete(); return; }
    turnLabel();
    if (CM[step].who === "my") renderBoard(true);
    else { renderBoard(false); aiStep(); }
  }

  function draftComplete() {
    renderBoard(false);                         // show the FULL board incl. AI's last pick
    $("#vsaiTurn").textContent = T("vsai.draftDone"); $("#vsaiTurn").className = "run-round";
    $("#vsaiToPos").classList.remove("hidden"); // wait for the player to move on
  }

  function onAction(heroId) {
    if (busy || CM[step].who !== "my") return;
    if (CM[step].act === "pick") picks.push({ team: MY, order: step, hero_id: heroId });
    else bans.push({ team: MY, hero_id: heroId });
    step++; advance();
  }

  async function aiStep() {
    busy = true;
    const c = CM[step];
    const aiTeam = picks.filter((p) => p.team === AI).map((p) => p.hero_id);
    const myTeam = picks.filter((p) => p.team === MY).map((p) => p.hero_id);
    const allBans = bans.map((b) => b.hero_id);
    let hid = null;
    try {
      const r = c.act === "pick"
        ? await API.draft.aipick({ aiTeam, myTeam, bans: allBans, difficulty: diff })
        : await API.draft.aiban({ aiTeam, myTeam, bans: allBans, difficulty: diff });
      hid = r.hero_id;
    } catch (e) {
      const used = new Set([...picks.map((p) => p.hero_id), ...allBans]);
      const pool = Object.values(HEROES).filter((h) => !used.has(h.id));
      if (pool.length) hid = pool[Math.floor(Math.random() * pool.length)].id;
    }
    if (hid != null) {
      if (c.act === "pick") picks.push({ team: AI, order: step, hero_id: hid });
      else bans.push({ team: AI, hero_id: hid });
    }
    step++; busy = false;
    setTimeout(advance, 380); // brief "thinking" beat
  }

  function toPositions() {
    $("#vsaiToPos").classList.add("hidden");
    show("vsaiPositions");
    const my = picks.filter((p) => p.team === MY).map((p) => p.hero_id);
    myPos = {}; my.forEach((h, i) => { myPos[h] = i + 1; });
    renderPosList(my);
  }

  function renderPosList(my) {
    const box = $("#vsaiPosList"); box.innerHTML = "";
    my.forEach((hid) => {
      const hero = HEROES[hid];
      const row = el("div", "pos-row");
      const img = el("img", "pos-portrait"); img.src = hero ? hero.img : ""; img.alt = hero ? hero.name : ""; img.loading = "lazy";
      const nm = el("span", "pos-hero"); nm.textContent = hero ? hero.name : ("#" + hid);
      const sel = el("select", "pos-select");
      for (let p = 1; p <= 5; p++) { const o = el("option"); o.value = String(p); o.textContent = I18N.role(p); if (myPos[hid] === p) o.selected = true; sel.appendChild(o); }
      sel.addEventListener("change", () => setPos(hid, parseInt(sel.value, 10), my));
      row.appendChild(img); row.appendChild(nm); row.appendChild(sel);
      box.appendChild(row);
    });
  }

  function setPos(hid, pos, my) {
    const prev = myPos[hid];
    const other = Object.keys(myPos).find((k) => myPos[k] === pos && Number(k) !== hid);
    if (other !== undefined) myPos[other] = prev; // keep a valid permutation by swapping
    myPos[hid] = pos;
    renderPosList(my);
  }

  async function analyze() {
    const myTeam = picks.filter((p) => p.team === MY).map((p) => p.hero_id);
    const aiTeam = picks.filter((p) => p.team === AI).map((p) => p.hero_id);
    const myPositions = {}; myTeam.forEach((h) => { myPositions[h] = myPos[h] || 0; });
    const allBans = bans.map((b) => b.hero_id);
    const btn = $("#vsaiAnalyzeBtn"); const old = btn.textContent; btn.disabled = true;
    let r;
    try { r = await API.draft.eval({ myTeam, myPositions, aiTeam, bans: allBans }); }
    catch (e) { btn.disabled = false; btn.textContent = old; return; }
    btn.disabled = false; btn.textContent = old;
    clearSaved();                 // draft finished — don't resume it on refresh
    renderResult(r);
  }

  function renderResult(r) {
    show("vsaiResult");
    const v = $("#vsaiVerdict");
    const key = r.winner === "mine" ? "vsai.verdictWin" : r.winner === "ai" ? "vsai.verdictLose" : "vsai.verdictTie";
    v.className = "verdict " + (r.winner === "mine" ? "win" : r.winner === "ai" ? "lose" : "tie");
    let extra = "";
    if (r.pros && r.pros.length) extra += `<div class="verdict-line pro"><b>${T("vsai.pros")}</b> ${r.pros.map((a) => I18N.evalAxis(a)).join(", ")}</div>`;
    if (r.cons && r.cons.length) extra += `<div class="verdict-line con"><b>${T("vsai.cons")}</b> ${r.cons.map((a) => I18N.evalAxis(a)).join(", ")}</div>`;
    const miss = (r.mine.concept && r.mine.concept.missing) || [];
    if (miss.length) extra += `<div class="verdict-line con"><b>${T("reason.lacks")}</b> ${miss.map((k) => I18N.conceptLabel(k)).join(", ")}</div>`;
    v.innerHTML = `<div class="verdict-title">${T(key)}</div>
      <div class="verdict-score">${T("vsai.scoreLine", { me: r.mine.score, ai: r.ai.score })}</div>
      <div class="verdict-arche"><span class="arche mine">${I18N.archetype(r.mine.archetype)}</span><span class="arche-vs">vs</span><span class="arche ai">${I18N.archetype(r.ai.archetype)}</span></div>${extra}`;

    const cmp = $("#vsaiCompare"); cmp.innerHTML = "";
    for (const ax of Object.keys(r.mine.axes)) {
      const mv = r.mine.axes[ax], av = r.ai.axes[ax];
      const row = el("div", "cmp-row");
      row.innerHTML =
        `<span class="cmp-half mine"><b class="cmp-val">${mv}</b><span class="track"><i style="width:${mv}%"></i></span></span>` +
        `<span class="cmp-axis">${I18N.evalAxis(ax)}</span>` +
        `<span class="cmp-half ai"><span class="track"><i style="width:${av}%"></i></span><b class="cmp-val">${av}</b></span>`;
      cmp.appendChild(row);
    }
    renderCoach(r.coach || []);
  }

  function reasonText(rs) {
    if (rs.type === "counter") return T("coach.counter", { name: rs.name });
    if (rs.type === "combo") return T("coach.combo", { name: rs.name });
    if (rs.type === "synergy") return T("coach.synergy", { name: rs.name });
    if (rs.type === "meta") return T("coach.meta");
    if (rs.type === "role") return T("coach.role");
    return T("coach.overall");
  }

  function renderCoach(coach) {
    const box = $("#vsaiCoach"); box.innerHTML = "";
    const head = el("div", "coach-head"); head.textContent = T("vsai.coachTitle"); box.appendChild(head);
    if (!coach.length) { const p = el("div", "coach-none"); p.textContent = T("vsai.coachNone"); box.appendChild(p); return; }
    const sub = el("div", "coach-sub"); sub.textContent = T("vsai.coachSub"); box.appendChild(sub);
    for (const c of coach) {
      const row = el("div", "coach-row");
      const yourH = HEROES[c.your.id], betterH = HEROES[c.better.id];
      const reasons = c.reasons.map(reasonText).join(", ");
      row.innerHTML =
        `<span class="coach-role">${I18N.role(c.pos)}</span>` +
        `<span class="coach-swap">` +
          `<img class="coach-hero bad" src="${yourH ? yourH.img : ""}" alt="" title="${c.your.name}">` +
          `<span class="coach-arrow">→</span>` +
          `<img class="coach-hero good" src="${betterH ? betterH.img : ""}" alt="" title="${c.better.name}">` +
          `<b class="coach-better">${c.better.name}</b>` +
        `</span>` +
        `<span class="coach-why">${reasons}</span>`;
      box.appendChild(row);
    }
  }

  function init() {
    document.querySelectorAll("#vsaiDiffRow .diff-btn").forEach((b) => {
      b.onclick = () => { diff = b.dataset.diff; document.querySelectorAll("#vsaiDiffRow .diff-btn").forEach((x) => x.classList.toggle("active", x === b)); };
    });
    $("#vsaiStartBtn").onclick = start;
    $("#vsaiToPos").onclick = toPositions;
    $("#vsaiAnalyzeBtn").onclick = analyze;
    $("#vsaiAgainBtn").onclick = () => { clearSaved(); reset(); show("vsaiSetup"); };
  }

  return { init, enter };
})();

// ============================================================ view switching
function setPickerTitle() {
  const h = document.getElementById("pickerTitle");
  if (!h) return;
  // "Who is the last pick?" only fits the guessing modes; drafting/builds just pick a hero.
  const guessMode = MODE === "casual" || MODE === "ranked" || MODE === "mp";
  h.textContent = T(guessMode ? "picker.title" : "picker.pick");
}

function switchMode(mode) {
  MODE = mode;
  try { localStorage.setItem("mode", mode); } catch (e) {}   // remember the tab across refresh
  document.querySelectorAll(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("#view-" + mode).classList.remove("hidden");
  $("#board").classList.toggle("builds-hide-draft", mode === "builds");  // builds reuses only the picker grid
  setPickerTitle();
  if (mode === "casual") Casual.enter();
  else if (mode === "ranked") Ranked.enter();
  else if (mode === "builds") Builds.enter();
  else if (mode === "vsai") VsAI.enter();
  else if (mode === "mp") MP.enter();
  else if (mode === "lb") Leaderboard.enter();
}

// ============================================================ init
async function init() {
  I18N.apply();
  try { await loadData(); }
  catch (e) {
    $("#loader").innerHTML = `<div class="error"><b>Failed to load data.</b><br>${e.message}</div>`; return;
  }
  await API.refreshMe();
  $("#loader").classList.add("hidden");

  Casual.init(); Ranked.init(); Builds.init(); VsAI.init(); MP.init(); Leaderboard.init(); Auth.init();

  document.querySelectorAll(".mode-btn").forEach((b) => b.onclick = () => switchMode(b.dataset.mode));
  document.querySelectorAll("#langToggle button").forEach((b) => {
    b.classList.toggle("active", b.dataset.lang === I18N.get());
    b.onclick = () => { I18N.set(b.dataset.lang); document.querySelectorAll("#langToggle button").forEach((x) => x.classList.toggle("active", x.dataset.lang === I18N.get())); };
  });

  // shared search wiring
  $("#search").addEventListener("input", (e) => Board.applySearch(e.target.value));
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if ($("#authModal").classList.contains("hidden") === false) return;
    // type-to-focus removed: on desktop it hijacked the cursor (couldn't copy text)
    if (e.key === "Enter") {
      const vis = [...document.querySelectorAll(".hero:not(.dim):not(.used):not(.banned)")];
      const st = Board.get();
      if (st && !st.answered && vis.length === 1) vis[0].click();
    }
  });

  document.addEventListener("langchange", () => {
    Auth.widget();
    if (MODE === "lb") Leaderboard.enter();
    if (MODE === "casual") Casual.relabel();
    setPickerTitle();
    Reasoning.refresh();  // repaint analytics in whichever mode shows it (casual/ranked)
  });

  const VALID = ["casual", "ranked", "builds", "vsai", "mp", "lb"];
  let startMode = "casual";
  try { const s = localStorage.getItem("mode"); if (VALID.includes(s)) startMode = s; } catch (e) {}
  switchMode(startMode);
}

init();
