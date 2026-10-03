#!/usr/bin/env python3
"""Private season-only candidate (mail 066): private-only, parity with the frozen
file, no downstream consumer, and rollback = file absent -> nothing emitted."""
import glob, json, os, re, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
ok = True
def check(c, msg):
    global ok
    print(("PASS " if c else "FAIL ") + msg); ok = ok and bool(c)
src = open(os.path.join(REPO, "scripts", "build_hub.py")).read()
check('"" if PUBLIC or not v2so_preview_payload() else V2S_BTN' in src, "button emitted only on a private build with a frozen file")
check('"" if PUBLIC or not v2so_preview_payload() else' in src.split('"{{V2S_JS}}"')[1][:80], "script emitted only on a private build")
check('"POWER 2026 &mdash; candidate"' in src and '"const V2S ="' in src, "public gate carries the preview markers (build aborts on leak)")
readers = [p for p in glob.glob(os.path.join(REPO, "scripts", "*.py"))
           if "v2so_preview" in open(p, errors="ignore").read()
           and os.path.basename(p) not in ("build_hub.py", "test_v2so_preview.py",
                                           "season_only_candidate.py",      # the PRODUCER (writes it)
                                           "season_only_scorecard.py",     # Cody-approved prospective scorecard (2026-09-28); writes only its own log
                                           "build_rankings_board.py",      # the PRIVATE DEFAULT consumer (Cody 2026-09-28), gated on WVB_POWER_DEFAULT
                                           "predict_2026.py",              # private forecasts (Cody: "switch the forecasts"), gated on the DEFAULT_ON flag; tracked outputs untouched
                                           "simulate_season_2026.py")]     # private season simulation (Cody: "switch the simulator too"), same gating
pr = open(os.path.join(REPO, "scripts", "predict_2026.py")).read()
check('"DEFAULT_ON"' in pr and 'power_candidate", "predictions_2026.json"' in pr, "predict_2026 writes candidate forecasts only to the private file, behind the flag")
check('os.environ.get("WVB_POWER_DEFAULT") == "candidate"' in open(os.path.join(REPO, "scripts", "build_rankings_board.py")).read(),
      "the board reads the candidate only behind the private-default env flag")
sc = open(os.path.join(REPO, "scripts", "season_only_scorecard.py")).read()
check('"w")' not in sc.replace('open(SUM, "w")', "") and "scorecard_log.jsonl" in sc,
      "scorecard only appends its own log and writes its own summary")
check("v2so_preview.json" in open(os.path.join(REPO, "scripts", "season_only_candidate.py")).read()
      and '"freeze"' in open(os.path.join(REPO, "scripts", "season_only_candidate.py")).read(),
      "season_only_candidate.py only produces the file (freeze) -- allowed as the writer")
