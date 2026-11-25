#!/usr/bin/env python3
"""Bind real conference-tournament matches to their leagues (Cody, 2026-11-22).

The tournament view had an empty results ledger, so finished tournaments were still shown as projections
and their finals were counted as regular-season conference results. Evidence used here, all of which must agree:

  1. NCAA.com's "Tracking all 32 automatic qualifiers" table: which leagues hold a tournament, the round
     dates, the site and the bids decided so far. Each change is appended to data/raw/2026/aq_tracker.jsonl.
  2. The counted feed: same-conference matches inside the league's sourced tournament window.
  3. STRUCTURE: a tournament is single elimination, so no team may lose twice or play after losing, and a
     decided league's last team standing must be the team NCAA.com names. A league failing any check is
     reported and binds NOTHING.

A window match alone is never treated as tournament evidence. If the tracker cannot be fetched, the last
stored capture is used. Writes conf_tournament_results.json (new rows only) and the derived
data/conf_tournament_observed_2026.json.
"""
import datetime, hashlib, html, json, os, re, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
import season_counts as SC
from reconcile_2025 import norm

RAW = os.path.join(REPO, "data", "raw", "2026")
TRACKER_URL = ("https://www.ncaa.com/news/volleyball-women/article/2026-11-21/"
               "tracking-all-32-automatic-qualifiers-2026-womens-volleyball-tournament")
SNAP = os.path.join(RAW, "aq_tracker.jsonl")
LEDGER = os.path.join(RAW, "conf_tournament_results.json")
CFG = os.path.join(RAW, "conf_tournaments_2026.json")
OUT = os.path.join(REPO, "data", "conf_tournament_observed_2026.json")

# NCAA.com's league label -> our config key
LABELS = {"Atlantic Sun": "ASUN", "Conference USA": "CUSA", "Horizon League": "Horizon", "The Metro": "MAAC",
          "Missouri Valley": "MVC", "Ohio Valley": "OVC", "Patriot League": "Patriot", "PAC-12": "Pac-12"}
# the tracker's short school names that differ from the hub's
WINNER_ALIASES = {"fdu": "fairleigh dickinson", "western kentucky": "western ky", "eastern kentucky": "eastern ky",
                  "incarnate word": "uiw", "georgia southern": "ga southern"}


def _key(name):
    k = norm(name or "")
    k = norm(WINNER_ALIASES.get(k, k))
    return re.sub(r"\bstate$", "st", k)              # NCAA.com writes "Wright State", the hub "Wright St."


def same_team(a, b):
    """The tracker's spelling and ours name one school: the alias key, or the shared outside-source normaliser
    (external_refs._ref_norm, which folds state names: "Southeast Missouri State" is "Southeast Mo. St.")."""
    if _key(a) == _key(b):
        return True
    import external_refs as _X
    return _X._ref_norm(a or "") == _X._ref_norm(b or "")


def parse_tracker(page):
    """{config key: {winner, schedule, location}} from the article's one table."""
    tables = re.findall(r"<table.*?</table>", page, flags=re.S)
    if not tables:
        return {}
    out = {}
    for row in re.findall(r"<tr.*?</tr>", tables[0], flags=re.S)[1:]:
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<td.*?</td>", row, flags=re.S)]
        if len(cells) < 4:
            continue
        winner = cells[1] if cells[1] not in ("-", "–", "") else None
        out[LABELS.get(cells[0], cells[0])] = {"winner": winner, "schedule": cells[2], "location": cells[3]}
    return out


