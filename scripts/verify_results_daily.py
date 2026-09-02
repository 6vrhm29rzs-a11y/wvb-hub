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

Per-school states: AGREE_COMPLETE / CONTRADICTS_SETS (winner agrees, set
count does not -- a contradiction, never an agreement) / CONTRADICTS /
NOT_POSTED / EVENT_NOT_FOUND / SITE_UNPARSED / SITE_BLOCKED /
SITE_HTTP_MISS / SITE_NETWORK_ERROR / SITE_NOT_CONFIGURED.
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


def parse_sidearm_date(cell):
    """'Sep 1 (Tue)' / 'Sept. 1' / 'September 1' -> (month, day) or
    (None, None). Speculative formats are NOT added -- unrecognised
    event-like cells are for the log to surface, and live failures grow
    the parser (review consult, 2026-09-01)."""
    m = re.match(r"([A-Z][a-z]+)\.?\s+(\d{1,2})", cell.strip())
    if not m:
        return None, None
    name = m.group(1)[:3]
    if m.group(1).startswith("Sept"):
        name = "Sep"
    if name not in MONTHS:
        return None, None
    return MONTHS[name], int(m.group(2))


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
    """-> (status, body, final_url). urlopen follows redirects SILENTLY, so
    the final URL is part of the evidence -- /schedule/text 302ing to the JS
    /schedule page is exactly how SITE_UNPARSED happens (review consult,
    2026-09-01)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:                                    # noqa: BLE001
        return None, str(e)[:120], url


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
        mo, day = parse_sidearm_date(cells[0])
        if not mo:
            continue
        # Aug-Dec belong to the season year; Jan+ would be the next
        year = season if mo >= 8 else season + 1
        date = "%04d-%02d-%02d" % (year, mo, day)
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


def parse_schedule_txt_plain(body, season=SEASON):
    """The legacy SIDEARM /services/schedule_txt.ashx plain-text export --
    the fallback for schools whose /schedule/text redirects to the JS page.
    Fixed-width columns, sliced by the header row's own offsets (measured on
    daytonflyers.com): Date / Time / At / Opponent / Location / Tournament /
    Result."""
    lines = body.splitlines()
    hdr = next((i for i, l in enumerate(lines)
                if l.strip().startswith("Date") and "Opponent" in l), None)
    if hdr is None:
        return []
    h = lines[hdr]
    cols = ["Date", "Time", "At", "Opponent", "Location", "Tournament",
            "Result"]
    starts = []
    for c in cols:
        j = h.find(c)
        if j < 0:
            return []
        starts.append(j)
    rows = []
    for l in lines[hdr + 1:]:
        if not l.strip():
            continue
        cells = {}
        for k, c in enumerate(cols):
            end = starts[k + 1] if k + 1 < len(cols) else len(l)
            cells[c] = l[starts[k]:end].strip()
        mo, day = parse_sidearm_date(cells["Date"])
        if not mo:
            continue
        year = season if mo >= 8 else season + 1
        opp_raw = cells["Opponent"]
        # ⚠ a hosted-tournament row names two OTHER teams ("Santa Clara vs.
        # Eastern Illinois" on Dayton's page) -- the school is not playing
        # in it and it must never match
        if " vs. " in opp_raw:
            continue
        exh = "(Exh.)" in opp_raw or "Exhibition" in opp_raw
        opp = re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "",
                     opp_raw.replace("(Exh.)", "")).strip()
        res = None
        rm = re.match(r"([WL])[,\s]+(\d)\s*-\s*(\d)", cells["Result"])
        if rm:
            res = (rm.group(1), int(rm.group(2)), int(rm.group(3)))
        rows.append({"date": "%04d-%02d-%02d" % (year, mo, day),
                     "site": cells["At"] if cells["At"] in
                     ("Home", "Away", "Neutral") else None,
                     "opponent": opp, "exhibition": exh, "result": res,
                     "raw": [cells[c] for c in cols]})
    return rows


def legacy_txt_rows(base, log, team):
    """Find the schedule_txt.ashx link on the vendor schedule page and parse
    its plain-text export. Returns (rows, url) or (None, None)."""
    for sport in ("womens-volleyball", "volleyball", "wvball", "wvb"):
        url = base + "/sports/%s/schedule" % sport
        status, body, _fu = _fetch(url)
        time.sleep(0.5)
        if status != 200 or not body:
            continue
        m = re.search(r"/services/schedule_txt\.ashx\?schedule=\d+", body)
        if not m:
            continue
        turl = base + m.group(0)
        status2, txt, _fu2 = _fetch(turl)
        time.sleep(0.5)
        log.append({"team": team, "url": turl, "http": status2,
                    "retrieved_utc": datetime.datetime.utcnow()
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "state": "legacy_txt"})
        if status2 == 200 and txt:
            rows = parse_schedule_txt_plain(txt)
            if rows:
                return rows, turl
    return None, None


def _judge_rows(rows, url, team, opponent, date, canonical):
    """Match the row and compare it to the canonical result.

    ⚠ OPPONENT IDENTITY DOMINATES THE DATE: a tournament day can hold two
    matches, and "first row of the date" is how the wrong match gets
    verified. R8's lesson, applied to scraping."""
    want = team_norm(opponent)
    cand = [r for r in rows if r["date"] == date
            and team_norm(r["opponent"]) == want
            and not r["exhibition"]]
    if not cand:
        return "EVENT_NOT_FOUND", {"url": url, "rows_on_date": [
            r["opponent"] for r in rows if r["date"] == date]}
    r = cand[0]
    if not r["result"]:
        return "NOT_POSTED", {"url": url, "row": r["raw"]}
    wl, a, b = r["result"]
    won = wl == "W"
    c_won = canonical["winner"] == team
    c_sets = (canonical["w_sets"], canonical["l_sets"]) if c_won \
        else (canonical["l_sets"], canonical["w_sets"])
    det = {"url": url, "assertion": "%s %s %d-%d vs %s"
           % (team, wl, a, b, r["opponent"]),
           "site_says": r["site"]}
    if won == c_won and (a, b) == c_sets:
        return "AGREE_COMPLETE", det
    if won == c_won:
        # ⚠ NOT "partial agreement" (review consult, 2026-09-01): the school
        # agrees on the winner but CONTRADICTS our set count. Two schools in
        # this state means two official sources say the feed's score line is
        # wrong -- that must surface as a review candidate, never verify.
        return "CONTRADICTS_SETS", det
    return "CONTRADICTS", det


