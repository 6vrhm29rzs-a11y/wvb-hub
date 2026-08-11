#!/usr/bin/env python3
"""Inject vb2025.json into vb_template.html -> vb_dashboard.html (self-contained)."""
import json, pathlib
base = pathlib.Path(__file__).resolve().parent.parent
data = json.load(open(base/"data/vb2025.json"))              # bracket + results feed
# Phase 3: the rankings view now runs on the real 348-team rating
# (RPI + opponent-adjusted net points/set, weights FITTED on 2025), not the
# 40-team hand-weighted sample. Rebuild inputs first:
#     python3 scripts/build_dataset.py && python3 scripts/rating_2025.py
# `fitted: True` tells the template to use the fitted composite and leave the
# hand-weighted SOS dial inert -- otherwise the dial silently overwrites it.
import os as _os
_SEASON = int(_os.environ.get("WVB_SEASON", "2025"))
_rate_p = base/("data/rating_%d.json" % _SEASON)
if not _rate_p.exists():
    # No rating yet (pre-season). Keep the last good dashboard rather than
    # replacing it with an empty one.
    print("no data/rating_%d.json yet -- leaving output/vb_dashboard.html untouched" % _SEASON)
    raise SystemExit(0)
_rate = json.load(open(_rate_p))
_ds_p = base/("data/data_%d.json" % _SEASON)
_tot  = {}
if _ds_p.exists():
    for t in json.load(open(_ds_p))["teams"]:
        st = t.get("season_totals") or {}
        if st.get("sets"):
            _tot[t["name_short"]] = st
def _per(nm, key):
    st = _tot.get(nm)
    if not st or not st.get("sets") or st.get(key) is None: return None
    return round(st[key] / float(st["sets"]), 3)
def _blocks(nm):
    st = _tot.get(nm)
    if not st or not st.get("sets"): return None
    bs, ba = st.get("block_solos") or 0, st.get("block_assists") or 0
    return round((bs + ba / 2.0) / float(st["sets"]), 3)
model = {
    "fitted": True,
    "generated_at": _rate["meta"].get("generated_at_utc"),
    "data_through": _rate["meta"].get("data_through"),
    "matches_in_data": _rate["meta"].get("matches_in_data"),
    "asof": "final 2025 (through Dec 21, 2025)",
    "sos_weight": 2,
    "weights": _rate["meta"]["weights"],
    "teams": [{
        "team": r["team"], "conf": r["conference"],
        "record": ("%d-%d" % (r["wins"], r["losses"])) if r["wins"] is not None else None,
        "composite": r["composite"], "delta": r["delta_vs_rpi"],
        "pps": r["adj_net_points_set"],
        "kps": _per(r["team"], "kills"), "aps": _per(r["team"], "aces"),
        "bps": _blocks(r["team"]),
        # OFFENSE-ONLY points/set (kills + aces + blocks), kept SEPARATE from
        # `pps`. `pps` now carries opponent-adjusted NET points/set, which is a
        # differential and can be negative; the 2026 returning-production view
        # and the team tracker both mean the offensive quantity and multiply by
        # a returning share, so feeding them a differential produces nonsense
        # (a real bug: "Ark.-Pine Bluff 2025 Pts/Set -14.31").
        "opps": (lambda k, a, b: round(k + a + b, 2)
                 if None not in (k, a, b) else None)(
            _per(r["team"], "kills"), _per(r["team"], "aces"), _blocks(r["team"])),
        "sos": r["sos_rank"], "rpi": r["rpi"], "rpiRank": r["official_rpi_rank"],
        "gp": r["games_played"], "lowconf": r["low_confidence"],
        "t25": r["resume"]["vs_rpi_top25"], "t50": r["resume"]["vs_rpi_top50"],
        "ncRpiRank": r["official_rpi_rank"],
    } for r in _rate["teams"]],
}

# --- merge OFFICIAL records + RPI from stats.ncaa.org (final 2025 nitty-gritty) by team name ---
off = json.load(open(base/"data/vb_ncaa_official.json"))["teams"]
merged = 0
for t in model["teams"]:
    o = off.get(t["team"])
    if o:
        t["record"] = o["wl"]
        t["rpi"] = o["rpi"]
        t["rpiRank"] = o["rpiRank"]
        t["ncRpiRank"] = o.get("ncRpiRank")
        merged += 1
model["official_asof"] = "records + RPI: official NCAA final 2025 (stats.ncaa.org, thru 12/21/2025)"
model["official_source"] = "https://stats.ncaa.org/selection_rankings/nitty_gritties/47691"
print("merged OFFICIAL record+RPI into %d of %d model teams" % (merged, len(model["teams"])))

