#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HOW MANY SCHOOLS PUBLISH A READABLE GAMEBOOK? A measurement, not a crawl.

    python3 scripts/gamebook_census.py [N]

WHY THIS EXISTS. The pilot (CL-0006/CL-0007) proved a LiveStats gamebook is
readable and carries rotations, serve order and both-name substitutions --
and then proved the format is NOT universal: Louisville publishes a SIDEARM
box with no play-by-play at all, Nebraska publishes nothing extractable. So
the question that decides whether any ingestion is worth building is simply
HOW MANY schools are on the LiveStats format. This answers exactly that.

⚠ IT CLASSIFIES AND DISCARDS. One document per school, read for its first
page, categorised, and thrown away. Nothing is stored, nothing is parsed for
statistics, nothing reaches data/. The output is a count.

⚠ AND IT IS BOUNDED AND POLITE. A fixed sample, the existing per-host lock
and fetch path, at most three requests per school. It is not a collector and
must not become one without a separate decision.

Formats, from the pilot:
  livestats_gamebook -- `##` team headers + Play-by-Play. Everything.
  sidearm_box        -- box totals only. NO play-by-play.
  not_a_pdf          -- the .pdf URL returns HTML (Nebraska's shape).
  none_found         -- no per-match document located by these routes.
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SKIP_PAT = re.compile(r"factbook|media-guide|guide|roster|schedule\.pdf|"
                      r"record-book|notes|release|poster|program",
                      re.I)


def candidates(base, html):
    """PDF URLs a page links, match documents first, boilerplate last."""
    out = []
    for m in re.finditer(r"https?://[^\"'\s\\<>]+\.pdf", html or ""):
        u = m.group(0)
        if SKIP_PAT.search(u):
            continue
        out.append(u)
    # a match tag (ma09-, gm01-) or a stats path is the strongest signal
    out.sort(key=lambda u: (0 if re.search(r"[-/](?:ma|gm)\d+-", u) else
                            1 if "/stats/" in u else 2, len(u)))
    return out


def classify(raw):
    if not raw[:5].startswith(b"%PDF"):
        return "not_a_pdf", ""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        txt = subprocess.check_output(["pdftotext", "-layout", "-l", "2",
                                       path, "-"],
                                      stderr=subprocess.DEVNULL)
        t = txt.decode("utf-8", "replace")
    except Exception:
        return "unreadable", ""
    finally:
        os.unlink(path)                 # ⚠ DISCARDED. Nothing is kept.
    if re.search(r"^\s*##\s+\S", t, re.M):
        return ("livestats_gamebook" if "Play-by-Play" in t
                else "livestats_box_nopbp"), t[:0]
    if re.search(r"\bSP\s+K\s+E\s+TA\s+PCT\b", t) or \
            re.search(r"^#\s+Player\s+SP\s", t, re.M):
        return "sidearm_box", ""
    return "other_pdf", ""


def probe(school, base, V, sid_of):
    """<=3 requests: schedule page, then one box page, then one document."""
    tried = []
    # 1) the schedule page's own PDF links
    for path in ("/sports/womens-volleyball/schedule",
                 "/sports/wvball/schedule/"):
        st, body, _ = V._fetch(base + path)
        tried.append(path)
        if st == 200 and body:
            # ⚠ ONLY A CANDIDATE WITH A MATCH SIGNAL. A schedule page also
            # links strategic plans and stat roundups; taking "the first
            # PDF" classified Tennessee's strategic plan as a gamebook
            # attempt. Require a match tag or a /stats/ path here, and fall
            # through to the box page otherwise.
            cands = [u for u in candidates(base, body)
                     if re.search(r"[-/](?:ma|gm)\d+-", u) or "/stats/" in u]
            if cands:
                return cands[0], "schedule"
            # 2) a box-score page linked from it
            m = re.search(r'href="([^"]*(?:boxscore[^"]*)")', body)
            if m:
                bu = m.group(1).strip('"')
                if bu.startswith("/"):
                    bu = base + bu
                st2, b2, _ = V._fetch(bu)
                if st2 == 200 and b2:
                    c2 = candidates(base, b2)
                    if c2:
                        return c2[0], "boxpage"
            break
    # 3) the platform API -> box_score_url
    sid = sid_of.get(school)
    if sid:
        u = (base + "/website-api/schedule-events?filter%5Bschedule.sport_id"
             "%5D=" + str(sid) + "&per_page=20&sort=-datetime")
        st, body, _ = V._fetch(u)
        if st == 200 and body:
            try:
                d = json.loads(body)
            except ValueError:
                d = {}
            for r in (d.get("data") or []):
                if r.get("status") == "completed" and r.get("box_score_url"):
                    st2, b2, _ = V._fetch(r["box_score_url"])
                    if st2 == 200 and b2:
                        c2 = candidates(base, b2)
                        if c2:
                            return c2[0], "api_boxpage"
                    break
    return None, "none"


def main():
    import verify_results_daily as V
    import fixture_time_check as F
    import collections
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    sites = V._sites()
    sid_of = F.load_ids()
    dg = json.load(io.open(os.path.join(
        REPO, "data", "digby_top25_2026.json"), encoding="utf-8"))
    order = [r["team"] for r in sorted(dg["all"], key=lambda x: x["rank"])]
    sample = [t for t in order if t in sites][:n]
    print("GAMEBOOK FORMAT CENSUS -- %d schools, classify and DISCARD\n" % len(sample))
    tally = collections.Counter()
    rows = []
    for i, school in enumerate(sample, 1):
        base = sites[school].rstrip("/")
        try:
            url, route = probe(school, base, V, sid_of)
        except Exception as e:
            url, route = None, "error:%s" % type(e).__name__
        fmt = "none_found"
        if url:
            try:
                st, raw, _ = None, None, None
                import urllib.request
                req = urllib.request.Request(
                    url, headers={"User-Agent": "wvb-hub census (personal)"})
                # ⚠ READ THE WHOLE DOCUMENT. Capping at 400 KB truncated
                # Kentucky's 595 KB gamebook, pdftotext could not parse the
                # fragment, and the census reported "unreadable" for the one
                # document we had already parsed successfully -- i.e. it
                # would have printed 0% for the format it was measuring.
                # A negative result from an incomplete scanner is not a
                # finding. These are 100 KB - 1 MB; read them fully.
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read()
                fmt, _ = classify(raw)
                del raw                      # ⚠ discarded
            except Exception as e:
                fmt = "fetch_error"
        tally[fmt] += 1
        rows.append((school, fmt, route, (url or "")[:70]))
        print("%3d %-22s %-20s %-12s %s"
              % (i, school, fmt, route, (url or "")[-48:]))
    print("\nTALLY")
    for k, v in tally.most_common():
        print("   %-22s %d  (%.0f%%)" % (k, v, 100.0 * v / len(sample)))
    gold = tally["livestats_gamebook"]
    print("\n   LiveStats gamebooks WITH play-by-play: %d of %d (%.0f%%)"
          % (gold, len(sample), 100.0 * gold / len(sample)))
    print("   That is the only format carrying rotations, serve order and")
    print("   both-name substitutions. Nothing was stored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