def school_evidence(team, opponent, date, canonical, sites, log):
    """One school's published word on one match. Returns (state, detail)."""
    base = sites.get(team)
    if not base:
        return "SITE_NOT_CONFIGURED", {"why": "no athletics site on file"}
    # ⚠ A SURFACE FAILURE IS AN OBSERVATION, NOT A VERDICT (review consult,
    # 2026-09-01): the old ladder returned SITE_UNPARSED / EVENT_NOT_FOUND
    # from the FIRST surface that half-answered, so a school whose text page
    # was a JS shell never reached the legacy export. Every surface is
    # tried; the best observation wins, and only a judged row short-circuits.
    best = ("SITE_UNREACHABLE", {"why": "no schedule surface answered"})
    rank = {"SITE_UNREACHABLE": 0, "SITE_HTTP_MISS": 1, "SITE_BLOCKED": 1,
            "SITE_NETWORK_ERROR": 1, "SITE_UNPARSED": 2,
            "EVENT_NOT_FOUND": 3, "NOT_POSTED": 4}
    def better(st, det):
        nonlocal_best = rank.get(st, 0) > rank.get(best[0], 0)
        return (st, det) if nonlocal_best else best
    for path in SPORT_PATHS:
        url = base + path
        status, body, final_url = _fetch(url)
        time.sleep(0.5)
        entry = {"team": team, "url": url, "http": status,
                 "retrieved_utc": datetime.datetime.utcnow()
                 .strftime("%Y-%m-%dT%H:%M:%SZ")}
        if final_url != url:
            entry["final_url"] = final_url
            entry["redirected"] = True
        if status is None:
            entry["state"] = "network_error"
            log.append(entry)
            best = better("SITE_NETWORK_ERROR", {"url": url, "why": body})
            continue
        if status in (401, 403, 429):
            entry["state"] = "blocked"
            log.append(entry)
            best = better("SITE_BLOCKED", {"url": url, "http": status})
            continue
        if status != 200:
            entry["state"] = "miss"
            log.append(entry)
            best = better("SITE_HTTP_MISS", {"url": url, "http": status})
            continue
        # ⚠ "the word schedule appears somewhere" is not a schedule surface
        # -- a branded 404 or the JS shell both contain it. The evidence is
        # successful row extraction, nothing weaker.
        rows = parse_schedule_text(body)
        if not rows:
            entry["state"] = "unparsed"
            log.append(entry)
            best = better("SITE_UNPARSED", {"url": final_url})
            continue
        entry["state"] = "parsed"
        log.append(entry)
        st, det = _judge_rows(rows, url, team, opponent, date, canonical)
        if st in ("AGREE_COMPLETE", "CONTRADICTS", "CONTRADICTS_SETS",
                  "NOT_POSTED"):
            return st, det
        best = better(st, det)
    # the legacy plain-text export -- reached even when every path above
    # produced only observations
    rows2, turl = legacy_txt_rows(base, log, team)
    if rows2:
        st, det = _judge_rows(rows2, turl, team, opponent, date, canonical)
        if st in ("AGREE_COMPLETE", "CONTRADICTS", "CONTRADICTS_SETS",
                  "NOT_POSTED"):
            return st, det
        best = better(st, det)
    return best


