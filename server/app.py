"""
Guess the Last Pick — game backend.

Provides: auth (login/password), ranked solo (5 rounds, server-validated),
Dota-style medal/rank system, leaderboard, and 1v1 multiplayer over WebSocket.

Casual (unranked) mode stays fully client-side; this backend only powers the
ranked / account / multiplayer features. Runs isolated on port 8422 in its own
venv — it does NOT touch the geekbot service (port 8000) or the VPN.
"""

import os
import json
import time
import uuid
import sqlite3
import secrets
import hashlib
import random
import asyncio
import threading
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
DB_PATH = os.path.join(DATA, "game.db")

# ---------------------------------------------------------------- data load
with open(os.path.join(DATA, "matches.json"), encoding="utf-8") as f:
    MATCHES = json.load(f)
with open(os.path.join(DATA, "heroes.json"), encoding="utf-8") as f:
    HEROES = json.load(f)  # id(str) -> {id,name,attr,img,...}

# matches indexed by id, and a clean list usable for ranked (must have a valid answer)
MATCH_BY_ID = {m["match_id"]: m for m in MATCHES}
RANKED_POOL = [m for m in MATCHES if m.get("answer") and m.get("picks")]

HERO_NAME = {int(h["id"]): h["name"] for h in HEROES.values()}

# "guess the build" pool (server-side so the answer isn't leaked to the client)
try:
    with open(os.path.join(DATA, "builds.json"), encoding="utf-8") as f:
        BUILDS = json.load(f)
except Exception:
    BUILDS = []