def load_tracker():
    """Fetch, append when changed, and fall back to the last stored capture."""
    rows = []
    if os.path.exists(SNAP):
        rows = [json.loads(l) for l in open(SNAP, encoding="utf-8") if l.strip()]
    try:
        req = urllib.request.Request(TRACKER_URL, headers={"User-Agent": "Mozilla/5.0 (personal-stats-hub)"})
        page = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
        parsed = parse_tracker(page)
        if len(parsed) < 30:
            raise ValueError("tracker table parsed to %d leagues" % len(parsed))
    except Exception as exc:
        if not rows:
            raise
        print("tracker fetch failed (%s); using capture of %s" % (exc, rows[-1]["retrieved_utc"]))
        return rows[-1]
    digest = hashlib.sha256(json.dumps(parsed, sort_keys=True).encode()).hexdigest()
    if rows and rows[-1].get("sha256") == digest:
        return rows[-1]
    rec = {"retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": TRACKER_URL,
           "sha256": digest, "leagues": parsed}
    with open(SNAP, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def et_date(epoch):
    return time.strftime("%Y-%m-%d", time.gmtime(int(epoch) - 5 * 3600))


def league_matches(doc, finals, members, lo, hi):
    """Same-league matches in the window: counted finals plus scheduled/live fixtures."""
    out, seen = [], set()
    for g in doc.get("games") or []:
        ts = g.get("teams") or []
        if len(ts) != 2 or not g.get("start_time_epoch"):
            continue
        a, b = ts[0].get("name_short"), ts[1].get("name_short")
        if norm(a) not in members or norm(b) not in members:
            continue
        d = et_date(g["start_time_epoch"])
        if not lo <= d <= hi:
            continue
        gid, state = str(g["game_id"]), g.get("state")
        winner = None
        if state == "F":
            if gid not in finals or SC.winner_index(finals[gid]) is None:
                continue                                    # not counted (duplicate, held, exhibition)
            winner = (a, b)[SC.winner_index(finals[gid])]
            sw = [t.get("sets_won") for t in finals[gid]["teams"]]
        else:
            sw = None
        pair = (d, frozenset((norm(a), norm(b))))
        if pair in seen:
            continue
        seen.add(pair)
        out.append({"game_id": gid, "date": d, "epoch": int(g["start_time_epoch"]), "a": a, "b": b,
                    "winner": winner, "state": state, "sets": sw})
    # the crawled log holds a fixture only near its date; the stored scoreboard lists the next rounds earlier
    day, stop = datetime.date.fromisoformat(lo), datetime.date.fromisoformat(hi)
    while day <= stop:
        pth = os.path.join(RAW, "scoreboard", "%s.json" % day.isoformat())
        day += datetime.timedelta(days=1)
        if not os.path.exists(pth):
            continue
        for row in json.load(open(pth, encoding="utf-8")).get("games") or []:
            g = row.get("game") or {}
            state = {"pre": "P", "live": "I"}.get(g.get("gameState"))
            a, b = ((g.get("away") or {}).get("names") or {}).get("short"), ((g.get("home") or {}).get("names") or {}).get("short")
            if not state or not g.get("startTimeEpoch") or norm(a) not in members or norm(b) not in members:
                continue
            d = et_date(g["startTimeEpoch"])
            pair = (d, frozenset((norm(a), norm(b))))
            if not lo <= d <= hi or pair in seen:
                continue
            seen.add(pair)
            out.append({"game_id": str(g["gameID"]), "date": d, "epoch": int(g["startTimeEpoch"]), "a": a, "b": b,
                        "winner": None, "state": state, "sets": None})
    return sorted(out, key=lambda m: (m["epoch"], m["game_id"]))


def check_structure(ms):
    """Single elimination: nobody loses twice, nobody plays after losing. Returns a list of violations."""
    lost, bad = {}, []
    for m in ms:
        for t in (m["a"], m["b"]):
            if t in lost and m["epoch"] > lost[t]:
                bad.append("%s plays on %s after being eliminated" % (t, m["date"]))
        if m["winner"]:
            l = m["b"] if m["winner"] == m["a"] else m["a"]
            if l in lost:
                bad.append("%s lost twice" % l)
            lost[l] = m["epoch"]
    return bad


def add_rounds(ms):
    """Round = 1 + the deeper of the two teams' previous rounds (a bye team enters at its first match)."""
    depth = {}
    for m in ms:
        m["round"] = max(depth.get(m["a"], -1), depth.get(m["b"], -1)) + 1
        depth[m["a"]] = depth[m["b"]] = m["round"]


def main():
    tracker = load_tracker()
    cfg = json.load(open(CFG))["conferences"]
    doc = json.load(open(os.path.join(REPO, "data", "data_2026.json")))
    polls = open(os.path.join(RAW, "polls_rpi.jsonl"), encoding="utf-8").read().splitlines()
    conf_rows = json.loads(polls[-1])["rows"]
    alias = {"Metro": "MAAC"}
    members = {}
    for r in conf_rows:
        members.setdefault(alias.get(r.get("Conf"), r.get("Conf")), set()).add(norm(r["School"]))
    led = json.load(open(LEDGER))
    have_r = set(str(x.get("game_id")) for x in led.get("results") or [])
    have_s = set(str(x.get("game_id")) for x in led.get("scheduled_fixtures") or [])
    led.setdefault("results", []); led.setdefault("scheduled_fixtures", [])
    leagues, failed, added_r, added_s = {}, {}, 0, 0
    finals_by_id = dict((str(g["game_id"]), g) for g in SC.countable(doc.get("games") or [], 2026, need_line=False, d1_only=False))
    for name, row in sorted(cfg.items()):
        tr = tracker["leagues"].get(name)
        if not tr or tr["schedule"] == "N/A" or name not in members or not row.get("window"):
            failed[name] = "not matched to the NCAA tracker or a member list"
            continue
        # the NCAA's first listed round can precede our stored window (America East played Nov. 19)
        days = [int(x) for x in re.findall(r"Nov\.?\s*(\d{1,2})", tr["schedule"])]
        lo = min([row["window"][0]] + (["2026-11-%02d" % min(days)] if days else []))
        ms = league_matches(doc, finals_by_id, members[name], lo, row["window"][1])
        problems = check_structure(ms)
        add_rounds(ms)
        finals = [m for m in ms if m["winner"]]
        losers = set((m["b"] if m["winner"] == m["a"] else m["a"]) for m in finals)
        teams = set(t for m in ms for t in (m["a"], m["b"]))
        # past the first round every team still in it has appeared, so the observed field is the real one
        # (MVC's stored format said 8; six teams played). Before that, byes are unseen: keep the sourced size.
        past_first = any(m["round"] >= 1 for m in ms)
        field = len(teams) if past_first else max(row["field"], len(teams))
        alive = sorted(teams - losers)
        champion = alive[0] if len(finals) == field - 1 and len(alive) == 1 else None
        awaiting_feed = False
        if tr.get("winner"):
            named = [t for t in teams if same_team(t, tr["winner"])]
            if not named:
                problems.append("NCAA names %s, who is not in the observed tournament" % tr["winner"])
            elif champion and champion != named[0]:
                problems.append("NCAA names %s, the bracket ends with %s" % (named[0], champion))
            elif not champion:
                # NCAA.com can post a champion before our crawl stores that final. Accept it only when the
                # one open match is the final and the named team is playing in it.
                still = [m for m in ms if not m["winner"]]
                if len(alive) == 2 and len(still) == 1 and named[0] in (still[0]["a"], still[0]["b"]):
                    champion, awaiting_feed = named[0], True
                else:
                    problems.append("NCAA names %s but the observed bracket is not finished" % named[0])
        if problems:
            failed[name] = "; ".join(problems)
            continue
        for m in ms:
            if m["winner"] and m["game_id"] not in have_r:
                led["results"].append({"conf": name, "round": m["round"], "teams": [m["a"], m["b"]],
                                       "winner": m["winner"], "game_id": m["game_id"], "date": m["date"],
                                       "source": TRACKER_URL, "basis": "NCAA tracker round window + single-elimination check"})
                have_r.add(m["game_id"]); added_r += 1
            elif not m["winner"] and m["game_id"] not in have_s:
                led["scheduled_fixtures"].append({"conf": name, "teams": [m["a"], m["b"]], "game_id": m["game_id"],
                                                  "date": m["date"], "source": TRACKER_URL})
                have_s.add(m["game_id"]); added_s += 1
        leagues[name] = {"matches": ms, "alive": alive, "champion": champion, "field": field, "awaiting_feed": awaiting_feed,
                         "ncaa_winner": tr.get("winner"), "schedule": tr["schedule"], "location": tr["location"]}
    tmp = LEDGER + ".tmp"
    json.dump(led, open(tmp, "w"), indent=1)
    os.replace(tmp, LEDGER)
    tmp = OUT + ".tmp"
    json.dump({"meta": {"tracker_retrieved_utc": tracker["retrieved_utc"], "source": TRACKER_URL},
               "leagues": leagues, "failed": failed}, open(tmp, "w"), indent=1)
    os.replace(tmp, OUT)
    print("conference tournaments: %d leagues bound, %d champions, +%d results, +%d fixtures"
          % (len(leagues), sum(1 for v in leagues.values() if v["champion"]), added_r, added_s))
    for k, v in sorted(failed.items()):
        print("  NOT BOUND %s: %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
