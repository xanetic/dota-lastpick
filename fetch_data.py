#!/usr/bin/env python3
"""
Fetches data for the "Guess the Last Pick" game from the OpenDota API
(free, no key required).

Outputs:
  data/heroes.json   - heroes: id, name, attribute (str/agi/int/all), image
  data/matches.json  - tournament matches: picks + bans with draft order,
                       pro player nicknames, and the marked last pick (answer).

Scraping Dotabuff directly is blocked by Cloudflare, so we use OpenDota, which
exposes the same data as clean JSON. Hero portraits come from Valve's CDN.

Usage:
  python3 fetch_data.py                       # default caps
  python3 fetch_data.py --ti 50 --other 22    # matches per TI / per other event
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
import urllib.error

API = "https://api.opendota.com/api"
HERO_IMG_BASE = "https://cdn.cloudflare.steamstatic.com"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
USER_AGENT = "lastpick-game/1.0 (local hobby project)"

# The International — leagueid -> fallback display name.
INTERNATIONALS = {
    600: "The International 2014",
    2733: "The International 2015",
    4664: "The International 2016",
    5401: "The International 2017",
    9870: "The International 2018",
    10749: "The International 2019",
    11625: "The International 10",
    13256: "The International 2021",
    14268: "The International 2022",
    15728: "The International 2023",
    16935: "The International 2024",
    18324: "The International 2025",
}

# Other marquee tournaments (Majors + big LANs) — leagueid -> fallback name.
OTHER_LEAGUES = {
    19101: "BLAST Slam VII",
    19099: "BLAST Slam VI",
    18937: "Games of the Future 2025",
    16881: "Riyadh Masters 2024",
    16905: "Elite League Season 2",
    19269: "DreamLeague Season 28",
    18111: "DreamLeague Season 26",
    16632: "DreamLeague Season 23",
    18920: "PGL Wallachia 2025 Season 6",
    17119: "PGL Wallachia 2024 Season 2",
    16518: "ESL One Birmingham 2024",
    15910: "ESL One Kuala Lumpur 2023",
    17509: "ESL One Bangkok 2024",
    17126: "BetBoom Dacha Belgrade 2024",
    15438: "The Bali Major 2023",
    15251: "ESL One Berlin Major 2023",
    15089: "Lima Major 2023",
    14417: "PGL Arlington Major 2022",
    14173: "ESL One Stockholm Major 2022",
    12906: "The Singapore Major 2021",
}


def fetch_json(url, retries=4, pause=2.0):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            code = getattr(e, "code", None)
            wait = pause * (4 if code == 429 else 1) * (attempt + 1)
            print(f"  ! {e} (try {attempt+1}/{retries}), waiting {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def build_heroes():
    print("Fetching heroes...")
    stats = fetch_json(f"{API}/heroStats")
    heroes = {}
    for h in stats:
        heroes[h["id"]] = {
            "id": h["id"],
            "name": h["localized_name"],
            "attr": h.get("primary_attr", "all"),     # str / agi / int / all
            "img": HERO_IMG_BASE + h["img"].rstrip("?"),
            "icon": HERO_IMG_BASE + h["icon"].rstrip("?"),
        }
    print(f"  heroes: {len(heroes)}")
    return heroes


def load_patches():
    """Return list of (epoch_seconds, name) sorted ascending by date."""
    data = fetch_json(f"{API}/constants/patch")
    out = []
    for p in data:
        epoch = dt.datetime.fromisoformat(p["date"].replace("Z", "+00:00")).timestamp()
        out.append((epoch, p["name"]))
    out.sort(key=lambda x: x[0])
    return out


def patch_for(ts, patches):
    if not ts or not patches:
        return None
    name = None
    for epoch, nm in patches:
        if ts >= epoch:
            name = nm
        else:
            break
    return name


def process_match(detail, fallback_name, is_ti, patches=None):
    """Convert /matches/{id} response into a compact record. None if data is unusable."""
    pb = detail.get("picks_bans") or []
    picks = [x for x in pb if x.get("is_pick")]
    bans = [x for x in pb if not x.get("is_pick")]
    if len(picks) < 10:
        return None  # incomplete draft (not Captains Mode or missing data)

    hero_to_player = {}
    for p in (detail.get("players") or []):
        hid = p.get("hero_id")
        if hid:
            hero_to_player[hid] = p.get("name") or p.get("personaname") or "—"

    def side(t):
        return "radiant" if t == 0 else "dire"

    pick_list = [{
        "hero_id": x["hero_id"],
        "team": side(x["team"]),
        "order": x["order"],
        "player": hero_to_player.get(x["hero_id"], "—"),
    } for x in picks]

    ban_list = [{
        "hero_id": x["hero_id"],
        "team": side(x["team"]),
        "order": x["order"],
    } for x in bans if x.get("hero_id")]

    last = max(pick_list, key=lambda x: x["order"])

    ts = detail.get("start_time")
    year = dt.datetime.utcfromtimestamp(ts).year if ts else None

    league_name = (detail.get("league") or {}).get("name") or fallback_name

    return {
        "match_id": detail["match_id"],
        "year": year,
        "patch": patch_for(ts, patches),
        "league": league_name,
        "is_ti": is_ti,
        "radiant_team": detail.get("radiant_name") or "Radiant",
        "dire_team": detail.get("dire_name") or "Dire",
        "radiant_win": detail.get("radiant_win"),
        "start_time": ts,
        "duration": detail.get("duration"),
        "radiant_score": detail.get("radiant_score"),
        "dire_score": detail.get("dire_score"),
        "picks": pick_list,
        "bans": ban_list,
        "answer": {"hero_id": last["hero_id"], "team": last["team"]},
    }


def harvest(leagues, is_ti, per_league, delay, seen, out, patches):
    for leagueid, name in leagues.items():
        print(f"\n{name} (league {leagueid})...")
        try:
            lst = fetch_json(f"{API}/leagues/{leagueid}/matches")
        except RuntimeError as e:
            print(f"  skip league: {e}", file=sys.stderr)
            continue
        lst = sorted(lst, key=lambda m: m.get("start_time", 0), reverse=True)
        taken = 0
        for m in lst:
            if taken >= per_league:
                break
            mid = m["match_id"]
            if mid in seen:
                continue
            try:
                detail = fetch_json(f"{API}/matches/{mid}")
            except RuntimeError as e:
                print(f"  match {mid} skipped: {e}", file=sys.stderr)
                time.sleep(delay)
                continue
            rec = process_match(detail, name, is_ti, patches)
            time.sleep(delay)
            if rec is None:
                continue
            out.append(rec)
            seen.add(mid)
            taken += 1
            print(f"  [{taken}/{per_league}] {rec['year']} {rec['radiant_team']} vs {rec['dire_team']}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ti", type=int, default=50, help="matches per International (incl. group stage)")
    ap.add_argument("--other", type=int, default=22, help="matches per other tournament")
    ap.add_argument("--delay", type=float, default=0.9, help="pause between API calls (sec)")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    heroes = build_heroes()
    with open(os.path.join(DATA_DIR, "heroes.json"), "w", encoding="utf-8") as f:
        json.dump(heroes, f, ensure_ascii=False, indent=0)

    patches = load_patches()
    print(f"  patches loaded: {len(patches)} (latest: {patches[-1][1]})")

    matches, seen = [], set()
    harvest(INTERNATIONALS, True, args.ti, args.delay, seen, matches, patches)
    harvest(OTHER_LEAGUES, False, args.other, args.delay, seen, matches, patches)

    with open(os.path.join(DATA_DIR, "matches.json"), "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=0)

    leagues = sorted({m["league"] for m in matches})
    print(f"\nDone. Matches: {len(matches)}. Tournaments: {len(leagues)}")
    for lg in leagues:
        print("  -", lg, sum(1 for m in matches if m["league"] == lg))


if __name__ == "__main__":
    main()
