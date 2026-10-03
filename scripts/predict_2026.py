#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Win probability for every scheduled 2026 match.

Reuses the rally model from scripts/simulate_2025.py rather than inventing a
second one: an expected per-set point margin becomes a per-rally probability,
and the best-of-5 outcome distribution follows analytically (Ferrante & Fonseca)
instead of by coin-flipping. The rally model itself scores Brier 0.1289 over
5,014 2025 matches when fed each match's TRUE margin -- a property of the
margin-to-probability mapping, NOT the accuracy of this forecast (which does
not know the margin in advance). The forecast's own record is the 2026 log.

WHERE STRENGTH COMES FROM: the same blend the Rankings tab shows -- the
preseason projection pulled toward this season's results, weight n/(n+k) --
converted to points/set by one scale fitted on 2025 (its old "held-out"
check reused outcomes -- see build()) and checked on
2025 matches (measure_forecast_calibration.py). Last season alone was the
source until 2026-09-23 and is now only the fallback. Every row still carries
how many 2026 matches its teams have played.

HOME ADVANTAGE IS APPLIED ONLY WHERE THERE IS A HOME TEAM. The fitted advantage
comes from our own ridge solve, not the literature, and scripts/venues.py says
which floors are neutral. All eight Jeep AVCA First Serve matches are neutral,
so none of them gets one.

Python 3.9 target. Writes data/predictions_2026.json.
"""

import json
import os
import sys
import glob
import datetime
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulate_2025 as S  # noqa: E402

SEASON = 2026
OUT = os.path.join(REPO, "data", "predictions_%d.json" % SEASON)
# A PERMANENT RECORD OF WHAT WE SAID BEFORE THE MATCH.
# predictions_2026.json only ever holds FUTURE fixtures -- a game drops out of it
# the moment it is played. Scoring the model against results afterwards would
# then mean re-deriving a "prediction" from data that now includes the outcome,
# which is not a forecast, it is a fit. So each fixture's first prediction is
# appended here and NEVER revised: first write wins, permanently.
LOG = os.path.join(REPO, "data", "raw", str(SEASON), "prediction_log.jsonl")

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                       # pragma: no cover
    ET = None


def load(p, default=None):
    path = os.path.join(REPO, p)
    return json.load(open(path)) if os.path.exists(path) else default


def et_date(epoch):
    if not epoch:
        return None
    if ET:
        return datetime.datetime.fromtimestamp(int(epoch), ET).strftime("%Y-%m-%d")
    return (datetime.datetime.utcfromtimestamp(int(epoch))
            - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")


def cand_win(cand, home, away, neutral):
    """Home-win chance from the frozen candidate's calibrated mapping (same formula as the page)."""
    import math
    m, T = cand["win_model"], cand.get("teams") or {}
    if home not in T or away not in T:
        return None
    d = T[home]["theta"] - T[away]["theta"]
    dep = min(1.0, min(T[home].get("sets", 40), T[away].get("sets", 40)) / 40.0)
    k = m["b"] + m["c"] * m["s_now"] + m.get("e", 0.0) * dep
    z = k * d if neutral else (m["a"] + k * (d + (cand.get("home_setshare") or 0.0)))
    return 1.0 / (1.0 + math.exp(-z))