def verdict(sa, sb):
    """Only complete agreement verifies. A set-count disagreement is a
    contradiction of the canonical record -- two schools in that state is
    the review candidate, not a verification (the consult's catch: the old
    retired winner-only 'partial agreement' state let two officially-published 3-1s verify our 3-2)."""
    con = {"CONTRADICTS", "CONTRADICTS_SETS"}
    if sa == "AGREE_COMPLETE" and sb == "AGREE_COMPLETE":
        return "VERIFIED_BOTH"
    if sa in con and sb in con:
        return "CONTRADICTED_BOTH"
    if (sa in con) != (sb in con) and "AGREE_COMPLETE" in (sa, sb):
        return "SCHOOL_CONFLICT"
    if sa in con or sb in con:
        return "CONTRADICTED_ONE"
    if "AGREE_COMPLETE" in (sa, sb):
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


AUTO_EVIDENCE = os.path.join(RAW, "result_evidence_auto.json")


def write_auto_evidence():
    """Regenerate result_evidence_auto.json from every committed daily
    report: latest observation per (gid, school). Deterministic and
    disposable -- deleting the file loses nothing the reports do not hold."""
    import glob
    latest = {}
    for rp in sorted(glob.glob(os.path.join(
            REPO, "data", "result_verification_*.json"))):
        try:
            doc = json.load(open(rp))
        except ValueError:
            continue
        gen = doc.get("generated_utc") or ""
        for m in doc.get("matches") or []:
            gid = str(m.get("gid"))
            for school, e in (m.get("schools") or {}).items():
                st = e.get("state")
                if st not in ("AGREE_COMPLETE", "CONTRADICTS",
                              "CONTRADICTS_SETS"):
                    continue
                key = (gid, school)
                prev = latest.get(key)
                if prev and prev["generated"] > gen:
                    continue
                latest[key] = {
                    "url": e.get("url"),
                    "kind": "school_schedule",
                    "school": school,
                    "retrieved": (e.get("retrieved_utc") or gen),
                    "text": e.get("assertion"),
                    "fields": ["result"],
                    "status": ("confirms" if st == "AGREE_COMPLETE"
                               else "conflict_observed"),
                    "observed_state": st,
                    "origin": "nightly_verifier",
                    "generated": gen,
                }
    ev = {}
    for (gid, _school), entry in sorted(latest.items()):
        ev.setdefault(gid, []).append(entry)
    json.dump({
        "_doc": ("MACHINE-DERIVED evidence projection, regenerated by "
                 "verify_results_daily.py from the committed daily "
                 "verification reports -- the latest usable observation per "
                 "(gid, school). Do NOT hand-edit; hand-curated evidence "
                 "lives in result_evidence.json, and a validated "
                 "conflict_observed entry is PROMOTED there by a human as a "
                 "real 'conflicts' entry. conflict_observed can never lift "
                 "or dispute a state (confidence.entry_supports ignores "
                 "it); 'confirms' entries corroborate and, being the "
                 "'school' kind alone, can never cross-source CONFIRM a "
                 "result without an independent box-kind source."),
        "evidence": ev}, open(AUTO_EVIDENCE, "w"), indent=1)
    print("auto evidence: %d observation(s) across %d match(es) -> %s"
          % (len(latest), len(ev), os.path.relpath(AUTO_EVIDENCE, REPO)))


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

    # ── the auto evidence projection ─────────────────────────────────────
    # (design settled with the external consult, 2026-09-01 evening)
    # A SEPARATE regenerable file, never the hand-curated ledger: the LATEST
    # usable observation per (gid, school), rebuilt from ALL committed daily
    # reports. Affirmative observations only -- NOT_POSTED / EVENT_NOT_FOUND
    # / SITE_* assert nothing and stay in the reports and the fetch log. A
    # contradiction is written as status "conflict_observed", which
    # confidence.py's entry_supports deliberately IGNORES for state lifting:
    # one parser slip must never auto-DISPUTE the public ledger. A human
    # promotes a validated conflict into result_evidence.json as a real
    # "conflicts" entry.
    write_auto_evidence()

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
