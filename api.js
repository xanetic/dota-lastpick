"use strict";
// Backend client. Auto-detects API base for local dev vs prod mount.
const API = (() => {
  const isLocal = ["127.0.0.1", "localhost"].includes(location.hostname);
  const MOUNT = location.pathname.includes("/guessthelastpick") ? "/guessthelastpick/api" : "/api";
  const BASE = isLocal ? "http://127.0.0.1:8422/api" : MOUNT;

  let token = localStorage.getItem("token") || null;
  let user = null;

  function setToken(t) { token = t; if (t) localStorage.setItem("token", t); else localStorage.removeItem("token"); }
  function getUser() { return user; }
  function isAuthed() { return !!token; }

  async function req(path, { method = "GET", body } = {}) {
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = "Bearer " + token;
    const res = await fetch(BASE + path, {
      method, headers, body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) throw new Error((data && data.detail) || ("HTTP " + res.status));
    return data;
  }

  async function register(username, password) {
    const r = await req("/register", { method: "POST", body: { username, password } });
    setToken(r.token); user = r.user; return user;
  }
  async function login(username, password) {
    const r = await req("/login", { method: "POST", body: { username, password } });
    setToken(r.token); user = r.user; return user;
  }
  async function logout() {
    try { await req("/logout", { method: "POST" }); } catch (e) {}
    setToken(null); user = null;
  }
  async function refreshMe() {
    if (!token) { user = null; return null; }
    try { const r = await req("/me"); user = r.user; return user; }
    catch (e) { setToken(null); user = null; return null; }
  }

  const solo = {
    start: () => req("/solo/start", { method: "POST" }),
    guess: (session, hero_id) => req("/solo/guess", { method: "POST", body: { session, hero_id } }),
  };
  const leaderboard = () => req("/leaderboard");
  const leaderboardBuilds = () => req("/leaderboard/builds");
  const builds = {
    next: () => req("/builds/new"),
    guess: (payload) => req("/builds/guess", { method: "POST", body: payload }),
  };
  const analyze = (payload) => req("/analyze", { method: "POST", body: payload });
  const draft = {
    aipick: (payload) => req("/draft/aipick", { method: "POST", body: payload }),
    aiban: (payload) => req("/draft/aiban", { method: "POST", body: payload }),
    eval: (payload) => req("/draft/eval", { method: "POST", body: payload }),
  };
  const mpCreate = (mode) => req("/mp/create", { method: "POST", body: { mode: mode || "guess" } });

  function wsUrl(code) {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const host = isLocal ? "127.0.0.1:8422" : location.host;
    const path = isLocal ? "/api/mp/ws" : MOUNT + "/mp/ws";
    return `${scheme}://${host}${path}?code=${encodeURIComponent(code)}&token=${encodeURIComponent(token || "")}`;
  }

  return { register, login, logout, refreshMe, getUser, isAuthed, setToken,
           solo, leaderboard, leaderboardBuilds, builds, analyze, draft, mpCreate, wsUrl };
})();