# ---------------------------------------------------------------- db
_db_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db_lock, db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT UNIQUE NOT NULL,
                uname_lc  TEXT UNIQUE NOT NULL,
                pw_hash   TEXT NOT NULL,
                salt      TEXT NOT NULL,
                rating    INTEGER NOT NULL DEFAULT 0,
                games     INTEGER NOT NULL DEFAULT 0,
                wins      INTEGER NOT NULL DEFAULT 0,
                best      INTEGER NOT NULL DEFAULT 0,
                created   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token     TEXT PRIMARY KEY,
                user_id   INTEGER NOT NULL,
                expires   REAL NOT NULL
            );
            """
        )
        for col in ("builds_played", "builds_correct"):   # migrate older DBs
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            except Exception:
                pass


# ---------------------------------------------------------------- auth helpers
def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def make_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _db_lock, db() as c:
        c.execute(
            "INSERT INTO sessions(token,user_id,expires) VALUES(?,?,?)",
            (token, user_id, time.time() + 60 * 60 * 24 * 30),
        )
    return token


def user_from_token(token: Optional[str]):
    if not token:
        return None
    if token.lower().startswith("bearer "):
        token = token[7:]
    with db() as c:
        row = c.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token=? AND s.expires>?",
            (token, time.time()),
        ).fetchone()
    return row


def require_user(authorization: Optional[str]):
    u = user_from_token(authorization)
    if not u:
        raise HTTPException(status_code=401, detail="auth required")
    return u


# ---------------------------------------------------------------- medals / rank
TIERS = ["Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine"]
BAND = 700        # rating points per medal
STAR = BAND // 5  # 140 per star


def medal(rating: int) -> dict:
    r = max(0, int(rating))
    if r >= BAND * len(TIERS):  # 4900+
        return {"tier": "Immortal", "star": 0, "label": f"Immortal · {r}", "rating": r}
    idx = r // BAND
    star = (r % BAND) // STAR + 1
    return {"tier": TIERS[idx], "star": star, "label": f"{TIERS[idx]} {star}", "rating": r}


def _col(row, name, default=0):
    try:
        v = row[name]
        return v if v is not None else default
    except (IndexError, KeyError):
        return default


def public_user(row) -> dict:
    bp = _col(row, "builds_played"); bc = _col(row, "builds_correct")
    return {
        "username": row["username"],
        "rating": row["rating"],
        "medal": medal(row["rating"]),
        "games": row["games"],
        "wins": row["wins"],
        "best": row["best"],
        "builds_played": bp,
        "builds_correct": bc,
        "builds_wr": round(bc / bp, 3) if bp else 0.0,
    }


# ---------------------------------------------------------------- match sanitize
def sanitize(m: dict) -> dict:
    """Client-facing view of a ranked match: the last pick is hidden, and no
    metadata that would let the player look the match up is leaked."""
    ans = m["answer"]
    picks = []
    for p in sorted(m["picks"], key=lambda x: x.get("order", 0)):
        hidden = p["hero_id"] == ans["hero_id"] and p["team"] == ans["team"]
        picks.append(
            {
                "team": p["team"],
                "order": p.get("order", 0),
                "hero_id": None if hidden else p["hero_id"],
                "hidden": hidden,
            }
        )
    return {
        "picks": picks,
        "bans": [{"team": b["team"], "hero_id": b["hero_id"]} for b in m.get("bans", [])],
        "answer_team": ans["team"],  # which side the missing pick belongs to
    }


def reveal(m: dict) -> dict:
    ans = m["answer"]
    return {
        "hero_id": ans["hero_id"],
        "hero_name": HERO_NAME.get(ans["hero_id"], f"#{ans['hero_id']}"),
        "answer_team": ans["team"],
        "match_id": m["match_id"],
        "league": m.get("league"),
        "year": m.get("year"),
        "patch": m.get("patch"),
        "is_ti": m.get("is_ti"),
        "radiant_team": m.get("radiant_team"),
        "dire_team": m.get("dire_team"),
        "radiant_win": m.get("radiant_win"),
        "radiant_score": m.get("radiant_score"),
        "dire_score": m.get("dire_score"),
        "duration": m.get("duration"),
    }


def match_analysis(m: dict):
    """Full reasoning for a revealed match (same shape as POST /api/analyze),
    built server-side so ranked/mp can show the analytics after the guess."""
    if analyzer is None:
        return None
    try:
        ans = m["answer"]
        ateam = ans["team"]
        allies, ally_acc, enemies = [], [], []
        picker = None
        for p in m["picks"]:
            is_answer = p["hero_id"] == ans["hero_id"] and p["team"] == ateam
            if is_answer:
                picker = p.get("account_id")
                continue
            if p["team"] == ateam:
                allies.append(p["hero_id"]); ally_acc.append(p.get("account_id"))
            else:
                enemies.append(p["hero_id"])
        bans = [b["hero_id"] for b in m.get("bans", [])]
        return analyzer.analyze(allies, enemies, bans, answer=ans["hero_id"],
                                picker=picker, ally_accounts=ally_acc)
    except Exception:
        return None


# ---------------------------------------------------------------- scoring
SOLO_ROUNDS = 5
CORRECT_PTS = 60
WRONG_PTS = -10


def tier_points(rating: int):
    """Progressive rating curve: low ranks give a lot & take little (easy to climb
    out of Herald); each tier up gives less and takes more (hard near Divine)."""
    tier = min(6, max(0, int(rating) // BAND))     # 0 Herald .. 6 Divine
    reward = max(35, 110 - 13 * tier)              # correct round: Herald +110 → Divine +35
    penalty = min(50, 5 + 8 * tier)                # wrong round:   Herald -5   → Divine -50
    return reward, penalty


def apply_solo_result(user_id: int, score: int, correct: int):
    """score = sum of round points; persist rating (floored 0), games, best, wins."""
    with _db_lock, db() as c:
        u = c.execute("SELECT rating,games,best FROM users WHERE id=?", (user_id,)).fetchone()
        new_rating = max(0, u["rating"] + score)
        new_best = max(u["best"], correct)
        won = 1 if correct >= 3 else 0  # "win" a solo set = 3/5+
        c.execute(
            "UPDATE users SET rating=?,games=games+1,best=?,wins=wins+? WHERE id=?",
            (new_rating, new_best, won, user_id),
        )
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return row, new_rating


# ---------------------------------------------------------------- solo sessions (in-memory)
SOLO = {}  # session_id -> {user_id, match_ids[], idx, score, correct}


def new_solo_session(user_id: int) -> dict:
    ids = [m["match_id"] for m in random.sample(RANKED_POOL, SOLO_ROUNDS)]
    sid = uuid.uuid4().hex
    with db() as c:
        u = c.execute("SELECT rating FROM users WHERE id=?", (user_id,)).fetchone()
    reward, penalty = tier_points(u["rating"] if u else 0)
    SOLO[sid] = {"user_id": user_id, "match_ids": ids, "idx": 0, "score": 0, "correct": 0,
                 "reward": reward, "penalty": penalty}
    return {"session": sid, "round": _solo_round_payload(sid), "reward": reward, "penalty": penalty}


def _solo_round_payload(sid: str) -> dict:
    s = SOLO[sid]
    m = MATCH_BY_ID[s["match_ids"][s["idx"]]]
    return {"idx": s["idx"] + 1, "total": SOLO_ROUNDS, "match": sanitize(m)}


# ================================================================ app
app = FastAPI(title="Guess the Last Pick API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
init_db()

# Draft Reasoning Engine v2 (optional — service still runs if its data is missing)
try:
    from server import analyze as analyzer
    print(f"analyzer loaded: {len(analyzer.HERO_IDS)} heroes, {len(analyzer.PLAYERS)} players")
except Exception as _e:  # noqa: BLE001
    analyzer = None
    print("analyzer disabled:", _e)


@app.get("/api/health")
def health():
    return {"ok": True, "matches": len(RANKED_POOL), "users": _count_users()}


def _count_users():
    with db() as c:
        return c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]


# ----------------------------------------------- auth
def _valid_name(n: str) -> bool:
    return isinstance(n, str) and 3 <= len(n) <= 20 and n.strip() == n


@app.post("/api/register")
def register(body: dict = Body(...)):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not _valid_name(username):
        raise HTTPException(400, "username must be 3-20 chars")
    if len(password) < 4:
        raise HTTPException(400, "password too short (min 4)")
    salt = secrets.token_hex(8)
    pwh = hash_pw(password, salt)
    try:
        with _db_lock, db() as c:
            cur = c.execute(
                "INSERT INTO users(username,uname_lc,pw_hash,salt,created) VALUES(?,?,?,?,?)",
                (username, username.lower(), pwh, salt, time.time()),
            )
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "username taken")
    token = make_token(uid)
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return {"token": token, "user": public_user(row)}


@app.post("/api/login")
def login(body: dict = Body(...)):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE uname_lc=?", (username.lower(),)).fetchone()
    if not row or hash_pw(password, row["salt"]) != row["pw_hash"]:
        raise HTTPException(401, "wrong username or password")
    token = make_token(row["id"])
    return {"token": token, "user": public_user(row)}


@app.get("/api/me")
def me(authorization: Optional[str] = Header(None)):
    u = require_user(authorization)
    return {"user": public_user(u)}


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(None)):
    tok = authorization or ""
    if tok.lower().startswith("bearer "):
        tok = tok[7:]
    with _db_lock, db() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (tok,))
    return {"ok": True}


# ----------------------------------------------- ranked solo
@app.post("/api/solo/start")
def solo_start(authorization: Optional[str] = Header(None)):
    u = require_user(authorization)
    return new_solo_session(u["id"])


@app.post("/api/solo/guess")
def solo_guess(body: dict = Body(...), authorization: Optional[str] = Header(None)):
    u = require_user(authorization)
    sid = body.get("session")
    hero_id = body.get("hero_id")
    s = SOLO.get(sid)
    if not s or s["user_id"] != u["id"]:
        raise HTTPException(404, "no such session")
    m = MATCH_BY_ID[s["match_ids"][s["idx"]]]
    correct = hero_id == m["answer"]["hero_id"]
    reward = s.get("reward", CORRECT_PTS); penalty = s.get("penalty", -WRONG_PTS)
    pts = reward if correct else -penalty
    s["score"] += pts
    if correct:
        s["correct"] += 1
    s["idx"] += 1

    out = {
        "correct": correct,
        "points": pts,
        "reveal": reveal(m),
        "analysis": match_analysis(m),
        "round_score": s["score"],
        "correct_count": s["correct"],
    }
    if s["idx"] >= SOLO_ROUNDS:
        row, new_rating = apply_solo_result(u["id"], s["score"], s["correct"])
        out.update(
            {
                "finished": True,
                "total_score": s["score"],
                "user": public_user(row),
                "delta": s["score"],
                "medal": medal(new_rating),
            }
        )
        SOLO.pop(sid, None)
    else:
        out.update({"finished": False, "next": _solo_round_payload(sid)})
    return out


# ----------------------------------------------- leaderboard
@app.get("/api/leaderboard")
def leaderboard():
    with db() as c:
        rows = c.execute(
            "SELECT username,rating,games,wins FROM users ORDER BY rating DESC, games ASC LIMIT 100"
        ).fetchall()
    top = []
    for i, r in enumerate(rows, 1):
        top.append(
            {
                "rank": i,
                "username": r["username"],
                "rating": r["rating"],
                "medal": medal(r["rating"]),
                "games": r["games"],
                "wins": r["wins"],
            }
        )
    return {"top": top}


# ----------------------------------------------- guess the build (account-tracked)
@app.get("/api/builds/new")
def builds_new():
    if not BUILDS:
        raise HTTPException(503, "no builds")
    i = random.randrange(len(BUILDS))
    b = BUILDS[i]
    return {"id": i, "items": b.get("items", []), "neutral": b.get("neutral", 0)}


@app.post("/api/builds/guess")
def builds_guess(body: dict = Body(...), authorization: Optional[str] = Header(None)):
    i = body.get("id")
    if not isinstance(i, int) or i < 0 or i >= len(BUILDS):
        raise HTTPException(400, "bad build id")
    b = BUILDS[i]
    correct = body.get("hero_id") == b["hero_id"]
    out = {
        "correct": correct,
        "answer": {
            "hero_id": b["hero_id"], "hero_name": HERO_NAME.get(b["hero_id"], f"#{b['hero_id']}"),
            "player": b.get("player"), "win": b.get("win"), "league": b.get("league"),
            "year": b.get("year"), "patch": b.get("patch"), "match_id": b.get("match_id"),
            "items": b.get("items", []), "neutral": b.get("neutral", 0),
        },
    }
    u = user_from_token(authorization)
    if u:
        with _db_lock, db() as c:
            c.execute("UPDATE users SET builds_played=builds_played+1, builds_correct=builds_correct+? WHERE id=?",
                      (1 if correct else 0, u["id"]))
            row = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
        bp = _col(row, "builds_played"); bc = _col(row, "builds_correct")
        out["stats"] = {"played": bp, "correct": bc, "winrate": round(bc / bp, 3) if bp else 0.0}
    return out


@app.get("/api/leaderboard/builds")
def leaderboard_builds():
    with db() as c:
        rows = c.execute(
            "SELECT username,builds_played,builds_correct FROM users "
            "WHERE builds_played>0 ORDER BY builds_correct DESC, builds_played ASC LIMIT 100"
        ).fetchall()
    top = []
    for i, r in enumerate(rows, 1):
        bp = _col(r, "builds_played"); bc = _col(r, "builds_correct")
        top.append({"rank": i, "username": r["username"], "played": bp, "correct": bc,
                    "winrate": round(bc / bp, 3) if bp else 0.0})
    return {"top": top}


# ----------------------------------------------- draft analysis (engine v2)
@app.post("/api/analyze")
def analyze_ep(body: dict = Body(...)):
    if analyzer is None:
        raise HTTPException(503, "analyzer unavailable")
    allies = body.get("allies") or []
    enemies = body.get("enemies") or []
    bans = body.get("bans") or []
    if not allies:
        raise HTTPException(400, "allies required")
    try:
        return analyzer.analyze(allies, enemies, bans,
                                answer=body.get("answer"), picker=body.get("picker"),
                                ally_accounts=body.get("allyAccounts"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"analyze error: {e}")


# ----------------------------------------------- vs-AI draft mode
@app.post("/api/draft/aipick")
def aipick_ep(body: dict = Body(...)):
    if analyzer is None:
        raise HTTPException(503, "analyzer unavailable")
    try:
        r = analyzer.ai_pick(body.get("aiTeam") or [], body.get("myTeam") or [],
                             body.get("bans") or [], body.get("difficulty", "medium"))
        if not r:
            raise HTTPException(400, "no available pick")
        return r
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"aipick error: {e}")


@app.post("/api/draft/aiban")
def aiban_ep(body: dict = Body(...)):
    if analyzer is None:
        raise HTTPException(503, "analyzer unavailable")
    try:
        r = analyzer.ai_ban(body.get("aiTeam") or [], body.get("myTeam") or [],
                            body.get("bans") or [], body.get("difficulty", "medium"))
        if not r:
            raise HTTPException(400, "no available ban")
        return r
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"aiban error: {e}")


@app.post("/api/draft/eval")
def drafteval_ep(body: dict = Body(...)):
    if analyzer is None:
        raise HTTPException(503, "analyzer unavailable")
    my_team = body.get("myTeam") or []
    ai_team = body.get("aiTeam") or []
    if len(my_team) < 1 or len(ai_team) < 1:
        raise HTTPException(400, "both teams required")
    try:
        return analyzer.draft_eval(my_team, body.get("myPositions") or {}, ai_team, body.get("bans") or [])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"eval error: {e}")


# ================================================================ multiplayer
class Lobby:
    def __init__(self, code, host_id, host_name, mode="guess"):
        self.code = code
        self.host_id = host_id
        self.mode = mode          # "guess" (last-pick race) | "draft" (Captains-Mode duel)
        self.players = {}        # user_id -> {name, ws, idx, score, correct, done, guessed_round}
        self.match_ids = []
        self.started = False
        self.finished = False
        self.created = time.time()
        # draft-duel state
        self.dstep = 0
        self.dpicks = {"radiant": [], "dire": []}
        self.dbans = []          # [{team, hero_id}]
        self.dpos = {}           # user_id -> {hero_id: pos}
        self.guest_id = None     # second player (T2 / dire)

    def add(self, user_id, name, ws):
        self.players[user_id] = {
            "name": name, "ws": ws, "idx": 0, "score": 0,
            "correct": 0, "done": False,
        }

    def others(self, user_id):
        return [p for uid, p in self.players.items() if uid != user_id]

    def state_msg(self):
        return {
            "type": "lobby",
            "code": self.code,
            "host": self.host_id,
            "started": self.started,
            "mode": self.mode,
            "players": [
                {"name": p["name"], "ready": True, "is_host": uid == self.host_id}
                for uid, p in self.players.items()
            ],
        }


LOBBIES = {}  # code -> Lobby
_lobby_lock = asyncio.Lock()


def _gen_code() -> str:
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(random.choice(alpha) for _ in range(5))
        if code not in LOBBIES:
            return code


@app.post("/api/mp/create")
def mp_create(body: dict = Body(default=None), authorization: Optional[str] = Header(None)):
    u = require_user(authorization)
    mode = (body or {}).get("mode", "guess")
    if mode not in ("guess", "draft"):
        mode = "guess"
    code = _gen_code()
    LOBBIES[code] = Lobby(code, u["id"], u["username"], mode)
    return {"code": code, "mode": mode}


# Captains-Mode order for the PvP draft duel (t1 = host/radiant, t2 = guest/dire)
CM_PVP = (
    [("t1", "ban"), ("t2", "ban"), ("t1", "ban"), ("t2", "ban")] +
    [("t1", "pick"), ("t2", "pick"), ("t2", "pick"), ("t1", "pick")] +
    [("t1", "ban"), ("t2", "ban"), ("t1", "ban"), ("t2", "ban"), ("t1", "ban"), ("t2", "ban")] +
    [("t1", "pick"), ("t2", "pick"), ("t2", "pick"), ("t1", "pick")] +
    [("t1", "ban"), ("t2", "ban"), ("t1", "ban"), ("t2", "ban")] +
    [("t1", "pick"), ("t2", "pick")]
)


def _draft_turn_uid(lobby: Lobby):
    if lobby.dstep >= len(CM_PVP):
        return None
    who = CM_PVP[lobby.dstep][0]
    return lobby.host_id if who == "t1" else lobby.guest_id


def _draft_state_msg(lobby: Lobby):
    done = lobby.dstep >= len(CM_PVP)
    cur = None if done else CM_PVP[lobby.dstep]
    return {
        "type": "draft_state",
        "picks": [{"team": t, "hero_id": h} for t in ("radiant", "dire") for h in lobby.dpicks[t]],
        "bans": lobby.dbans,
        "step": lobby.dstep, "total": len(CM_PVP),
        "turn_uid": _draft_turn_uid(lobby),
        "act": (cur[1] if cur else None),
        "host_id": lobby.host_id,
    }


async def _draft_finish(lobby: Lobby):
    if analyzer is None:
        return
    host_pos = lobby.dpos.get(lobby.host_id, {})
    guest_pos = lobby.dpos.get(lobby.guest_id, {})
    rad = lobby.dpicks["radiant"]; dire = lobby.dpicks["dire"]
    bans = [b["hero_id"] for b in lobby.dbans]
    ea = analyzer.draft_eval(rad, host_pos, dire, bans)
    eb = analyzer.draft_eval(dire, guest_pos, rad, bans)
    sa, sb = ea["mine"]["score"], eb["mine"]["score"]
    winner = lobby.host_id if sa > sb + 2 else lobby.guest_id if sb > sa + 2 else None
    hp = lobby.players.get(lobby.host_id); gp = lobby.players.get(lobby.guest_id)
    res = {
        "type": "draft_result",
        "host": {"id": lobby.host_id, "name": hp["name"] if hp else "?", "eval": ea, "coach": ea.get("coach")},
        "guest": {"id": lobby.guest_id, "name": gp["name"] if gp else "?", "eval": eb, "coach": eb.get("coach")},
        "winner": winner,
    }
    lobby.finished = True
    await _broadcast(lobby, res)


async def _send(ws: WebSocket, obj: dict):
    try:
        await ws.send_text(json.dumps(obj))
    except Exception:
        pass


async def _broadcast(lobby: Lobby, obj: dict):
    for p in list(lobby.players.values()):
        await _send(p["ws"], obj)


def _mp_round_payload(lobby: Lobby, idx: int) -> dict:
    m = MATCH_BY_ID[lobby.match_ids[idx]]
    return {"type": "round", "idx": idx + 1, "total": SOLO_ROUNDS, "match": sanitize(m)}


async def _progress(lobby: Lobby):
    """Tell each player their own + opponents' progress (score, round, done)."""
    for uid, p in lobby.players.items():
        opp = lobby.others(uid)
        await _send(
            p["ws"],
            {
                "type": "progress",
                "you": {"idx": p["idx"], "score": p["score"], "correct": p["correct"], "done": p["done"]},
                "opponents": [
                    {"name": o["name"], "idx": o["idx"], "done": o["done"]}
                    for o in opp
                ],
            },
        )


