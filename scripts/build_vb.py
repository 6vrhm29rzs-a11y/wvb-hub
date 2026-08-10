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
_rate = json.load(open(base/"data/rating_2025.json"))
_ds_p = base/"data/data_2025.json"
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
        "sos": r["sos_rank"], "rpi": r["rpi"], "rpiRank": r["official_rpi_rank"],
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

# --- 2026 returning production + full rosters from official 2025 player stats ---
pl_path = base/"data/vb_players_2025.json"     # full per-player rosters (preferred)
rp_path = base/"data/vb_returning_2026.json"   # compact fallback (rp + top departers)
if pl_path.exists():
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
    print("no returning data yet — 2026 board stays illustrative")
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
