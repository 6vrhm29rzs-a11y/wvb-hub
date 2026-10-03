#!/usr/bin/env python3
"""LIVE-DISPLAY BACKUP SOURCE (mails 039/040, Cody: "we need backups for
events like this").

On 2026-09-27 the NCAA source itself (ncaa.com, and every endpoint derived
from it) held 24+ started matches at `pre` for over an hour while ESPN's
public scoreboard carried them in progress. The ncaa-api proxy is NOT an
independent backup -- it relays ncaa.com. ESPN is.

WHAT THIS MODULE MAY DO -- DISPLAY ONLY
  * Fill a match the NCAA feed still calls `pre` (or has emptied) with ESPN's
    in-progress or finished state, LABELLED as ESPN, with ESPN's fetch time.
  * Keep the last known backup score, marked stale, when both sources go
    quiet -- never revert a match that was seen in progress to "scheduled".
  * Flag a disagreement between two sources that each claim a state; it
    never averages, splices or picks a consensus that neither source said.

WHAT IT MAY NOT DO
  * Feed games.jsonl, the dataset, verification, the rating or POWER. The
    crawler reads the NCAA feed directly; nothing here is written to data/.
    An ESPN final is shown as "final per ESPN, NCAA not yet updated" and is
    counted nowhere until the NCAA record and the existing verification
    chain establish it.
  * Match a game on a guess. Identity needs BOTH teams resolved on the same
    ET date, in the same home/away orientation, to exactly ONE ESPN event.
    Anything else leaves the NCAA row untouched.

ACCESS -- MEASURED 2026-09-27, AND WHY THIS IS OFF BY DEFAULT.
ESPN's API answers generic clients (curl's and Python's default user agents)
but returns 403 to ANY self-identifying user agent (tested: "wvb-hub/0.1",
"research", "scoreboard backup", "1 req/min" -- all 403), and espn.com's
robots.txt disallows the `anthropic-ai` agent outright. Passing that filter
would mean presenting a generic identity specifically because our honest
one is refused -- evading an access control, which this project does not
do. So the adapter keeps an honest UA, records the refusal as a health
fact, and is DISABLED unless Cody decides otherwise (WVB_ESPN_FALLBACK=1).
When no backup is usable the page shows direct scoreboard links instead.
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ESPN_URL = ("https://site.api.espn.com/apis/site/v2/sports/volleyball/"
            "womens-college-volleyball/scoreboard?dates=%s&limit=400")
UA = "wvb-hub/0.1 (personal research project; live scoreboard backup, 1 req/min)"
STALE_AFTER = 20 * 60        # a backup reading older than this is shown as stale
MEMORY_HOLD = 3 * 3600       # how long a last-known in-progress score is kept

_health = {"ok_epoch": None, "fail_epoch": None, "fails": 0,
           "next_try": 0, "last_error": None, "events": 0}


def enabled():
    return os.environ.get("WVB_ESPN_FALLBACK", "0") == "1"


def health():
    return dict(_health)


def fetch(date_yyyymmdd, now=None, opener=None):
    """ESPN scoreboard for one ET date, or None. Backs off exponentially
    (60 s, 120 s ... capped at 15 min) after failures; never raises."""
    now = now or time.time()
    if now < _health["next_try"]:
        return None
    try:
        req = urllib.request.Request(ESPN_URL % date_yyyymmdd,
                                     headers={"User-Agent": UA})
        op = opener or urllib.request.urlopen
        with op(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        _health.update(ok_epoch=int(now), fails=0, next_try=0, last_error=None,
                       events=len(d.get("events") or []))
        return d
    except Exception as exc:                      # noqa: BLE001
        _health["fails"] += 1
        _health.update(fail_epoch=int(now), last_error=str(exc)[:160])
        _health["next_try"] = now + min(900, 60 * (2 ** (_health["fails"] - 1)))
        return None


def _names(team):
    out = []
    for k in ("location", "shortDisplayName", "displayName", "name"):
        v = (team or {}).get(k)
        if v and v not in out:
            out.append(v)
    return out


def parse(doc, fetched_epoch):
    """ESPN scoreboard JSON -> neutral event records."""
    out = []
    for e in (doc or {}).get("events") or []:
        comp = (e.get("competitions") or [{}])[0]
        st = (e.get("status") or {}).get("type") or {}
        sides = {}
        for c in comp.get("competitors") or []:
            lines = []
            for l in c.get("linescores") or []:
                try:
                    lines.append(int(float(l.get("value"))))
                except (TypeError, ValueError):
                    lines.append(None)
            try:
                tally = int(c.get("score"))
            except (TypeError, ValueError):
                tally = None
            sides[c.get("homeAway")] = {"names": _names(c.get("team")),
                                        "sets": tally, "lines": lines,
                                        "winner": bool(c.get("winner"))}
        if "home" not in sides or "away" not in sides:
            continue
        out.append({"id": str(e.get("id")), "state": st.get("state"),
                    "completed": bool(st.get("completed")),
                    "detail": st.get("shortDetail") or st.get("detail") or "",
                    "date": e.get("date"), "home": sides["home"],
                    "away": sides["away"], "fetched_epoch": int(fetched_epoch)})
    return out


def _key(name):
    import verify_results_daily as V
    return V._fold_key(V.team_norm(name or ""))


def _side_matches(ncaa_name, espn_names):
    k = _key(ncaa_name)
    return bool(k) and any(_key(n) == k for n in espn_names)


def identify(row, events):
    """The ONE ESPN event for this NCAA row, or None. Both teams must
    resolve, home to home and away to away; two candidates -> None."""
    hits = [e for e in events
            if _side_matches(row.get("home"), e["home"]["names"])
            and _side_matches(row.get("away"), e["away"]["names"])]
    return hits[0] if len(hits) == 1 else None


def _pairs(ev):
    a, h = ev["away"]["lines"], ev["home"]["lines"]
    n = min(len(a), len(h))
    out = []
    for i in range(n):
        if a[i] is None or h[i] is None:
            break
        out.append([a[i], h[i]])
    # ESPN lists a set not yet begun as 0-0 after the current one; drop
    # trailing all-zero pairs unless the match is in progress and it is the
    # only set (0-0 at first serve is a real state).
    while len(out) > 1 and out[-1] == [0, 0]:
        out.pop()
    return out


def _ordinal(n):
    return {1: "1ST", 2: "2ND", 3: "3RD", 4: "4TH", 5: "5TH"}.get(n, "%dTH" % n)


def _ncaa_claims_state(row):
    s = (row.get("state") or "").lower()
    return s not in ("pre", "p", "")


def merge(row, ev, memory, now=None):
    """Apply the backup to ONE NCAA row. Returns the label applied, or None.
    `memory` is a dict gid -> last backup reading, owned by the caller."""
    now = now or time.time()
    gid = str(row.get("id"))
    row["primary_state"] = row.get("state")
    if ev is None:
        # no backup for this match right now: keep a remembered in-progress
        # reading rather than let an NCAA 'pre' erase it -- labelled stale
        m = memory.get(gid)
        if m and not _ncaa_claims_state(row) and now - m["fetched_epoch"] < MEMORY_HOLD:
            _apply(row, m, stale=True, now=now)
            return "espn_last_known"
        return None
    if ev["state"] == "pre":
        return None
    reading = {"state": ev["state"], "completed": ev["completed"],
               "detail": ev["detail"], "pairs": _pairs(ev),
               "away_sets": ev["away"]["sets"], "home_sets": ev["home"]["sets"],
               "fetched_epoch": ev["fetched_epoch"], "espn_id": ev["id"]}
    if _ncaa_claims_state(row):
        # both sources claim a state: the primary stays; a disagreement is
        # SAID, never resolved by averaging or by picking one
        try:
            na, nh = int(row.get("away_sets") or 0), int(row.get("home_sets") or 0)
        except (TypeError, ValueError):
            na = nh = None
        ncaa_final = (row.get("state") or "").lower() in ("final", "f")
        if ncaa_final and ev["completed"] and (na, nh) != (reading["away_sets"], reading["home_sets"]):
            row["source_conflict"] = ("ESPN final %s-%s vs NCAA final %s-%s -- "
                                      "neither overwrites the other; the verified "
                                      "result chain decides" % (
                                          reading["away_sets"], reading["home_sets"], na, nh))
            return "conflict"
        # RECOVERY ONLY WHEN CONSISTENT: a primary that has come back but is
        # BEHIND the backup (fewer sets played) is lagging, not recovered --
        # switching to it would move the score backwards on screen.
        n_pairs = len(row.get("sets") or [])
        played_n = (na or 0) + (nh or 0) if na is not None else 0
        if (not ncaa_final and reading["pairs"]
                and (len(reading["pairs"]) > max(n_pairs, played_n + 1)
                     or ev["completed"])):
            memory[gid] = reading
            _apply(row, reading, stale=False, now=now)
            row["source_note"] += " (NCAA feed has resumed but is behind)"
            return "espn_ahead_of_primary"
        memory.pop(gid, None)
        return None
    # NCAA says pre (or has nothing): the backup carries the display
    prev = memory.get(gid)
    if prev and prev.get("completed") and not reading["completed"]:
        return _apply(row, prev, stale=False, now=now) or "espn_final_held"
    memory[gid] = reading
    _apply(row, reading, stale=False, now=now)
    return "espn"


def _apply(row, r, stale, now):
    row["state"] = "final" if r["completed"] else "live"
    row["period"] = "FINAL" if r["completed"] else (
        _ordinal(len(r["pairs"])) + " SET" if r["pairs"] else r["detail"])
    row["sets"] = r["pairs"]
    if r["away_sets"] is not None:
        row["away_sets"] = str(r["away_sets"])
    if r["home_sets"] is not None:
        row["home_sets"] = str(r["home_sets"])
    age = int(now - r["fetched_epoch"])
    row["source"] = "ESPN"
    row["source_fetched_epoch"] = r["fetched_epoch"]
    row["source_stale"] = bool(stale or age > STALE_AFTER)
    row["source_note"] = (
        ("ESPN %s, fetched %d min ago; NCAA feed still lists it as not started"
         % ("final (provisional -- not a counted result)" if r["completed"] else "live score",
            age // 60))
        + (" -- LAST KNOWN, backup has not refreshed" if row["source_stale"] else ""))
    return None
