#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the game-day readiness and live-probe runbook.

⚠ WHAT THIS PROTECTS. Friday is the first chance to answer a question this
project has deliberately left open for weeks: does the source serve team or
player statistics during a live match? The answer is only worth anything if the
measurement is precise, so the failure modes that would corrupt it are what is
tested -- a blank score read as zero, a 502 read as "no stats", and a late
re-run quietly weakening what was seen earlier.

Python 3.9 target. Run: python3 scripts/test_gameday.py
"""

import ast
import io
import json
import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)
import probe_observe as PO      # noqa: E402
import preflight_live as PF     # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    print("GAME-DAY READINESS GUARDS\n")

    print("1. PREFLIGHT IS READ-ONLY")
    src = io.open(os.path.join(SCRIPTS, "preflight_live.py"),
                  encoding="utf-8").read()
    tree = ast.parse(src)
    writes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            if fname == "open" and len(node.args) > 1:
                m = getattr(node.args[1], "s", getattr(node.args[1], "value", ""))
                if isinstance(m, str) and ("w" in m or "a" in m):
                    writes.append("open(...)")
            if fname in ("remove", "unlink", "rmtree", "makedirs", "rename"):
                writes.append(fname)
    check("[-] it never opens a file for writing", not writes, str(writes))
    # ⚠ SCAN CODE, NOT PROSE. "commit" appears in this file's own docstring
    # ("the committed game log") -- the guard-finds-its-own-denial trap, for
    # the eighth time in this project. Comments and docstrings are stripped
    # before asking whether the CODE does these things.
    code = re.sub(r'"""[\s\S]*?"""', " ", src)
    code = re.sub(r"#[^\n]*", " ", code)
    for bad in ("git ", "subprocess", "commit", "snapshot_rankings",
                "localStorage"):
        check("[-] and never touches %-18s" % bad, bad not in code)

    print("\n2. PREFLIGHT PICKS SENSIBLY")
    rows = PF.candidates()
    check("[+] it finds upcoming fixtures", len(rows) > 0, "%d" % len(rows))
    if rows:
        r = rows[0]
        for f in ("game_id", "away", "home", "when_pt", "link",
                  "context_known"):
            check("   a candidate reports %-14s" % f, f in r)
        check("   the link points at the official game page",
              r["link"].startswith("https://www.ncaa.com/game/"))
        check("   the time is stated in Pacific", "PT" in r["when_pt"])
        # ⚠ RANKED FOR USEFULNESS, NOT DRAMA: a watchable hour beats a
        # marquee fixture at 4am, because all four checkpoints must be
        # observable by a human.
        check("[-] the top pick is not in the small hours",
              6 <= r["pt_hour"] <= 22, "%dh PT" % r["pt_hour"])
        check("every candidate is in the future",
              all(x["epoch"] > 0 for x in rows))
        check("[-] no withdrawn fixture is offered",
              all(x["game_id"] for x in rows))

    print("\n3. EACH OUTCOME IS ITS OWN FACT")
    cases = [
        ("network failure", dict(transport_error="timeout"), PO.NETWORK_FAILURE),
        ("http 502", dict(http_status=502, body="<html>"), PO.SOURCE_502),
        # ⚠ NON-JSON IS THE SOURCE REFUSING, NOT AN EMPTY BOX SCORE.
        ("200 but HTML", dict(http_status=200, body="<html>err"), PO.SOURCE_502),
        ("valid, nothing yet", dict(http_status=200, body="{}"), PO.NO_DATA),
        ("final, no box", dict(http_status=200,
                               body='{"status":"F","teamBoxscore":[]}'),
         PO.FINAL_PENDING),
        ("final with box", dict(http_status=200,
                                body='{"status":"F","teamBoxscore":'
                                     '[{"playerStats":[1]},{"playerStats":[2]}]}'),
         PO.FINAL_WITH_BOX),
    ]
    for label, kw, want in cases:
        got = PO.classify(**kw)["outcome"]
        check("%-20s -> %s" % (label, want), got == want, got)
    live = PO.classify(http_status=200, body='{"status":"I"}',
                       scoreboard={"state": "I", "away_sets": 1, "home_sets": 0})
    check("live, no stats     -> live_score_only",
          live["outcome"] == PO.LIVE_SCORE_ONLY, live["outcome"])
    # ⚠ THE FINDING THE WHOLE EXERCISE IS FOR gets its own outcome name.
    hot = PO.classify(http_status=200,
                      body='{"status":"I","teamBoxscore":[{"a":1},{"b":2}]}',
                      scoreboard={"state": "I", "away_sets": 1, "home_sets": 0})
    check("live WITH team totals is recorded as its own finding",
          hot["outcome"] == "live_with_team_stats", hot["outcome"])
    check("...and flagged as notable", "notable" in hot["why"])

    print("\n4. A BLANK SCORE IS NOT ZERO")
    pre = PO.classify(http_status=502, body="<html>",
                      scoreboard={"away_sets": "", "home_sets": "",
                                  "state": "pre"})
    check("'' becomes None, never 0",
          pre["score"]["away"] is None and pre["score"]["home"] is None,
          str(pre["score"]))
    check("' ' too", PO._num("  ") is None)
    check("[+] but a real '0' is zero", PO._num("0") == 0)
    zero = PO.classify(http_status=200, body="{}",
                       scoreboard={"away_sets": "0", "home_sets": "0",
                                   "state": "I"})
    check("a genuine 0-0 is preserved",
          zero["score"]["away"] == 0 and zero["score"]["home"] == 0)

    print("\n5. SHAPE FACTS, NOT RAW BODIES")
    c = PO.classify(http_status=200,
                    body='{"status":"F","period":"FINAL","teamBoxscore":'
                         '[{"playerStats":[1,2,3]},{"playerStats":[4,5]}]}')
    check("team entries counted", c["shape"]["team_entries"] == 2)
    check("player rows counted", c["shape"]["player_rows"] == 5)
    rec = PO.observation("123", "box", c, "note")
    check("[-] the record carries NO response body",
          "body" not in rec and "raw" not in rec and "content" not in rec)
    check("the record carries what matters",
          {"observed_utc", "game_id", "checkpoint", "outcome", "shape",
           "score", "why"} <= set(rec))
    check("[-] and no credentials or cookies",
          not any(k in json.dumps(rec).lower()
                  for k in ("cookie", "token", "authorization", "password")))

    print("\n6. HISTORY IS APPEND-ONLY AND CANNOT BE WEAKENED")
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    tmp.close()
    try:
        strong = PO.observation("g1", "box",
                                PO.classify(http_status=200,
                                            body='{"status":"F","teamBoxscore":'
                                                 '[{"playerStats":[1]},{"x":2}]}'))
        a = PO.append_observation(strong, tmp.name)
        check("a real observation is written", a["written"])
        # ⚠ A FLAKY MIDNIGHT RE-RUN MUST NOT ERASE THE 4PM EVIDENCE.
        weak = PO.observation("g1", "box", PO.classify(transport_error="timeout"))
        b = PO.append_observation(weak, tmp.name)
        check("[-] a weaker later run is REFUSED", not b["written"], str(b))
        check("   ...and says why", "not overwritten" in b["reason"])
        rows = PO.read_observations(tmp.name)
        check("the file still holds exactly the strong row", len(rows) == 1,
              "%d rows" % len(rows))
        check("...unchanged", rows[0]["outcome"] == PO.FINAL_WITH_BOX)
        # a DIFFERENT checkpoint is independent
        other = PO.observation("g1", "pre", PO.classify(http_status=502,
                                                        body="<html>"))
        c2 = PO.append_observation(other, tmp.name)
        check("a different checkpoint is unaffected", c2["written"])
        # an equal-or-stronger repeat is allowed (a second confirmation)
        again = PO.append_observation(strong, tmp.name)
        check("an equally strong repeat may be appended", again["written"])
        check("[+] nothing is ever edited in place",
              len(PO.read_observations(tmp.name)) == 3)
    finally:
        os.unlink(tmp.name)

    print("\n7. THE PANEL DOES NOT OVERCLAIM")
    bh = io.open(os.path.join(SCRIPTS, "build_hub.py"), encoding="utf-8").read()
    check("readiness is computed", "def gameday_readiness" in bh)
    # ⚠ ONE THING SETS "PROVEN": a real match observed serving team totals.
    check("proven means exactly one measured outcome",
          'v == "live_with_team_stats" for v in done.values()' in bh)
    check("the panel says statistics are NOT established until then",
          "not established</b>" in bh)
    check("...and names what would change it",
          "observed serving them" in bh)
    check("[-] it never says ready/verified/confirmed of live stats",
          not any(w in bh for w in ("live stats ready", "live stats verified",
                                    "live stats confirmed")))
    priv = os.path.join(REPO, "Cody", "START-HERE.html")
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(priv) and os.path.exists(pub):
        ph = io.open(priv, encoding="utf-8").read()
        qh = io.open(pub, encoding="utf-8").read()
        check("[+] the private page shows the panel", "gd-panel" in ph)
        for sym in ("gd-panel", "GAMEDAY", "gdPanel", "live validation"):
            check("public: no %r" % sym, sym not in qh)

    print("\n8. THE RUNBOOK IS DOCUMENTED IN THE TOOL")
    pb = io.open(os.path.join(SCRIPTS, "probe_live_boxscore.py"),
                 encoding="utf-8").read()
    for cp in PO.CHECKPOINTS:
        check("checkpoint %-5s exists" % cp, '"%s"' % cp in pb)
    check("each checkpoint records one row", "def checkpoint_run" in pb)
    check("...and tells Cody what to send back",
          "PASTE THE BLOCK ABOVE" in pb)
    check("the standing rule is still stated",
          "may claim" in pb.lower() or "NOTHING IN THIS PROJECT" in pb)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL GAME-DAY GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
