#!/usr/bin/env python3
"""Mail 073 corrections (2026-11-05): behavioural regressions, isolated storage.

#1 candidate input identity: same cut-off + corrected earlier score / changed
   eligibility / changed site -> refit and manifest updated; failed fit keeps
   the previous artifact and stays retryable; idle unchanged inputs skip.
#2 site is a rating input: a site VALUE change -> full rebuild; a citation-only
   ledger change stays presentation; venues run BEFORE the gate.
#3 weekly label: a row whose results run past its cutoff is not called a
   week-ending freeze; a freeze-only change reaches the page (present mode).
Never touches Cody's real ballot/candidate state: everything runs in temp dirs.
Python 3.9."""
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_only_candidate as SOC  # noqa: E402
import local_refresh as LR            # noqa: E402
import build_rankings_board as BRB    # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


EP = 1_793_000_000


def game(gid, start, h, v, hs=3, vs=1, **kw):
    g = {"game_id": gid, "start_time_epoch": start, "state": "F", "winner_team_id": "A" if hs > vs else "B",
         "linescores": [{"period": 1, "home": 25, "visit": 20}],
         "teams": [{"team_id": "A", "is_home": True, "sets_won": hs, "is_winner": hs > vs},
                   {"team_id": "B", "is_home": False, "sets_won": vs, "is_winner": vs > hs}]}
    g.update(kw)
    return g


def make_repo(root, games, sites, box_extra=None):
    os.makedirs(os.path.join(root, "data", "raw", "2026"), exist_ok=True)
    json.dump({"games": games}, open(os.path.join(root, "data", "data_2026.json"), "w"))
    json.dump({"games": [{"game_id": g, "site": s} for g, s in sites.items()]},
              open(os.path.join(root, "data", "venues_2026.json"), "w"))
    with open(os.path.join(root, "data", "raw", "2026", "boxscores.jsonl"), "w") as f:
        for g in games:
            r = {"game_id": g["game_id"], "teams": [{"k": 40}], "fetched_utc": "2026-11-01T00:00:00Z"}
            r.update((box_extra or {}).get(g["game_id"], {}))
            f.write(json.dumps(r) + "\n")


def test_identity():
    d = tempfile.mkdtemp()
    try:
        base = [game("1", EP - 1000, "A", "B"), game("2", EP - 500, "A", "B")]
        make_repo(d, base, {"1": "home", "2": "home"})
        i0, m0 = SOC.input_identity(EP, d)
        check(SOC.input_identity(EP, d)[0] == i0, "identity is deterministic (idle -> same)")
        # timestamp-only box change -> unchanged
        make_repo(d, base, {"1": "home", "2": "home"}, {"1": {"fetched_utc": "2026-11-05T00:00:00Z"}})
        check(SOC.input_identity(EP, d)[0] == i0, "re-fetch timestamp alone does not change identity")
        # a game AFTER the cut-off -> unchanged
        make_repo(d, base + [game("9", EP + 100, "A", "B")], {"1": "home", "2": "home", "9": "home"})
        check(SOC.input_identity(EP, d)[0] == i0, "a final after the cut-off does not change identity")
        # corrected EARLIER score, same max timestamp
        cor = [game("1", EP - 1000, "A", "B", hs=1, vs=3, result_corrected=True), base[1]]
        make_repo(d, cor, {"1": "home", "2": "home"})
        i1, m1 = SOC.input_identity(EP, d)
        check(i1 != i0 and m1["games"] != m0["games"], "corrected earlier score -> identity + manifest change")
        # eligibility change (held under review)
        make_repo(d, [game("1", EP - 1000, "A", "B", under_review=True), base[1]], {"1": "home", "2": "home"})
        check(SOC.input_identity(EP, d)[0] != i0, "eligibility change (under_review) -> identity changes")
        # site correction at same cut-off
        make_repo(d, base, {"1": "neutral", "2": "home"})
        i3, m3 = SOC.input_identity(EP, d)
        check(i3 != i0 and m3["sites"] != m0["sites"], "site correction -> identity + manifest change")
        # box stat revision
        make_repo(d, base, {"1": "home", "2": "home"}, {"2": {"teams": [{"k": 41}]}})
        check(SOC.input_identity(EP, d)[0] != i0, "box-score stat revision -> identity changes")
    finally:
        shutil.rmtree(d)


FAKE_FIT = r'''
import json, os, sys
root = os.environ["T073_ROOT"]
if os.environ.get("T073_FAIL"):
    print("fit failed"); sys.exit(2)
out = {"version": "t", "data_through_epoch": int(sys.argv[3]), "lambda": 8.0, "earned_weight": 0.15,
       "ramp_w0": 0.5, "ballast_active": True, "height_term": False, "start_parts": [1, 2, 3, 4],
       "structure": "s", "fit_used": "c093.fit_both+T", "fifth_set_weight": 0.5,
       "opp_uncertainty_s0": 96, "theta_sd": 1.0, "teams": {}}
n = os.path.join(root, "fits.txt"); open(n, "a").write("x\n")
json.dump(out, open(os.path.join(root, "Cody", "data", "power_candidate", "v2so_preview.json"), "w"))
print("frozen")
'''


