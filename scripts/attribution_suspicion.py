#!/usr/bin/env python3
"""Attribution-suspicion detector: H0 (feed attribution correct) vs H1
(sides swapped), per counted final, from evidence the linescore cannot see.

Authorized by Cody 2026-09-01 ("build the permutation detector"); design
from the trust-layer consult (docs/trust_layer_consult_2026-09-01.md) and
a second consult the same night whose rules are load-bearing here:

- V1 IS AN UNWEIGHTED FORENSIC FEATURE TABLE. Three known positives cannot
  fit weights; components VOTE (SUPPORTS_H0 / SUPPORTS_H1 / UNAVAILABLE)
  with their measured values logged, and the queue ranks by vote count.
  The queue rule is a stated display/ranking heuristic, never a truth
  claim (R1).
- COMPARATIVE ERROR, NOT EXACT MATCH: feed records include exhibitions and
  non-D-I games ours exclude, so a component asks which hypothesis fits
  BETTER, and by how much. A missing input is UNAVAILABLE, never a pass.
- LEAVE-ONE-OUT: hypotheses are computed from the RAW pre-correction
  attribution, while every season-graph reference uses the CORRECTED
  corpus with the candidate game removed -- otherwise a previously
  corrected inversion proves its own H1 through the corrected graph.
- ADJUDICATIONS LIVE APART: data/raw/2026/attribution_adjudications.json
  is the hand-labelled truth file; features never absorb labels, so in six
  weeks weights can be fitted against frozen features without leakage.
- THE DETECTOR MUTATES NOTHING: it writes its artifact and review-queue
  candidates. No correction, no counting change, no state lift.

Components:
  feed_record_fit   the feed's own pre-match record strings vs OUR replayed
                    pre-match D-I records, under H0 and swapped
  box_roster_fit    each side's box names vs each roster (the SMU signature:
                    own 0.00 / other 1.00 on both sides)
  record_continuity later record_at_time observations vs the trajectory each
                    hypothesis implies
  school_verification  the nightly verifier's verdict for this gid
Context (recorded, never voting in v1): neutral site, nominal home is not
the venue host -- the pattern all three known inversions share.
"""
import datetime
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_counts as SC  # noqa: E402

SEASON = 2026
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(REPO, "data", "attribution_suspicion_%d.json" % SEASON)
ADJUDICATIONS = os.path.join(RAW, "attribution_adjudications.json")
MODEL_VERSION = "v1.1-unweighted"

# v1 reliability gate for the box component -- a RELIABILITY floor for
# voting eligibility, stated as such, never a truth threshold (R1)
BOX_MIN_TOTAL = 6
BOX_MIN_SIDE = 3


def _load_json(p, default):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return default