check(not readers, "no other script reads the preview file %s" % readers)
shared = src.split("const RULER_VIEWS = {};")[0][-3000:] + src.split("function renderPoll(which) {")[1][:6000]
check("v2s" not in shared and "V2S" not in shared, "shared ruler code names no preview view")
# rollback: file absent -> payload None
import build_hub as B
B._V2S_CACHE[:] = []
real = B.load
B.load = lambda rel: None if "v2so_preview" in rel else real(rel)
check(B.v2so_preview_payload() is None, "file absent -> preview payload None (placeholders render empty)")
B.load = real; B._V2S_CACHE[:] = []
fz = os.path.join(REPO, "Cody", "data", "power_candidate", "v2so_preview.json")
page = os.path.join(REPO, "Cody", "START-HERE.html")
if os.path.exists(fz) and os.path.exists(page):
    html = open(page, encoding="utf-8").read()
    m = re.search(r"const V2S = (\{.*?\});\n", html)
    check(m, "private page carries the preview payload")
    if m:
        emb, frozen = json.loads(m.group(1)), json.load(open(fz))
        check(emb["teams"] == frozen["teams"] and emb["version"] == frozen["version"],
              "embedded ranks/values identical to the frozen file (%s)" % frozen["version"])
        check(len(emb["teams"]) + len(emb["unrated"]) == 348, "every D-I team rated or explicitly unrated")
        # ⚠ 2026-09-28: two freezes silently ran the PLAIN base while the file claimed a richer model.
        # The frozen file must now say which fit ran, and it must match what the page describes.
        sp = emb.get("start_parts") or []
        want = ("c093.fit_both+T" if "team_results" in sp else "c093.fit_both") if emb.get("structure") else ("c087.fit" if len(sp) == 3 else None)
        check(want is None or emb.get("fit_used") == want, "frozen file records the fit that actually ran (%s)" % emb.get("fit_used"))
        check(not emb.get("structure") or (emb.get("conference_effects") and len(emb["conference_effects"]) > 20), "conference effects present when structure is claimed")
        # RULE-101/104 (2026-09-28): the four fit knobs are a MEASURED selection, not hand-set. The frozen file must
        # carry the cell the receipts chose: c101's winner, replaced by c104's only if c104's verdict is CHANGE.
        import re as _re
        cell = None
        for rc in ("c101_eval.json", "c104_eval.json"):
            rp = os.path.join(REPO, "Cody", "data", "power_candidate", rc)
            if os.path.exists(rp):
                v = json.load(open(rp)); mm = _re.match(r"CHANGE to L([\d.]+)\|K([\d.]+)\|S(\d+)\|F([\d.]+)", v.get("verdict") or "")
                if mm:
                    cell = {"lambda": float(mm.group(1)), "earned_weight": float(mm.group(2)), "opp_uncertainty_s0": int(mm.group(3)), "fifth_set_weight": float(mm.group(4))}
        if emb.get("structure") and cell:
            got = dict((k, emb.get(k)) for k in cell)
            check(got == cell, "frozen knobs equal the receipt-selected cell (%s vs receipts %s)" % (got, cell))
        # WHY block (2026-09-28): explanation must reconcile with the rank it explains -- parts sum to theta, every
        # counted result is listed exactly once with the record it produced, and the trajectory ends at today's rank.
        why_teams = [(n, t) for n, t in emb["teams"].items() if t.get("why")]
        if "team_results" in (emb.get("start_parts") or []):
            check(len(why_teams) == len(emb["teams"]), "every rated team carries a why block (%d of %d)" % (len(why_teams), len(emb["teams"])))
            bad_sum = [n for n, t in why_teams if abs(t["why"]["parts"]["season"] + t["why"]["parts"]["conf"] + sum(t["why"]["parts"]["start"].values()) - t["theta"]) > 2e-4]
            check(not bad_sum, "why parts sum to theta for every team (%d off: %s)" % (len(bad_sum), bad_sum[:3]))
            bad_rec = [n for n, t in why_teams if "%d-%d" % (sum(1 for r in t["why"]["results"] if r["won"]), sum(1 for r in t["why"]["results"] if not r["won"])) != t["record"]]
            check(not bad_rec, "listed results reproduce the record for every team (%d off: %s)" % (len(bad_rec), bad_rec[:3]))
            bad_tr = [n for n, t in why_teams if not t["why"]["trajectory"] or t["why"]["trajectory"][-1]["rank"] != t["rank"]]
            check(not bad_tr, "trajectory ends at the current rank for every team (%d off: %s)" % (len(bad_tr), bad_tr[:3]))
            check(isinstance(emb.get("theta_sd"), (int, float)) and emb["theta_sd"] > 0, "theta_sd carried for the POWER-point scale")
            check(all(r["site"] in ("H", "A", "N") for _, t in why_teams for r in t["why"]["results"]), "every listed result names its floor (H/A/N)")
            # what-if (2026-09-28): a win can never leave a team ranked below where a loss leaves it
            wi = [(n, t["why"]["what_if"]) for n, t in why_teams if t["why"].get("what_if")]
            bad_wi = [n for n, w in wi if not (w.get("win") and w.get("loss")) or w["win"]["rank"] > w["loss"]["rank"]]
            check(wi and not bad_wi, "what-if present and coherent for the teams that carry it (%d teams, %d incoherent)" % (len(wi), len(bad_wi)))
        cur = json.load(open(os.path.join(REPO, "data", "digby_top25_2026.json")))
        check(emb["current"]["rank"] == dict((r["team"], r["rank"]) for r in cur["all"]),
              "current column = current POWER ranks, unchanged")
        # team-page hook (2026-09-28): the dossier carries the anatomy only through the WHY-HOOK fence
        check("/* WHY-HOOK-BEGIN */" in html and "tdWhyRank" in html, "private page carries the team-page why hook")
        pub = open(os.path.join(REPO, "output", "vb_dashboard.html"), encoding="utf-8", errors="ignore").read()
        check("tdWhyRank" not in pub and "WHY-HOOK" not in pub, "public page carries neither the hook nor its fence")
    for p in ("data/digby_top25_2026.json", "output/vb_dashboard.html"):
        t = open(os.path.join(REPO, p), encoding="utf-8", errors="ignore").read()
        check("v2so-" not in t and "const V2S" not in t, "%s carries no preview value" % p)
else:
    print("SKIP page checks: private page or frozen file absent (CI / rollback)")
print("ALL V2 SEASON-ONLY CHECKS HOLD" if ok else "V2 SEASON-ONLY CHECKS FAILED"); sys.exit(0 if ok else 1)