def margin_for_win(p, lo=-20.0, hi=20.0):
    """The per-set margin at which the rally model gives home-win chance p (monotone; bisection)."""
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if S.match_dist(S.rally_p(mid))["win"] < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def build():
    # ⚠ STRENGTH IS THE BLEND NOW, NOT LAST SEASON (Cody 2026-09-23: "2025
    # numbers should only be used for baseline and start points"). The same
    # blend the Rankings tab shows (digby_top25: preseason + 2026 results,
    # w=n/(n+k)), converted to points/set by ONE scale fitted on 2025
    # (measure_forecast_calibration.py). ⚠ CORRECTED 2026-09-26: that run's
    # "held-out Brier 0.172" reused the same outcomes for fitting and scoring
    # and ran a slightly different implementation -- a historical calibration,
    # NOT a clean held-out estimate. The honest record is the 2026 log scored
    # by score_predictions.py. Last season stays the fallback, only when the
    # blend or its calibration receipt is missing.
    strength = {}
    source = None
    blend = load("data/digby_top25_%d.json" % SEASON) or {}
    cal = load("data/forecast_calibration_2025.json") or {}
    scale = cal.get("scale_pts_per_unit")
    if scale and blend.get("all"):
        for t in blend["all"]:
            if t.get("score") is not None:
                strength[t["team"]] = float(t["score"]) * float(scale)
        source = "blend"
    if not strength:
        rating = load("data/rating_2025.json") or {}
        for t in rating.get("teams", []):
            v = t.get("adj_net_points_set")
            if v is not None:
                strength[t["team"]] = v
        source = "prior_2025"
    if not strength:
        print("no rating to stand on")
        return None

    # ⚠ PRIVATE DEFAULT FORECASTS (Cody, 2026-09-28: "switch the forecasts to the
    # new model"). When the flag file is present, the win chance comes from the
    # frozen 2026 candidate's calibrated mapping (season-aware, evidence-depth
    # aware); the set distribution is the rally model at the margin that IMPLIES
    # that chance, so every downstream field stays coherent. The previous model's
    # rows are still computed and written to a PRIVATE file so the prospective
    # scorecard keeps its head-to-head. Never on CI (no flag file there).
    cand = None
    _flag = os.path.join(REPO, "Cody", "data", "power_candidate", "DEFAULT_ON")
    _cpath = os.path.join(REPO, "Cody", "data", "power_candidate", "v2so_preview.json")
    if os.path.exists(_flag) and os.path.exists(_cpath):
        try:
            cand = json.load(open(_cpath))
            if not cand.get("win_model"):
                cand = None
        except ValueError:
            cand = None
    venues = load("data/venues_%d.json" % SEASON) or {}
    site_of = {r["game_id"]: r["site"] for r in venues.get("games", [])}
    event_of = {}
    for e in venues.get("events", []):
        for gid in e.get("game_ids", []):
            event_of[gid] = e.get("name")

    cand_rows = []
    # how many 2026 matches has each team actually played? -- the honesty column
    # ⚠ KEY BY THE HUB SPELLING, SAME AS THE LOOKUP (ultrareview 2026-09-08).
    # The counter stored "LSU New Orleans" while the fixture loop looked up
    # "New Orleans", so played_2026 read 0 for aliased teams -- and the
    # prediction log is append-only, so a wrong 0 written there is permanent.
    from reconcile_2025 import norm as _pnorm
    _hub_of = {_pnorm(k): k for k in strength}
    played = {}
    gpath = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if os.path.exists(gpath):
        seen = set()
        for line in open(gpath):
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if not isinstance(g, dict) or g.get("game_state") != "F":
                continue
            if g.get("game_id") in seen:
                continue
            seen.add(g.get("game_id"))
            for t in g.get("teams") or []:
                nm_raw = (t.get("name_short") or "").strip()
                nm = _hub_of.get(_pnorm(nm_raw), nm_raw)
                if nm:
                    played[nm] = played.get(nm, 0) + 1

    # the fitted home advantage, in points per set, from our own ridge solve
    home_adv = 0.0
    try:
        import bakeoff_2025 as B
        matches, di = B.load()
        M = B.build_metrics(matches, di)
        home_adv = M.get("_home_adv_points_per_set", 0.0) or 0.0
    except Exception:
        home_adv = 0.0

    today = datetime.date.today().isoformat()
    rows, skipped = [], 0
    for path in sorted(glob.glob(os.path.join(
            REPO, "data/raw/%d/scoreboard/*.json" % SEASON))):
        try:
            payload = json.load(open(path))
        except ValueError:
            continue
        for entry in payload.get("games") or []:
            g = entry.get("game", entry)
            gid = str(g.get("gameID") or "")
            a = (g.get("away") or {}).get("names", {}).get("short")
            h = (g.get("home") or {}).get("names", {}).get("short")
            if not a or not h:
                continue
            # ⚠ THE SCOREBOARD SPELLS TEAMS ITS OWN WAY ("LSU New Orleans "
            # with a trailing space vs the hub's "New Orleans") -- joining
            # raw names against `strength` silently dropped all 29 of New
            # Orleans' fixtures, so it had no projections, no title odds and
            # no projected final RPI. Fifth bite of this alias; the fix is
            # the same normaliser every other join uses.
            a = _hub_of.get(_pnorm(a), a.strip())
            h = _hub_of.get(_pnorm(h), h.strip())
            date = et_date(g.get("startTimeEpoch")) or os.path.basename(path)[:-5]
            if date < today:
                continue
            if a not in strength or h not in strength:
                # A team we have no 2025 rating for -- usually a non-D-I
                # opponent. Skipped rather than given a made-up strength.
                skipped += 1
                continue

            site = site_of.get(gid)
            adv = 0.0 if site == "neutral" else home_adv
            margin = (strength[h] + adv) - strength[a]      # home team's margin
            p = S.rally_p(margin)
            dist = S.match_dist(p)
            model_tag = "prev"
            if cand is not None:
                cw = cand_win(cand, h, a, site == "neutral")
                if cw is not None:
                    _cm = margin_for_win(cw); _cd = S.match_dist(S.rally_p(_cm))
                    cand_rows.append({"game_id": gid, "date": date, "time": (g.get("startTime") or "").strip(),
                                      "start_epoch": (int(g.get("startTimeEpoch")) if str(g.get("startTimeEpoch") or "").isdigit() else None),
                                      "away": a, "home": h, "home_win": round(_cd["win"], 4), "away_win": round(1.0 - _cd["win"], 4),
                                      "home_margin_per_set": round(_cm, 3), "neutral": site == "neutral", "event": event_of.get(gid),
                                      "played_2026": {"away": played.get(a, 0), "home": played.get(h, 0)},
                                      "home_dist": {"3-0": round(_cd["w30"], 4), "3-1": round(_cd["w31"], 4), "3-2": round(_cd["w32"], 4)},
                                      "away_dist": {"3-0": round(_cd["l30"], 4), "3-1": round(_cd["l31"], 4), "3-2": round(_cd["l32"], 4)},
                                      "model": "candidate:" + str(cand.get("version"))})
            rows.append({
                "game_id": gid, "date": date,
                "time": (g.get("startTime") or "").strip(),
                "start_epoch": (int(g.get("startTimeEpoch")) if str(
                    g.get("startTimeEpoch") or "").isdigit() else None),
                "away": a, "home": h,
                "home_win": round(dist["win"], 4),
                "away_win": round(1.0 - dist["win"], 4),
                "home_margin_per_set": round(margin, 3),
                "neutral": site == "neutral",
                "event": event_of.get(gid),
                "played_2026": {"away": played.get(a, 0), "home": played.get(h, 0)},
                # NAME WHOSE DISTRIBUTION THIS IS. match_dist() returns w/l
                # from the perspective of the team whose rally probability was
                # passed in -- the HOME team here. Printed as bare w30/w31/w32
                # it read as the favourite's distribution and showed
                # "Pittsburgh 98%  (3-0 0% / 3-1 1%)", which is Xavier's.
                "home_dist": {"3-0": round(dist["w30"], 4),
                              "3-1": round(dist["w31"], 4),
                              "3-2": round(dist["w32"], 4)},
                "away_dist": {"3-0": round(dist["l30"], 4),
                              "3-1": round(dist["l31"], 4),
                              "3-2": round(dist["l32"], 4)},
            })
    rows.sort(key=lambda r: (r["date"], r["time"]))
    if cand is not None:
        # PRIVATE forecasts file (read by the private page when DEFAULT_ON); the tracked
        # data/predictions_2026.json and its append-only logs stay on the previous model,
        # exactly as CI produces them, so nothing tracked changes meaning.
        cand_rows.sort(key=lambda r: (r["date"], r["time"]))
        _pp = os.path.join(REPO, "Cody", "data", "power_candidate", "predictions_2026.json")
        json.dump({"meta": {"season": SEASON, "source_tier": "DERIVED", "strength_basis": "candidate",
                            "candidate": {"version": cand.get("version"),
                                          "win_chance": "the 2026 model's calibrated mapping (season-aware, evidence-depth aware)",
                                          "set_distribution": "rally model at the margin implying that chance"},
                            "home_advantage_points_per_set": round(home_adv, 4), "fixtures": len(cand_rows),
                            "generated_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")},
                   "games": cand_rows}, open(_pp, "w"), indent=1)
        # private last-pre-match stream for the candidate (append-only, mirrors append_latest)
        _lp = os.path.join(REPO, "Cody", "data", "power_candidate", "prediction_log_latest_candidate.jsonl")
        import time as _t
        _now = _t.time(); _last = {}
        if os.path.exists(_lp):
            for _ln in open(_lp):
                try:
                    _r = json.loads(_ln); _last[_r["game_id"]] = _r.get("home_win")
                except (ValueError, KeyError):
                    continue
        with open(_lp, "a") as _fh:
            for _r in cand_rows:
                _se = _r.get("start_epoch") or 0
                if _se and _now < _se <= _now + LATEST_HORIZON_S and _last.get(_r["game_id"]) != _r["home_win"]:
                    _fh.write(json.dumps({"game_id": _r["game_id"], "date": _r["date"], "away": _r["away"], "home": _r["home"],
                                          "home_win": _r["home_win"], "neutral": _r["neutral"], "start_epoch": _se, "model": _r["model"],
                                          "issuance": "last-pre-match", "logged_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n")
    return {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "model": ("rally model from simulate_2025.py -- one pooled per-rally "
                      "probability, best-of-5 distribution derived analytically"),
            "calibration": ("rally model: Brier 0.1289 over 5,014 2025 matches "
                            "when fed the TRUE margin -- a property of the rally "
                            "model, NOT this forecast's accuracy"),
            "strength_source": (
                ("the Rankings blend (preseason projection + 2026 results, "
                 "w=n/(n+%s)) x %.2f pts/set per unit, scale fitted on 2025 "
                 "(historical overlapping-checkpoint calibration Brier %s vs %s "
                 "for last-season-only -- NOT a clean held-out estimate)" % (
                     (blend.get("meta") or {}).get("k_matches"), float(scale),
                     cal.get("heldout_brier"), cal.get("prior_only_heldout_brier")))
                if source == "blend" else
                "FALLBACK: 2025 opponent-adjusted net points/set -- the blend "
                "or its calibration receipt was missing"),
            "strength_basis": source,
            "home_advantage_points_per_set": round(home_adv, 4),
            "home_advantage_applied": "except on floors venues.py calls neutral",
            "fixtures": len(rows),
            "skipped_no_rating": skipped,
        },
        "games": rows,
    }


LOG_LATEST = os.path.join(REPO, "data", "raw", str(SEASON),
                          "prediction_log_latest.jsonl")
# how far ahead the last-pre-match stream starts recording a fixture
LATEST_HORIZON_S = 48 * 3600


def provenance():
    """Which model and which inputs produced this forecast (Phase A,
    2026-09-26). The first-issued log carried none of this, so it could never
    say which model version it was scoring. Missing pieces are recorded as
    None, never guessed."""
    import hashlib
    import subprocess
    ver = None
    try:
        ver = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10).stdout.strip() or None
        dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--",
                                "scripts"], capture_output=True, text=True,
                               timeout=10).stdout.strip()
        if ver and dirty:
            ver += "+uncommitted-scripts"
    except Exception:                                   # noqa: BLE001
        pass
    blend = load("data/digby_top25_%d.json" % SEASON) or {}
    bm = blend.get("meta") or {}
    cal = load("data/forecast_calibration_2025.json") or {}
    h = hashlib.sha256()
    for rel in ("data/digby_top25_%d.json" % SEASON,
                "data/forecast_calibration_2025.json",
                "data/venues_%d.json" % SEASON):
        fp = os.path.join(REPO, rel)
        if os.path.exists(fp):
            h.update(open(fp, "rb").read())
    return {
        "model_version": ver,
        "k": bm.get("k_matches"),
        "hit_weight": bm.get("hit_channel_weight"),
        "tau_hit": bm.get("hit_channel_tau"),
        "scale_pts_per_unit": cal.get("scale_pts_per_unit"),
        "corpus_fingerprint": bm.get("corpus_fingerprint"),
        "rating_cutoff_epoch": bm.get("rating_cutoff_epoch"),
        "blend_generated_utc": bm.get("generated_at_utc"),
        "input_hash": h.hexdigest()[:16],
    }