async def _maybe_finish(lobby: Lobby):
    if lobby.finished or not lobby.players:
        return
    if not all(p["done"] for p in lobby.players.values()):
        return
    lobby.finished = True
    ranked = sorted(lobby.players.items(), key=lambda kv: kv[1]["score"], reverse=True)
    top_score = ranked[0][1]["score"]
    winners = [uid for uid, p in ranked if p["score"] == top_score]
    # rating: winner +40, others -20 (floored), draw +10 each; plus persist game stats
    results = []
    for uid, p in lobby.players.items():
        if len(winners) > 1 and uid in winners:
            delta = 10
        elif uid in winners:
            delta = 40
        else:
            delta = -20
        won = 1 if (uid in winners and len(winners) == 1) else 0
        with _db_lock, db() as c:
            row = c.execute("SELECT rating,best FROM users WHERE id=?", (uid,)).fetchone()
            if row:
                new_rating = max(0, row["rating"] + delta)
                new_best = max(row["best"], p["correct"])
                c.execute(
                    "UPDATE users SET rating=?,games=games+1,wins=wins+?,best=? WHERE id=?",
                    (new_rating, won, new_best, uid),
                )
            else:
                new_rating = 0
        results.append(
            {"name": p["name"], "score": p["score"], "correct": p["correct"],
             "delta": delta, "rating": new_rating, "medal": medal(new_rating),
             "winner": uid in winners}
        )
    await _broadcast(lobby, {"type": "result", "draw": len(winners) > 1, "players": results})