# --- 2026 returning production: REAL 2026 rosters x 2025 production ---------
# PREFERRED over the two paths below, and a different QUESTION from the one they
# answered. They inferred departure from class year (Sr/Gr graduate), across a
# 40-team sample. This reads the actual 2026 roster published by each school and
# asks whether last season's producer is on it -- which also captures transfers
# out, early departures and medical retirements that a class-year rule calls
# "returning".
#
# R4 APPLIES: the number under "Returning %" changes meaning here, so the method
# text on the page changes with it. `returning_method` carries that to the
# template; do not set the number without it.
rj_path = base/"data/returning_2026.json"
rosters_path = base/"data/raw/2026/rosters_2026.json"
_wired = False
if rj_path.exists() and rosters_path.exists():
    _join = json.load(open(rj_path))["teams"]
    # team NAMES are not a safe join key across ncaa.com endpoints -- go via
    # team_id, the only stable identifier (see CLAUDE.md).
    _rmeta = json.load(open(rosters_path))["teams"]
    _by_id = {}
    for _tname, _m in _rmeta.items():
        _rec = _join.get(_tname)
        if _m.get("team_id") and _rec and _rec.get("returning") is not None:
            _by_id[str(_m["team_id"])] = _rec
    # Names differ BETWEEN ncaa.com endpoints for the same school -- the rating
    # payload says "New Orleans" where the dataset says "LSU New Orleans " (a
    # 2025 rebrand, trailing space and all). Reuse the reconciler's normaliser
    # and alias map rather than adding a second one here; a private copy would
    # drift from it silently, and this school would just go missing again.
    import sys as _sys
    _sys.path.insert(0, str(base/"scripts"))
    from reconcile_2025 import norm as _norm
    _name_to_id = {}
    if _ds_p.exists():
        for _t in json.load(open(_ds_p))["teams"]:
            if _t.get("team_id"):
                _name_to_id[_norm(_t["name_short"])] = str(_t["team_id"])
    _n = 0
    for t in model["teams"]:
        rec = _by_id.get(_name_to_id.get(_norm(t["team"]), ""))
        if not rec:
            continue
        ret_pts = sum((p.get("pts") or 0) for p in rec["returning"])
        dep_pts = sum((p.get("pts") or 0) for p in rec["departed"])
        total = ret_pts + dep_pts
        if total <= 0:
            continue          # no 2025 scoring at all -> em dash, not a zero
        t["ret2026"] = round(ret_pts / total, 3)
        t["teamPts"] = round(total, 1)
        dep = sorted(rec["departed"], key=lambda p: -(p.get("pts") or 0))
        t["dep1"] = "%s (%s)" % (dep[0]["name"], dep[0]["pts"]) if dep else None
        t["dep2"] = "%s (%s)" % (dep[1]["name"], dep[1]["pts"]) if len(dep) > 1 else None
        t["roster"] = (
            [{"n": p["name"], "yr": p.get("class") or "", "pos": p.get("pos") or "",
              "pts": p.get("pts") or 0, "k": p.get("kills") or 0,
              "a": p.get("aces") or 0, "b": p.get("blocks") or 0, "ret": True}
             for p in sorted(rec["returning"], key=lambda p: -(p.get("pts") or 0))]
            + [{"n": p["name"], "yr": "", "pos": p.get("pos") or "",
                "pts": p.get("pts") or 0, "k": p.get("kills") or 0,
                "a": p.get("aces") or 0, "b": p.get("blocks") or 0, "ret": False}
               for p in dep])
        # Roster players whose 2025 production could not be resolved. Their
        # production, if any, is NOT attributed -- so the share is conservative,
        # never inflated. Surfaced per team rather than buried in a total.
        t["unres2026"] = len(rec.get("unresolved") or [])
        _n += 1
    if _n:
        _wired = True
        model["returning_method"] = "roster"
        model["returning_source"] = (
            "2026 rosters published by each school (OFFICIAL) x 2025 per-player "
            "production from ncaa.com box scores (OFFICIAL); the join is DERIVED")
        print("attached ROSTER-BASED returning%% for %d of %d model teams"
              % (_n, len(model["teams"])))

# --- legacy 40-team graduation-based path (only if the real join is absent) ---
pl_path = base/"data/vb_players_2025.json"     # full per-player rosters (preferred)
rp_path = base/"data/vb_returning_2026.json"   # compact fallback (rp + top departers)
if _wired:
    pass                       # real join already wired; do not overwrite it
