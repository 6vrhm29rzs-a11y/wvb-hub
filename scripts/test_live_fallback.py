#!/usr/bin/env python3
"""Live-display backup rules (mails 039/040). Synthetic ESPN fixtures, the
real merge/identify code."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import live_fallback as LF
FAIL = []
def check(n, ok):
    print("  %-66s %s" % (n, "ok" if ok else "FAIL"))
    if not ok: FAIL.append(n)
NOW = 1790532000

def ev(away, home, state="in", aw=0, hw=2, a_l=(23, 20, 4), h_l=(25, 25, 2), done=False, fetched=NOW):
    doc = {"events": [{"id": "e1", "status": {"type": {"state": state, "completed": done, "shortDetail": "3rd Set"}},
           "competitions": [{"competitors": [
               {"homeAway": "home", "team": {"location": home}, "score": str(hw), "linescores": [{"value": v} for v in h_l]},
               {"homeAway": "away", "team": {"location": away}, "score": str(aw), "linescores": [{"value": v} for v in a_l]}]}]}]}
    return LF.parse(doc, fetched)

def row(state="pre", a="Texas", h="Kentucky", **kw):
    r = {"id": "g1", "state": state, "away": a, "home": h, "away_sets": None, "home_sets": None, "sets": []}
    r.update(kw); return r

check("disabled unless Cody switches it on", not LF.enabled())
# primary stale -> backup carries the display, labelled
r = row(); m = {}
lab = LF.merge(r, LF.identify(r, ev("Texas", "Kentucky")), m, NOW + 60)
check("NCAA pre + ESPN in progress -> ESPN live score shown", lab == "espn" and r["state"] == "live" and r["sets"] == [[23, 25], [20, 25], [4, 2]])
check("...labelled with source and fetch time", r["source"] == "ESPN" and r["source_fetched_epoch"] == NOW and "ESPN" in r["source_note"])
# wrong match
r2 = row(a="Texas A&M")
check("wrong match (Texas A&M vs Texas) is not identified", LF.identify(r2, ev("Texas", "Kentucky")) is None)
check("reversed home/away is not identified", LF.identify(row(a="Kentucky", h="Texas"), ev("Texas", "Kentucky")) is None)
two = ev("Texas", "Kentucky") + [dict(e, id="e2") for e in ev("Texas", "Kentucky")]
check("two candidate events -> no identity (never a guess)", LF.identify(row(), two) is None)
# backup unavailable -> last known kept, marked stale, never back to scheduled
r3 = row()
lab = LF.merge(r3, None, m, NOW + 40 * 60)
check("backup gone: last known score kept, not reverted to scheduled", lab == "espn_last_known" and r3["state"] == "live")
check("...and marked stale", r3["source_stale"] and "LAST KNOWN" in r3["source_note"])
check("[NEG] with no memory, an NCAA pre row stays pre", LF.merge(row(), None, {}, NOW) is None)
# missing scores
e_pre = ev("Texas", "Kentucky", state="pre")
r4 = row(); check("ESPN pre adds nothing", LF.merge(r4, LF.identify(r4, e_pre), {}, NOW) is None and r4["state"] == "pre")
# final conflict
r5 = row(state="final", away_sets="3", home_sets="1", sets=[[25, 20]] * 4)
lab = LF.merge(r5, LF.identify(r5, ev("Texas", "Kentucky", state="post", aw=1, hw=3, done=True)), {}, NOW)
check("NCAA final vs ESPN final disagreeing -> conflict stated, NCAA kept", lab == "conflict" and r5["away_sets"] == "3" and "source_conflict" in r5)
# a seen final never reverts to in-progress
mm = {}
r6 = row(); LF.merge(r6, LF.identify(r6, ev("Texas", "Kentucky", state="post", aw=0, hw=3, done=True, a_l=(23, 20, 20), h_l=(25, 25, 25))), mm, NOW)
r7 = row(); LF.merge(r7, LF.identify(r7, ev("Texas", "Kentucky")), mm, NOW + 60)
check("an ESPN final is never replaced by an older in-progress reading", r7["state"] == "final")
# recovery
r8 = row(state="live", away_sets="0", home_sets="2", sets=[[23, 25], [20, 25], [4, 2]], period="3RD SET")
lab = LF.merge(r8, LF.identify(r8, ev("Texas", "Kentucky")), m, NOW)
check("recovered, consistent primary is used again", lab is None and r8.get("source") is None and "g1" not in m)
r9 = row(state="live", away_sets="0", home_sets="0", sets=[[3, 4]], period="1ST SET")
lab = LF.merge(r9, LF.identify(r9, ev("Texas", "Kentucky")), {}, NOW)
check("a primary that resumed BEHIND the backup does not move the score backwards", lab == "espn_ahead_of_primary" and len(r9["sets"]) == 3)
# failure/backoff
LF._health.update(fails=0, next_try=0)
class Boom(Exception): pass
def bad_open(*a, **k): raise Boom("HTTP Error 403: Forbidden")
check("a failed fetch returns None, never raises", LF.fetch("20260927", NOW, bad_open) is None)
check("...records the reason and backs off", LF.health()["last_error"].startswith("HTTP Error 403") and LF.health()["next_try"] > NOW)
check("...and does not retry inside the backoff", LF.fetch("20260927", NOW + 5, bad_open) is None and LF.health()["fails"] == 1)
check("the honest UA is not a disguised browser/library one", "wvb-hub" in LF.UA)
src = open(os.path.join(HERE, "live_fallback.py")).read()
check("nothing in the backup writes to data/", "data/" not in src.replace("to data/", "").replace("data/.", "") or "open(" not in src)
print("FAILED: %s" % FAIL if FAIL else "ALL LIVE-FALLBACK CHECKS HOLD"); sys.exit(1 if FAIL else 0)