@app.websocket("/api/mp/ws")
async def mp_ws(ws: WebSocket, code: str = "", token: str = ""):
    await ws.accept()
    u = user_from_token(token)
    code = code.upper()
    lobby = LOBBIES.get(code)
    if not u or not lobby:
        await _send(ws, {"type": "error", "error": "invalid lobby or auth"})
        await ws.close()
        return
    if len(lobby.players) >= 2 and u["id"] not in lobby.players:
        await _send(ws, {"type": "error", "error": "lobby full"})
        await ws.close()
        return

    lobby.add(u["id"], u["username"], ws)
    await _broadcast(lobby, lobby.state_msg())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            t = msg.get("type")

            if t == "start" and u["id"] == lobby.host_id and not lobby.started:
                if len(lobby.players) < 2:
                    await _send(ws, {"type": "error", "error": "need 2 players"})
                    continue
                lobby.started = True
                if lobby.mode == "draft":
                    lobby.guest_id = next(uid for uid in lobby.players if uid != lobby.host_id)
                    lobby.dstep = 0; lobby.dpicks = {"radiant": [], "dire": []}; lobby.dbans = []; lobby.dpos = {}
                    await _broadcast(lobby, {"type": "draft_begin", "host_id": lobby.host_id, "total": len(CM_PVP)})
                    await _broadcast(lobby, _draft_state_msg(lobby))
                    continue
                lobby.match_ids = [m["match_id"] for m in random.sample(RANKED_POOL, SOLO_ROUNDS)]
                for p in lobby.players.values():
                    p["idx"] = 0
                await _broadcast(lobby, {"type": "begin", "total": SOLO_ROUNDS})
                # NB: do NOT broadcast a lobby state here — the client's lobby
                # handler would switch the view back from the game to the lobby.
                for uid, p in lobby.players.items():
                    await _send(p["ws"], _mp_round_payload(lobby, 0))

            elif t == "draft_act" and lobby.started and lobby.mode == "draft" and not lobby.finished:
                if lobby.dstep >= len(CM_PVP) or _draft_turn_uid(lobby) != u["id"]:
                    continue
                hid = msg.get("hero_id")
                used = set(lobby.dpicks["radiant"] + lobby.dpicks["dire"] + [b["hero_id"] for b in lobby.dbans])
                if not isinstance(hid, int) or hid in used:
                    continue
                who, act = CM_PVP[lobby.dstep]
                team = "radiant" if who == "t1" else "dire"
                if act == "pick":
                    lobby.dpicks[team].append(hid)
                else:
                    lobby.dbans.append({"team": team, "hero_id": hid})
                lobby.dstep += 1
                await _broadcast(lobby, _draft_state_msg(lobby))
                if lobby.dstep >= len(CM_PVP):
                    await _broadcast(lobby, {"type": "draft_positions"})

            elif t == "draft_pos" and lobby.mode == "draft" and not lobby.finished:
                pos = msg.get("positions") or {}
                lobby.dpos[u["id"]] = {int(k): int(v) for k, v in pos.items()}
                if lobby.host_id in lobby.dpos and lobby.guest_id in lobby.dpos:
                    await _draft_finish(lobby)

            elif t == "guess" and lobby.started and not lobby.finished:
                p = lobby.players.get(u["id"])
                if not p or p["done"]:
                    continue
                m = MATCH_BY_ID[lobby.match_ids[p["idx"]]]
                correct = msg.get("hero_id") == m["answer"]["hero_id"]
                p["score"] += CORRECT_PTS if correct else WRONG_PTS
                if correct:
                    p["correct"] += 1
                await _send(
                    ws,
                    {"type": "reveal", "correct": correct, "reveal": reveal(m),
                     "analysis": match_analysis(m),
                     "round_score": p["score"], "idx": p["idx"] + 1},
                )
                p["idx"] += 1
                if p["idx"] >= SOLO_ROUNDS:
                    p["done"] = True
                else:
                    await _send(ws, _mp_round_payload(lobby, p["idx"]))
                await _progress(lobby)
                await _maybe_finish(lobby)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if u["id"] in lobby.players:
            lobby.players.pop(u["id"], None)
        if not lobby.players:
            LOBBIES.pop(code, None)
        else:
            if not lobby.started:
                await _broadcast(lobby, lobby.state_msg())  # only relevant pre-game
            await _broadcast(lobby, {"type": "peer_left"})


# periodic cleanup of stale lobbies / expired sessions
@app.on_event("startup")
async def _cleanup_task():
    async def loop():
        while True:
            await asyncio.sleep(600)
            now = time.time()
            for code in [c for c, l in LOBBIES.items() if now - l.created > 3600 and not l.players]:
                LOBBIES.pop(code, None)
            try:
                with _db_lock, db() as c:
                    c.execute("DELETE FROM sessions WHERE expires<?", (now,))
            except Exception:
                pass
    asyncio.create_task(loop())
