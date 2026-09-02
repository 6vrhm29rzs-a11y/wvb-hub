#!/usr/bin/env python3
"""Nightly result verification against the schools' own published schedules.

Cody's directive (2026-09-01, after the third feed attribution inversion):
"each night, scores/wins should be verified against official team websites
and not rely solely on the ncaa site." Design refined with an external
review the same evening (docs/trust_layer_consult_2026-09-01.md).

WHAT IT DOES: for each of the day's counted D-I finals, fetch BOTH schools'
published schedule (SIDEARM's /schedule/text surface first -- a structured
page carrying "W 3-1"-style results and an explicit Home/Away/Neutral
column), find the row for this match by OPPONENT IDENTITY on the date
(never "first event of the date" -- doubleheaders), and compare
winner + set count against our canonical record.

WHAT IT NEVER DOES: correct anything. Two schools agreeing against the feed
produces a loud REVIEW CANDIDATE in data/raw/2026/result_review_queue.json
with both citations; a human files the correction ledger entry. One school
agreeing is corroboration, not verification. "Not posted yet" is NOT
disagreement -- schools post final results minutes to hours after the whistle.

Per-school states: AGREE_COMPLETE / AGREE_PARTIAL / CONTRADICTS /
NOT_POSTED / EVENT_NOT_FOUND / SITE_UNREACHABLE / SITE_UNPARSED.
Match verdicts: VERIFIED_BOTH / CORROBORATED_ONE / UNVERIFIED /
CONTRADICTED_BOTH / SCHOOL_CONFLICT / CONTRADICTED_ONE.

Every fetch attempt -- success, block, miss -- is appended to
data/raw/2026/result_verification_log.jsonl. Append-only, like every raw log.
"""
import datetime
import html as _html
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_counts as SC                                   # noqa: E402
from reconcile_2025 import norm as team_norm                 # noqa: E402

SEASON = 2026
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
UA = ("wvb-hub result verifier (personal research project; "
      "~2 requests per school per night)")
SPORT_PATHS = [
    "/sports/womens-volleyball/schedule/text",
    "/sports/volleyball/schedule/text",       # no men's program (Nebraska)
    "/sports/wvball/schedule/text",           # WMT naming (Kentucky)
    "/sports/wvb/schedule/text",              # short code (LSU)
]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _sites():
    sites = json.load(open(os.path.join(RAW, "athletics_sites.json")))
    ov = json.load(open(os.path.join(RAW, "athletics_sites_overrides.json")))
    out = {}
    for team, rec in sites.items():
        u = (rec or {}).get("url")
        if u:
            out[team] = u.rstrip("/")
    for team, u in (ov.get("teams") or {}).items():
        out[team] = u.rstrip("/")
    return out


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:                                    # noqa: BLE001
        return None, str(e)[:120]


def _cells(row_html):
    return [_html.unescape(re.sub(r"<[^>]+>", " ", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>",
                                row_html, re.S | re.I)]


def parse_schedule_text(page, season=SEASON):
    """SIDEARM /schedule/text -> normalized rows.

    Columns observed: Date | Time | At | Opponent | Location [| Tournament]
    | Result. The result is wherever a "W 3-1" / "L 0-3" token sits -- the
    column count varies by school, so the row is scanned for the token
    rather than trusting a position.
    """
    rows = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = _cells(m.group(1))
        if len(cells) < 4:
            continue
        dm = re.match(r"([A-Z][a-z]{2})\.?\s+(\d{1,2})", cells[0])
        if not dm or dm.group(1) not in MONTHS:
            continue
        mo = MONTHS[dm.group(1)]
        # Aug-Dec belong to the season year; Jan+ would be the next
        year = season if mo >= 8 else season + 1
        date = "%04d-%02d-%02d" % (year, mo, int(dm.group(2)))
        site = next((c for c in cells[1:4]
                     if c in ("Home", "Away", "Neutral")), None)
        # the opponent is the cell after the site column, rank prefix
        # stripped; "(Exh.)" is a marker, not part of the name
        try:
            opp_raw = cells[cells.index(site) + 1] if site else cells[3]
        except (ValueError, IndexError):
            continue
        exh = "(Exh.)" in opp_raw or "Exhibition" in opp_raw
        # rank prefixes come in three spellings: "#7 ", "No. 7 ", and "RV "
        # (receiving votes -- found live on Louisville's page, where the
        # opponent read "RV Dayton" and the row went unmatched)
        opp = re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "",
                     opp_raw.replace("(Exh.)", "")).strip()
        res = None
        for c in cells:
            rm = re.fullmatch(r"([WL])[,\s]+(\d)\s*-\s*(\d)", c.strip())
            if rm:
                res = (rm.group(1), int(rm.group(2)), int(rm.group(3)))
        rows.append({"date": date, "site": site, "opponent": opp,
                     "exhibition": exh, "result": res, "raw": cells})
    return rows