def append_latest(rows, prov, now=None):
    """The LAST-PRE-MATCH stream (Phase A): for fixtures starting within the
    next 48h, append a row whenever the forecast changed (or the fixture has
    none yet). Append-only; the scorer takes the latest row logged strictly
    before the stored start. Never mixed with the first-issued log."""
    import time as _t
    now = now or _t.time()
    last = {}
    if os.path.exists(LOG_LATEST):
        for line in open(LOG_LATEST):
            try:
                r = json.loads(line)
                last[r["game_id"]] = r.get("home_win")
            except (ValueError, KeyError):
                continue
    added = 0
    with open(LOG_LATEST, "a") as fh:
        for r in rows:
            ep = r.get("start_epoch")
            if not ep or not (now < ep <= now + LATEST_HORIZON_S):
                continue
            if last.get(r["game_id"]) == r["home_win"]:
                continue
            fh.write(json.dumps(dict({
                "game_id": r["game_id"], "date": r["date"],
                "away": r["away"], "home": r["home"],
                "home_win": r["home_win"], "neutral": r["neutral"],
                "start_epoch_at_issue": ep,
                "played_2026": r["played_2026"],
                "issuance": "last-pre-match",
                "logged_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, **prov)) + "\n")
            added += 1
    return added


def append_log(rows, prov=None):
    """Record the first prediction made for each fixture, once, forever."""
    seen = set()
    if os.path.exists(LOG):
        for line in open(LOG):
            try:
                seen.add(json.loads(line)["game_id"])
            except (ValueError, KeyError):
                continue
    added = 0
    if not os.path.isdir(os.path.dirname(LOG)):
        os.makedirs(os.path.dirname(LOG))
    with open(LOG, "a") as fh:
        for r in rows:
            if r["game_id"] in seen:
                continue
            fh.write(json.dumps(dict({
                "game_id": r["game_id"], "date": r["date"],
                "away": r["away"], "home": r["home"],
                "home_win": r["home_win"], "neutral": r["neutral"],
                "played_2026": r["played_2026"],
                "issuance": "first-issued",
                "logged_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, **(prov or {}))) + "\n")
            added += 1
    return added, len(seen) + added


if __name__ == "__main__":
    out = build()
    if not out:
        sys.exit(1)
    json.dump(out, open(OUT, "w"), indent=1)
    prov = provenance()
    added, total = append_log(out["games"], prov)
    print("prediction log: +%d new, %d fixtures on record" % (added, total))
    print("last-pre-match log: +%d rows" % append_latest(out["games"], prov))
    m = out["meta"]
    print("wrote %s" % OUT)
    print("  fixtures predicted : %d" % m["fixtures"])
    print("  skipped (no rating): %d" % m["skipped_no_rating"])
    print("  home advantage     : %+.3f points/set (fitted)"
          % m["home_advantage_points_per_set"])
    print("\n  next up:")
    for r in out["games"][:10]:
        fav = r["home"] if r["home_win"] >= 0.5 else r["away"]
        pct = max(r["home_win"], r["away_win"])
        tag = "  [%s]" % r["event"] if r["event"] else ("  [neutral]" if r["neutral"] else "")
        d = r["home_dist"] if r["home_win"] >= 0.5 else r["away_dist"]
        print("     %s  %-20s at %-20s  %-14s %.0f%%  (3-0 %.0f / 3-1 %.0f / 3-2 %.0f)%s"
              % (r["date"], r["away"][:20], r["home"][:20], fav[:14], 100 * pct,
                 100 * d["3-0"], 100 * d["3-1"], 100 * d["3-2"], tag))