def test_main_flow():
    d = tempfile.mkdtemp()
    saved = (SOC.REPO, SOC.WORK, SOC.DIR, list(sys.argv), dict(os.environ))
    try:
        base = [game("1", EP - 1000, "A", "B"), game("2", EP - 500, "A", "B")]
        make_repo(d, base, {"1": "home", "2": "home"})
        os.makedirs(os.path.join(d, "Cody", "data", "power_candidate"))
        json.dump({"meta": {"data_through_epoch": EP}}, open(os.path.join(d, "data", "digby_top25_2026.json"), "w"))
        fake = os.path.join(d, "fake_fit.py")
        open(fake, "w").write(FAKE_FIT)
        SOC.REPO, SOC.WORK, SOC.DIR = d, fake, os.path.join(d, "Cody", "data", "power_candidate")
        os.environ["T073_ROOT"] = d
        sys.argv = ["season_only_candidate.py"]
        out = os.path.join(SOC.DIR, "v2so_preview.json")
        fits = os.path.join(d, "fits.txt")
        nfits = lambda: len(open(fits).readlines()) if os.path.exists(fits) else 0  # noqa: E731

        check(SOC.main() == 0 and nfits() == 1, "first run fits")
        a1 = json.load(open(out))
        check(bool(a1.get("input_identity")) and "games" in (a1.get("input_manifest") or {}),
              "successful artifact records input identity + manifest")
        check(SOC.main() == 0 and nfits() == 1, "idle unchanged inputs -> skipped (no refit)")
        # corrected earlier score at the SAME cut-off
        make_repo(d, [game("1", EP - 1000, "A", "B", hs=0, vs=3), base[1]], {"1": "home", "2": "home"})
        check(SOC.main() == 0 and nfits() == 2, "same cut-off, corrected earlier score -> refit")
        a2 = json.load(open(out))
        check(a2["input_identity"] != a1["input_identity"], "manifest updated after the corrected-score refit")
        # failed fit: previous artifact retained, retried next cycle
        make_repo(d, [game("1", EP - 1000, "A", "B", hs=0, vs=3), base[1]], {"1": "neutral", "2": "home"})
        os.environ["T073_FAIL"] = "1"
        before = open(out).read()
        check(SOC.main() == 1 and open(out).read() == before, "failed fit -> previous artifact kept unchanged")
        os.environ.pop("T073_FAIL")
        check(SOC.main() == 0 and nfits() == 3, "after a failed fit the next cycle retries (site change)")
        check(SOC.main() == 0 and nfits() == 3, "...and then skips again once settled")
    finally:
        SOC.REPO, SOC.WORK, SOC.DIR = saved[0], saved[1], saved[2]
        sys.argv = saved[3]
        os.environ.clear(); os.environ.update(saved[4])
        shutil.rmtree(d)


def test_gate():
    d = tempfile.mkdtemp()
    try:
        vp = os.path.join(d, "venues.json")
        json.dump({"games": [{"game_id": "1", "site": "home", "citation": "a"}]}, open(vp, "w"))
        s0 = LR.site_digest(vp)
        json.dump({"games": [{"game_id": "1", "site": "home", "citation": "b (reworded)"}]}, open(vp, "w"))
        check(LR.site_digest(vp) == s0, "citation-only change does not move the site digest")
        json.dump({"games": [{"game_id": "1", "site": "neutral", "citation": "b"}]}, open(vp, "w"))
        s1 = LR.site_digest(vp)
        check(s1 != s0, "site value change moves the site digest")
        prev = {"finals": "f", "rating": "r:v:d:" + s0, "presentation": "p:w"}
        cur = dict(prev, rating="r:v:d:" + s1)
        check(LR.decide(prev, cur) == "full", "site change -> FULL rebuild (ratings + candidate + forecasts)")
        check(LR.decide(prev, dict(prev)) == "none", "nothing changed -> none")
        # weekly freeze alone -> present
        ap = os.path.join(d, "hist.jsonl")
        open(ap, "w").write('{"week":"W1"}\n')
        w0 = LR.weekly_digest([ap])
        open(ap, "a").write('{"week":"W2"}\n')
        w1 = LR.weekly_digest([ap])
        check(w1 != w0, "an appended weekly freeze moves the weekly digest")
        check(LR.decide(dict(prev, presentation="p:" + w0), dict(prev, presentation="p:" + w1)) == "present",
              "freeze-only change -> page rebuild (movement labels)")
        names = [a[0] for a in LR.PREGATE]
        check("scripts/venues.py" in names and "scripts/venue_site_evidence.py" in names,
              "site ledger + venues run before the gate")
        check(names.index("scripts/venue_site_evidence.py") < names.index("scripts/venues.py"),
              "evidence produced before it is applied")
        check(all(a[1][0] != "scripts/venues.py" for a in LR.PRESENT), "PRESENT no longer re-runs venues")
        check(LR.site_digest() in LR.digests("f")["rating"], "real digests(): site digest is part of the RATING digest")
        check(LR.weekly_digest() in LR.digests("f")["presentation"], "real digests(): weekly digest is presentation")
    finally:
        shutil.rmtree(d)


def test_label():
    w42 = {"week": "2026-W42", "cutoff": "2026-10-18", "captured_utc": "2026-10-20T00:38:49Z",
           "data_through_epoch": 1792450800}
    lab = BRB.weekly_label(w42)
    check(not lab.startswith("the week-ending") and "Oct 19" in lab, "W42 (results past cutoff) not called a week-ending freeze: " + lab)
    ok = dict(w42, data_through_epoch=1792450800 - 2 * 86400)
    check(BRB.weekly_label(ok) == "the week-ending Oct 18 freeze", "a true week-ending row keeps the freeze label")
    check(BRB.weekly_label({"week": "2026-W40", "cutoff": "2026-10-04"}) == "the week-ending Oct 4 freeze",
          "published-archive row without results-through keeps cutoff label")
    # negative control: the pre-073 label (cutoff only) would mislabel W42
    old = "the week-ending Oct 18 freeze"
    check(old != lab, "negative control: cutoff-only label differs from the honest one")


if __name__ == "__main__":
    test_identity()
    test_main_flow()
    test_gate()
    test_label()
    print("\n%d failure(s)" % len(FAILS))
    sys.exit(1 if FAILS else 0)