def school_evidence(team, opponent, date, canonical, sites, log):
    """One school's published word on one match. Returns (state, detail)."""
    base = sites.get(team)
    if not base:
        return "SITE_UNREACHABLE", {"why": "no athletics site on file"}
    for path in SPORT_PATHS:
        url = base + path
        status, body = _fetch(url)
        time.sleep(0.5)
        entry = {"team": team, "url": url, "http": status,
                 "retrieved_utc": datetime.datetime.utcnow()
                 .strftime("%Y-%m-%dT%H:%M:%SZ")}
        if status != 200 or "chedule" not in body:
            entry["state"] = "miss"
            log.append(entry)
            continue
        rows = parse_schedule_text(body)
        if not rows:
            entry["state"] = "unparsed"
            log.append(entry)
            return "SITE_UNPARSED", {"url": url}
        # ⚠ OPPONENT IDENTITY DOMINATES THE DATE: a tournament day can hold
        # two matches, and "first row of the date" is how the wrong match
        # gets verified. R8's lesson, applied to scraping.
        want = team_norm(opponent)
        cand = [r for r in rows if r["date"] == date
                and team_norm(r["opponent"]) == want
                and not r["exhibition"]]
        if not cand:
            entry["state"] = "event_not_found"
            log.append(entry)
            return "EVENT_NOT_FOUND", {"url": url, "rows_on_date": [
                r["opponent"] for r in rows if r["date"] == date]}
        r = cand[0]
        entry["state"] = "row_found"
        entry["assertion"] = " | ".join(r["raw"])[:200]
        log.append(entry)
        if not r["result"]:
            return "NOT_POSTED", {"url": url, "row": r["raw"]}
        wl, a, b = r["result"]
        won = wl == "W"
        # canonical: did `team` win, and with what set counts?
        c_won = canonical["winner"] == team
        c_sets = (canonical["w_sets"], canonical["l_sets"]) if c_won \
            else (canonical["l_sets"], canonical["w_sets"])
        agree_w = won == c_won
        agree_s = (a, b) == c_sets
        det = {"url": url, "assertion": "%s %s %d-%d vs %s"
               % (team, wl, a, b, r["opponent"]),
               "site_says": r["site"]}
        if agree_w and agree_s:
            return "AGREE_COMPLETE", det
        if agree_w:
            return "AGREE_PARTIAL", det
        return "CONTRADICTS", det
    return "SITE_UNREACHABLE", {"why": "no schedule surface answered"}


def verdict(sa, sb):
    ag = {"AGREE_COMPLETE", "AGREE_PARTIAL"}
    if sa in ag and sb in ag:
        return "VERIFIED_BOTH"
    if sa == "CONTRADICTS" and sb == "CONTRADICTS":
        return "CONTRADICTED_BOTH"
    if "CONTRADICTS" in (sa, sb) and (sa in ag or sb in ag):
        return "SCHOOL_CONFLICT"
    if "CONTRADICTS" in (sa, sb):
        return "CONTRADICTED_ONE"
    if sa in ag or sb in ag:
        return "CORROBORATED_ONE"
    return "UNVERIFIED"


def finals_for(date):
    games = []
    with open(os.path.join(RAW, "games.jsonl")) as f:
        for line in f:
            try:
                games.append(json.loads(line))
            except ValueError:
                continue
    out = []
    cls_of = SC.classify(games, SEASON)
    for g in SC.resolve(games):
        if cls_of.get(str(g.get("game_id"))) != "ok":
            continue
        et = g.get("start_time_epoch")
        if not et:
            continue
        d = (datetime.datetime.fromtimestamp(et, datetime.timezone.utc)
             - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")
        if d != date:
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        w = next((t for t in ts if t.get("is_winner")), None)
        l = next((t for t in ts if not t.get("is_winner")), None)
        if not w or not l:
            continue
        out.append({"gid": str(g.get("game_id")),
                    "winner": w.get("name_short"),
                    "loser": l.get("name_short"),
                    "w_sets": w.get("sets_won"),
                    "l_sets": l.get("sets_won")})
    return out


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")
    sites = _sites()
    finals = finals_for(date)
    print("verifying %d counted finals for %s against both schools' "
          "published schedules" % (len(finals), date))
    log, report, queue_adds = [], [], []
    for f in finals:
        sa, da = school_evidence(f["winner"], f["loser"], date, f, sites, log)
        sb, db = school_evidence(f["loser"], f["winner"], date, f, sites, log)
        v = verdict(sa, sb)
        row = {"gid": f["gid"], "date": date,
               "canonical": "%s def. %s %d-%d" % (
                   f["winner"], f["loser"], f["w_sets"], f["l_sets"]),
               "verdict": v,
               "schools": {f["winner"]: {"state": sa, **da},
                           f["loser"]: {"state": sb, **db}}}
        report.append(row)
        if v in ("CONTRADICTED_BOTH", "CONTRADICTED_ONE", "SCHOOL_CONFLICT"):
            queue_adds.append(row)
        print("  %-22s %s" % (v, row["canonical"]))

    # append-only fetch log
    with open(os.path.join(RAW, "result_verification_log.jsonl"), "a") as f:
        for e in log:
            f.write(json.dumps(e) + "\n")
    # the day's report (rewritten per run -- it is derived, the log is raw)
    outp = os.path.join(REPO, "data", "result_verification_%s.json" % date)
    counts = {}
    for r in report:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    json.dump({"date": date, "generated_utc": datetime.datetime.utcnow()
               .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "counts": counts, "matches": report},
              open(outp, "w"), indent=1)
    print("report: %s  %s" % (outp, counts))

    # review candidates -- NEVER corrections. Merged, never overwritten.
    if queue_adds:
        qp = os.path.join(RAW, "result_review_queue.json")
        q = json.load(open(qp)) if os.path.exists(qp) else {}
        for row in queue_adds:
            q.setdefault(row["gid"], row)
        json.dump(q, open(qp, "w"), indent=1)
        print("⚠ %d REVIEW CANDIDATE(S) written to %s -- a human files any "
              "correction" % (len(queue_adds), qp))


if __name__ == "__main__":
    main()