elif pl_path.exists():
    pdata = json.load(open(pl_path)).get("teams", {})
    n = 0
    for t in model["teams"]:
        pt = pdata.get(t["team"])
        if pt and pt.get("players"):
            players = sorted(pt["players"], key=lambda p: -p["pts"])
            t["ret2026"] = pt["rp"]; t["teamPts"] = pt.get("teamPts")
            dep = [p for p in players if not p["ret"]]
            t["dep1"] = "%s (%s)" % (dep[0]["n"], dep[0]["pts"]) if dep else None
            t["dep2"] = "%s (%s)" % (dep[1]["n"], dep[1]["pts"]) if len(dep) > 1 else None
            t["roster"] = [{"n": p["n"], "yr": p["yr"], "pos": p.get("pos", ""), "pts": p["pts"],
                            "k": p.get("k", 0), "a": p.get("a", 0),
                            "b": round(p.get("bs", 0) + p.get("ba", 0), 1), "ret": p["ret"]} for p in players]
            n += 1
    model["returning_source"] = "official 2025 player stats (stats.ncaa.org season_to_date_stats); graduation-based (Sr/Gr depart)"
    print("attached FULL rosters + returning%% for %d of %d model teams" % (n, len(model["teams"])))

    # --- transfers (NON-OFFICIAL tracker), if compiled ---
    tr_path = base/"data/vb_transfers_2026.json"
    if tr_path.exists():
        tr = json.load(open(tr_path)); trT = tr.get("teams", {})
        def norm(s): return " ".join((s or "").lower().replace(".", "").split())
        def prev_pts(school, name):
            pt = pdata.get(school)                     # only if the prev school is one of our 40
            if not pt: return None
            nm = norm(name)
            for p in pt["players"]:
                if norm(p["n"]) == nm: return p["pts"]
            ln = nm.split()[-1] if nm else ""
            for p in pt["players"]:
                pn = norm(p["n"])
                if ln and pn.split()[-1] == ln and pn[:1] == nm[:1]: return p["pts"]
            return None
        applied = 0
        for t in model["teams"]:
            info = trT.get(t["team"]); t["xout"] = []; t["xin"] = []
            if not info or not t.get("roster"): continue
            applied += 1
            byname = {norm(p["n"]): p for p in t["roster"]}
            for o in (info.get("out") or []):
                nm = o.get("n", ""); key = norm(nm); p = byname.get(key)
                if not p and key:
                    ln = key.split()[-1]
                    for pp in t["roster"]:
                        pn = norm(pp["n"])
                        if pn.split()[-1] == ln and pn[:1] == key[:1]: p = pp; break
                if p: p["xfer"] = True
                t["xout"].append({"n": nm, "to": o.get("to"), "pts": p["pts"] if p else None, "wasRet": bool(p and p["ret"])})
            for i in (info.get("in") or []):
                if norm(i.get("n", "")) in byname: continue   # already on 2025 roster -> stale, not a 2026 incoming
                t["xin"].append({"n": i.get("n"), "from": i.get("from"), "pts": prev_pts(i.get("from"), i.get("n"))})
            teamPts = t.get("teamPts") or sum(p["pts"] for p in t["roster"]) or 1
            retNet = sum(p["pts"] for p in t["roster"] if p["ret"] and not p.get("xfer"))
            t["ret2026net"] = round(retNet / teamPts, 3)
            t["inPts"] = round(sum(x["pts"] for x in t["xin"] if x["pts"]), 1)
        model["transfers_source"] = tr.get("source"); model["transfers_asof"] = tr.get("asof"); model["transfers_conf"] = tr.get("confidence")
        print("applied transfers to %d teams" % applied)
    else:
        print("no vb_transfers_2026.json yet — returning%% is graduation-only")
elif rp_path.exists():
    rp = json.load(open(rp_path)).get("teams", {})
    for t in model["teams"]:
        r = rp.get(t["team"])
        if r and r.get("rp") is not None:
            t["ret2026"] = r["rp"]; t["dep1"] = r.get("dep1"); t["dep2"] = r.get("dep2")
    print("merged compact returning%% (no full rosters)")
else:
    print("no returning data yet — 2026 board shows dashes, nothing estimated")
# --- team logos (embedded data URIs), if downloaded ---
lg_path = base/"data/vb_logos.json"
if lg_path.exists():
    L = json.load(open(lg_path))["teams"]
    model["logos"] = {t: v.get("bgl") for t, v in L.items() if v.get("bgl")}  # single lookup map; template reads MODEL.logos
    print("attached %d team logos" % len(model["logos"]))

tpl = (base/"output/vb_template.html").read_text()
def blob(o): return json.dumps(o, ensure_ascii=False).replace("</", "<\\/")  # guard </script>
assert "__DATA__" in tpl and "__MODEL__" in tpl, "no injection point"
out = tpl.replace("__DATA__", blob(data)).replace("__MODEL__", blob(model))
assert "__DATA__" not in out and "__MODEL__" not in out
(base/"output/vb_dashboard.html").write_text(out)
print("wrote output/vb_dashboard.html  bytes=%d  model_teams=%d" % (len(out), len(model["teams"])))

# CACHE BUSTING. GitHub Pages serves with cache-control: max-age=600 and the CDN
# edge holds the object that long, so a freshly deployed fix keeps serving OLD
# bytes for up to ten minutes -- long enough that a phone check tests the
# previous build and reports the fix as broken. That is exactly what happened.
# index.html redirects with a content hash in the query, so every new build is a
# new URL to both the CDN and Safari.
import hashlib, re as _re
_ver = hashlib.sha1(out.encode("utf-8")).hexdigest()[:12]
_idx = base / "index.html"
_html = _idx.read_text()
_html = _re.sub(r"output/vb_dashboard\.html(\?v=[0-9a-f]+)?",
                "output/vb_dashboard.html?v=" + _ver, _html)
_idx.write_text(_html)
print("index.html -> output/vb_dashboard.html?v=%s" % _ver)