def _rec_str(t):
    m = re.search(r"\((\d+)-(\d+)\)", str(t.get("record_at_time") or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _namekey(*parts):
    return re.sub(r"[^a-z]", "", " ".join(p or "" for p in parts).lower())


def load_corpora():
    games = []
    with open(os.path.join(RAW, "games.jsonl")) as f:
        for line in f:
            try:
                games.append(json.loads(line))
            except ValueError:
                continue
    raw = {str(g.get("game_id")): g for g in SC.resolve(games)}
    cls = SC.classify(games, SEASON)
    corr = SC.corrections(SEASON)
    corrected = {}
    for gid, g in raw.items():
        if cls.get(gid) != "ok" or g.get("game_state") != "F":
            continue
        corrected[gid] = SC.apply_correction(g, corr)
    return raw, corrected


def team_results(corrected):
    """team_id -> [(epoch, gid, won)] from the CORRECTED corpus."""
    out = defaultdict(list)
    for gid, g in corrected.items():
        ep = g.get("start_time_epoch")
        if not ep:
            continue
        for t in g.get("teams") or []:
            out[str(t.get("team_id"))].append(
                (ep, gid, bool(t.get("is_winner"))))
    for v in out.values():
        v.sort()
    return out


def pre_record(results, tid, epoch, exclude_gid):
    w = l = 0
    for ep, gid, won in results.get(tid, []):
        if ep >= epoch or gid == exclude_gid:
            continue
        w, l = (w + 1, l) if won else (w, l + 1)
    return w, l


def feed_record_fit(g, results, gid):
    ts = g.get("teams") or []
    fa, fb = _rec_str(ts[0]), _rec_str(ts[1])
    if fa is None or fb is None:
        return {"available": False, "vote": "UNAVAILABLE",
                "why": "feed record missing or unparseable"}
    ep = g.get("start_time_epoch") or 0
    ta = pre_record(results, str(ts[0].get("team_id")), ep, gid)
    tb = pre_record(results, str(ts[1].get("team_id")), ep, gid)
    err = lambda f, t: abs(f[0] - t[0]) + abs(f[1] - t[1])  # noqa: E731
    h0 = err(fa, ta) + err(fb, tb)
    h1 = err(fa, tb) + err(fb, ta)
    vote = "SUPPORTS_H1" if h1 < h0 else (
        "SUPPORTS_H0" if h0 < h1 else "UNINFORMATIVE")
    return {"available": True, "feed": [fa, fb], "ours": [ta, tb],
            "h0_error": h0, "h1_error": h1, "delta_h1_better": h0 - h1,
            "vote": vote}


def box_roster_fit(gid, g, boxes, roster_keys, id2n):
    box = boxes.get(gid)
    if not box:
        return {"available": False, "vote": "UNAVAILABLE",
                "why": "no box rows held"}
    by = defaultdict(list)
    for x in box.get("rows") or []:
        k = _namekey(x.get("first"), x.get("last"))
        if k:
            by[str(x.get("team_id"))].append(k)
    tids = [str(t.get("team_id")) for t in (g.get("teams") or [])]
    if len(tids) != 2 or any(t not in by for t in tids):
        return {"available": False, "vote": "UNAVAILABLE",
                "why": "box sides do not match the game's teams"}
    ra = roster_keys.get(id2n.get(tids[0]) or "") or set()
    rb = roster_keys.get(id2n.get(tids[1]) or "") or set()
    if not ra or not rb:
        return {"available": False, "vote": "UNAVAILABLE",
                "why": "roster missing for a side"}
    na, nb = by[tids[0]], by[tids[1]]
    if len(na) + len(nb) < BOX_MIN_TOTAL or min(len(na), len(nb)) \
            < BOX_MIN_SIDE:
        return {"available": False, "vote": "UNAVAILABLE",
                "why": "below the v1 reliability gate (%d+%d names)"
                % (len(na), len(nb))}
    fit = lambda names, rk: round(  # noqa: E731
        sum(1 for n in names if n in rk) / len(names), 3)
    h0 = [fit(na, ra), fit(nb, rb)]
    h1 = [fit(na, rb), fit(nb, ra)]
    gain = round(min(h1) - max(h0), 3)
    unmatched = [n for n in na if n not in ra][:4] + \
                [n for n in nb if n not in rb][:4]
    vote = "SUPPORTS_H1" if (min(h1) > max(h0)) else (
        "SUPPORTS_H0" if min(h0) > max(h1) else "UNINFORMATIVE")
    return {"available": True, "eligible_rows": len(na) + len(nb),
            "h0": h0, "h1": h1, "fit_gain": gain,
            "unmatched_sample": unmatched[:6], "vote": vote}


def record_continuity(g, gid, raw, results):
    """Later record_at_time observations vs each hypothesis' trajectory."""
    ep = g.get("start_time_epoch") or 0
    ts = g.get("teams") or []
    if len(ts) != 2:
        return {"available": False, "vote": "UNAVAILABLE"}
    later = defaultdict(list)   # tid -> [(epoch, (w, l))]
    for og in raw.values():
        oep = og.get("start_time_epoch") or 0
        if oep <= ep or str(og.get("game_id")) == gid:
            continue
        for t in og.get("teams") or []:
            r = _rec_str(t)
            if r:
                later[str(t.get("team_id"))].append((oep, r))
    h0e = h1e = 0
    n_obs = 0
    for i, t in enumerate(ts):
        tid = str(t.get("team_id"))
        won_h0 = bool(t.get("is_winner"))
        for oep, obs in sorted(later.get(tid, []))[:3]:
            base = pre_record(results, tid, oep, gid)
            n_obs += 1
            for won, acc in ((won_h0, "h0"), (not won_h0, "h1")):
                w, l = (base[0] + 1, base[1]) if won \
                    else (base[0], base[1] + 1)
                d = abs(obs[0] - w) + abs(obs[1] - l)
                if acc == "h0":
                    h0e += d
                else:
                    h1e += d
    if not n_obs:
        return {"available": False, "vote": "UNAVAILABLE",
                "why": "no later feed record observations yet"}
    vote = "SUPPORTS_H1" if h1e < h0e else (
        "SUPPORTS_H0" if h0e < h1e else "UNINFORMATIVE")
    return {"available": True, "n_observations": n_obs,
            "h0_error": h0e, "h1_error": h1e, "vote": vote}


def school_verification(gid):
    import glob
    v = None
    for rp in sorted(glob.glob(os.path.join(
            REPO, "data", "result_verification_*.json"))):
        doc = _load_json(rp, {})
        for m in doc.get("matches") or []:
            if str(m.get("gid")) == gid:
                v = m.get("verdict")
    if not v:
        return {"available": False, "vote": "UNAVAILABLE",
                "why": "not yet verified"}
    vote = ("SUPPORTS_H1" if v in ("CONTRADICTED_BOTH", "CONTRADICTED_ONE",
                                   "SCHOOL_CONFLICT")
            else "SUPPORTS_H0" if v in ("VERIFIED_BOTH", "CORROBORATED_ONE")
            else "UNINFORMATIVE")
    return {"available": True, "verdict": v, "vote": vote}


def modal_venues(corrected):
    from collections import Counter
    c = defaultdict(Counter)
    for g in corrected.values():
        v = (g.get("location") or {}).get("venue")
        if not v:
            continue
        for t in g.get("teams") or []:
            if t.get("is_home"):
                c[str(t.get("team_id"))][v] += 1
    return {tid: cnt.most_common(1)[0][0] for tid, cnt in c.items() if cnt}


def build():
    raw, corrected = load_corpora()
    results = team_results(corrected)
    boxes = {}
    with open(os.path.join(RAW, "playerbox.jsonl")) as f:
        for line in f:
            try:
                r = json.loads(line)
                boxes[str(r.get("game_id"))] = r
            except ValueError:
                continue
    d = _load_json(os.path.join(REPO, "data", "data_%d.json" % SEASON), {})
    id2n = {str(t["team_id"]): t["name_short"] for t in d.get("teams") or []}
    R = _load_json(os.path.join(RAW, "rosters_2026.json"), {})
    roster_keys = {}
    for team, v in (R.get("teams") or {}).items():
        ks = set(_namekey(p.get("name_raw")) for p in (v.get("players")
                                                       or []))
        ks.discard("")
        if ks:
            roster_keys[team] = ks
    modal = modal_venues(corrected)
    adjud = _load_json(ADJUDICATIONS, {}).get("labels") or {}

    rows = []
    for gid, g in sorted(corrected.items()):
        graw = raw[gid]      # hypotheses from RAW pre-correction attribution
        ts = graw.get("teams") or []
        if len(ts) != 2:
            continue
        comps = {
            "feed_record_fit": feed_record_fit(graw, results, gid),
            "box_roster_fit": box_roster_fit(gid, graw, boxes,
                                             roster_keys, id2n),
            "record_continuity": record_continuity(graw, gid, raw, results),
            "school_verification": school_verification(gid),
        }
        home = next((t for t in ts if t.get("is_home")), None)
        venue = (graw.get("location") or {}).get("venue")
        ctx = {
            "venue": venue,
            "nominal_home_is_venue_host": (
                None if not (home and venue and
                             str(home.get("team_id")) in modal)
                else modal[str(home.get("team_id"))] == venue),
        }
        n_h1 = sum(1 for c in comps.values() if c.get("vote")
                   == "SUPPORTS_H1")
        n_av = sum(1 for c in comps.values() if c.get("available"))
        # v1.1 TWO-TIER QUEUE (consult, 2026-09-02, calibrated on night
        # one: double-vote candidates went 13/13 true; record_continuity
        # ALONE at error-delta 1 produced ~7 false positives). Review
        # thresholds, stated as such -- chosen to suppress the OBSERVED
        # delta-1 noise, never a truth claim:
        #   primary    n_h1_votes >= 2
        #   secondary  a single record component only at delta >= 2;
        #              box_roster_fit alone only on an unmistakable
        #              reversal (fit_gain >= 0.5, reliability-gated)
        # a single H1 vote below its gate stays in the artifact as
        # watch: true -- preserved for training, not queued for a human.
        def _delta(c, k):
            return c.get(k) if c.get("available") else None
        frf, rc, brf = (comps["feed_record_fit"],
                        comps["record_continuity"],
                        comps["box_roster_fit"])
        strong = (
            (frf.get("vote") == "SUPPORTS_H1"
             and (frf.get("delta_h1_better") or 0) >= 2)
            or (rc.get("vote") == "SUPPORTS_H1"
                and ((rc.get("h0_error") or 0)
                     - (rc.get("h1_error") or 0)) >= 2)
            or (brf.get("vote") == "SUPPORTS_H1"
                and (brf.get("fit_gain") or 0) >= 0.5))
        queued = n_h1 >= 2 or strong
        row = {
            "gid": gid, "epoch": graw.get("start_time_epoch"),
            "teams": [id2n.get(str(t.get("team_id")),
                               t.get("name_short")) for t in ts],
            "already_corrected": bool(corrected[gid]
                                      .get("result_corrected")),
            "context": ctx, "components": comps,
            "n_h1_votes": n_h1, "n_available": n_av,
            "queued": queued,
            "watch": (not queued) and n_h1 >= 1,
            "adjudication": adjud.get(gid) or None,
        }
        rows.append(row)

    # ⚠ FREEZE THE FIRST SCORE (consult, 2026-09-02): the artifact is
    # regenerated nightly, and later corrections, later record
    # observations, better rosters and arriving school verification all
    # mutate current features -- training on those leaks the answer. Each
    # gid keeps the components EXACTLY as first measured, immutable; the
    # eventual fit joins first_score to human adjudications, never
    # current features. (school_verification stays out of any future fit
    # entirely -- it is the labelling mechanism, and a detector trained on
    # it would only ever rediscover the verifier.)
    prev = _load_json(OUT, {})
    prev_first = {m.get("gid"): m for m in prev.get("matches") or []
                  if m.get("first_score")}
    now_utc = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in rows:
        old = prev_first.get(r["gid"])
        if old:
            r["first_scored_utc"] = old["first_scored_utc"]
            r["first_feature_version"] = old.get("first_feature_version",
                                                 old.get("feature_version"))
            r["first_score"] = old["first_score"]
        else:
            r["first_scored_utc"] = now_utc
            r["first_feature_version"] = MODEL_VERSION
            r["first_score"] = {
                "components": r["components"],
                "n_h1_votes": r["n_h1_votes"],
                "school_verification_available_at_scoring":
                    r["components"]["school_verification"].get("available",
                                                              False),
            }

    rows.sort(key=lambda r: (-r["n_h1_votes"], r["gid"]))
    queued = [r for r in rows if r["queued"]]
    json.dump({
        "model_version": MODEL_VERSION,
        "generated_utc": datetime.datetime.utcnow()
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queue_rule": {"description":
                       "any component voting SUPPORTS_H1 queues the match "
                       "for human review; ranking is by vote count. A "
                       "display/ranking heuristic only -- not a truth "
                       "claim, and nothing here corrects or counts."},
        "n_finals": len(rows), "n_queued": len(queued),
        "matches": rows}, open(OUT, "w"), indent=1)
    print("attribution suspicion: %d finals scored, %d queued -> %s"
          % (len(rows), len(queued), os.path.relpath(OUT, REPO)))
    for r in queued[:20]:
        votes = {k: v["vote"] for k, v in r["components"].items()
                 if v.get("vote") == "SUPPORTS_H1"}
        print("  %s %s v %s  H1-votes=%d %s%s"
              % (r["gid"], r["teams"][0], r["teams"][1], r["n_h1_votes"],
                 list(votes), " [already corrected]"
                 if r["already_corrected"] else ""))

    # review-queue candidates (merged, never overwritten; NEVER corrections)
    qp = os.path.join(RAW, "result_review_queue.json")
    q = _load_json(qp, {})
    added = 0
    for r in queued:
        if r["already_corrected"] or r.get("adjudication"):
            continue
        key = "attr-" + r["gid"]
        if key in q:
            continue
        q[key] = {"gid": r["gid"], "kind": "attribution_suspicion",
                  "teams": r["teams"], "n_h1_votes": r["n_h1_votes"],
                  "components": {k: v for k, v in r["components"].items()
                                 if v.get("vote") == "SUPPORTS_H1"},
                  "queued_utc": datetime.datetime.utcnow()
                  .strftime("%Y-%m-%dT%H:%M:%SZ")}
        added += 1
    if added:
        json.dump(q, open(qp, "w"), indent=1)
        print("⚠ %d new review candidate(s) -> %s (a human adjudicates; "
              "nothing is corrected)" % (added, os.path.relpath(qp, REPO)))
    return rows


if __name__ == "__main__":
    build()
