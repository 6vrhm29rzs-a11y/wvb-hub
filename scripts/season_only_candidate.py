#!/usr/bin/env python3
"""LOCAL-ONLY, PRIVATE: refreeze the season-only POWER candidate (Cody,
2026-09-27: "keep it as comparison ... go ahead with 1"). Runs in the local
refresh after digby_top25.py, so the candidate uses EXACTLY Current POWER's
results cut-off (data_through_epoch). Writes only
Cody/data/power_candidate/v2so_preview.json. Never gates the build: on any
failure the previous frozen file stays and the page shows its own cut-off.
The model code lives in Cody/coordination/research/ (gitignored); absent in CI,
this exits 0 and does nothing."""
import json, os, subprocess, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(REPO, "Cody", "coordination", "research", "TONIGHT-BUILDER-HANDOFF", "work", "c066.py")
DIR = os.path.join(REPO, "Cody", "data", "power_candidate")
LAM = "8.0"      # RULE-067 chose 1.0 one-at-a-time; RULE-101 joint -> 2.0; RULE-104 range extension -> 8.0 (c104_eval.json)
KE = "0.15"      # RULE-069 chose 0.25; RULE-101 joint re-selection -> 0.15. (The STRUCT fit reads its knobs from c093; these must match it.)
PP = "ppa5"      # RULE-087 3-part returning start (RULE-078 who-plays) + RULE-093 conference/opp-uncertainty + RULE-095 last-season TEAM results (Cody 2026-09-28: "Go with B")
HT = ""          # height REMOVED by Cody 2026-09-28 ("Height only matters for front row but isn't necessarily correlated to skill"); RULE-086 kept as a record
W0 = "0.5"       # normalized recency ramp start weight: Cody's DESIGN CHOICE 2026-09-27 (RULE-071 showed it neutral); revisit later in the season


def input_identity(ep, repo=None):
    """073 #1: the identity of what the candidate fit actually READS, so a
    corrected score, a changed eligibility or a site correction at an UNCHANGED
    cut-off still forces a refit. Inputs (from c093/c066/v2): data/data_2026.json
    games up to the cut-off (counting flags, winner, lines, teams, home flag),
    their box scores (earned/hitting channels), the effective site per game
    (venues_2026.json -- the no-venue set and home edge), the conference
    registry + overrides, the 2025 dataset and returning file (start parts), and
    the cut-off itself. Timestamps never enter. Returns (digest, manifest)."""
    import hashlib
    repo = repo or REPO
    man = {}

    def h(obj):
        return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def fbytes(rel):
        p = os.path.join(repo, rel)
        if not os.path.exists(p):
            return "absent"
        if rel.endswith(".json"):
            # content, not bytes: data_2025.json is rebuilt every full cycle with a
            # fresh generated_at_utc, which would otherwise force a refit each time
            try:
                return h(_strip_ts(json.load(open(p, encoding="utf-8"))))
            except ValueError:
                pass
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]

    try:
        doc = json.load(open(os.path.join(repo, "data", "data_2026.json")))
    except (IOError, ValueError):
        doc = {"games": []}
    keep = ("game_id", "state", "winner_team_id", "linescores", "duplicate_of",
            "result_corrected", "result_corrected_kind", "under_review", "championship")
    games, gids = [], set()
    for g in doc.get("games") or []:
        if (g.get("start_time_epoch") or 0) > ep:
            continue
        gids.add(str(g.get("game_id")))
        games.append(dict({k: g.get(k) for k in keep},
                          teams=[(str(t.get("team_id")), bool(t.get("is_home")), t.get("sets_won"),
                                  t.get("is_winner")) for t in g.get("teams") or []]))
    games.sort(key=lambda x: str(x["game_id"]))
    man["games"] = h(games)
    man["games_n"] = len(games)
    box = {}
    bp = os.path.join(repo, "data", "raw", "2026", "boxscores.jsonl")
    if os.path.exists(bp):
        for line in open(bp, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            gid = str(r.get("game_id") or r.get("gid") or "")
            if gid in gids:
                box[gid] = _strip_ts(r)          # one record per game, last wins
    man["boxscores"] = h(sorted(box.items()))
    try:
        v = json.load(open(os.path.join(repo, "data", "venues_2026.json")))
        man["sites"] = h(sorted((str(x.get("game_id")), x.get("site")) for x in v.get("games") or []
                                if str(x.get("game_id")) in gids))
    except (IOError, ValueError):
        man["sites"] = "absent"
    for rel in ("data/raw/2026/conferences_2026.json", "data/raw/2026/conference_overrides.json",
                "data/data_2025.json", "data/returning_2026.json"):
        man[rel] = fbytes(rel)
    man["cutoff_epoch"] = ep
    return h(man), man


def _strip_ts(o):
    if isinstance(o, dict):
        return dict((k, _strip_ts(x)) for k, x in o.items()
                    if not any(t in k.lower() for t in ("fetched", "retriev", "_utc", "captured", "generated")))
    if isinstance(o, list):
        return [_strip_ts(x) for x in o]
    return o


def settings_match(cur):
    return (str(cur.get("lambda")) == LAM and str(cur.get("earned_weight")) == KE and str(cur.get("ramp_w0")) == W0
            and cur.get("ballast_active") is True and cur.get("height_term") is False
            and len(cur.get("start_parts") or []) == 4 and bool(cur.get("structure"))
            and cur.get("fit_used") == "c093.fit_both+T" and cur.get("fifth_set_weight") == 0.5
            and cur.get("opp_uncertainty_s0") == 96 and bool(cur.get("theta_sd")))


def main():
    global DIR
    if not os.path.exists(WORK):
        print("season-only candidate: research code absent (CI/fresh checkout) -- skipped")
        return 0
    meta = json.load(open(os.path.join(REPO, "data", "digby_top25_2026.json"))).get("meta") or {}
    ep = meta.get("data_through_epoch")
    if not ep:
        print("season-only candidate: Current POWER has no data_through_epoch -- skipped")
        return 0
    out = os.path.join(REPO, "Cody", "data", "power_candidate", "v2so_preview.json")
    # B3: freeze the completed week from the file as it stands BEFORE this cycle
    # can add later results to it
    weekly_freeze(out)
    if "--weekly-only" in sys.argv:
        return 0
    ident, manifest = input_identity(ep)
    try:
        cur = json.load(open(out))
        # 073 #1: skip only when the cut-off, the settings AND the identity of
        # every input the fit reads are unchanged. (The cut-off alone missed a
        # corrected earlier score, an eligibility change or a site correction.)
        if (cur.get("data_through_epoch") == ep and settings_match(cur)
                and cur.get("input_identity") == ident and "--force" not in sys.argv):
            print("season-only candidate: inputs unchanged since the last fit -- unchanged")
            return 0
    except (IOError, ValueError):
        pass
    r = subprocess.run([sys.executable, WORK, "freeze", LAM, str(ep), KE, W0, PP] + ([HT] if HT else []), cwd=REPO,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    print((r.stdout or "").strip().splitlines()[-1:] or ["(no output)"])
    if r.returncode != 0:
        # the fit writes its file only on success, so the previous artifact (and
        # its old identity) stays; the next cycle sees a mismatch and retries
        return 1
    stamp_identity(out, ident, manifest)
    return 0


def stamp_identity(out, ident, manifest):
    """Record the input identity in the successful artifact (atomic)."""
    try:
        cur = json.load(open(out))
    except (IOError, ValueError):
        return False
    cur["input_identity"] = ident
    cur["input_manifest"] = manifest
    tmp = out + ".tmp"
    json.dump(cur, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, out)
    return True


def weekly_freeze(cand_path, now=None):
    """PRIVATE weekly archive of the candidate (Cody made it the private default 2026-09-28):
    one row per completed Monday-to-Sunday week, append-only, same shape as
    data/rankings_history (week = the ISO week that COMPLETED; cutoff = its Sunday).

    B3 (2026-11-04): decoupled from re-fits. This used to run only after a
    successful re-fit, and only on a Monday -- a quiet Monday exited "unchanged"
    first, so W40, W41, W43 and W44 were never captured. Now it runs every
    refresh cycle (local_refresh calls --weekly-only before its gate) and:
      * is idempotent by BOUNDARY: one row per cutoff Sunday, whatever day runs it;
      * freezes only a candidate whose results stop at that Sunday (data through
        < Monday 00:00 PT). Once Monday results are in, the week is reported
        MISSED and nothing is written -- later data is never labelled as the
        week's snapshot, and missed weeks are never fabricated;
      * records the actual capture time and the results-through time.
    Returns one of: "frozen", "already", "missed", "no-candidate"."""
    import datetime as _dt
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
    now = now or _dt.datetime.now(PT)
    monday = (now - _dt.timedelta(days=now.weekday())).date()
    sunday = monday - _dt.timedelta(days=1)
    boundary = _dt.datetime(monday.year, monday.month, monday.day, tzinfo=PT)
    arch = os.path.join(DIR, "rankings_history_candidate.jsonl")
    if os.path.exists(arch):
        for l in open(arch):
            try:
                if json.loads(l).get("cutoff") == str(sunday):
                    return "already"
            except ValueError:
                continue
    try:
        c = json.load(open(cand_path))
    except (IOError, ValueError):
        return "no-candidate"
    ep = c.get("data_through_epoch")
    if not ep or ep >= boundary.timestamp():
        print("candidate weekly freeze: week ending %s MISSED -- the candidate already "
              "includes results after that Sunday (through %s); nothing written"
              % (sunday, _dt.datetime.fromtimestamp(ep, PT).isoformat() if ep else "unknown"))
        return "missed"
    row = {"week": "%d-W%02d" % sunday.isocalendar()[:2], "track": "candidate_weekly",
           "cutoff": str(sunday),
           "captured_utc": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "date": str(now.date()), "season": 2026, "source": "candidate",
           "version": c.get("version"), "data_through_epoch": ep,
           "results_through_pt": _dt.datetime.fromtimestamp(ep, PT).isoformat(),
           "note": "Append-only private archive of the 2026 candidate, one row per completed "
                   "week, frozen from the candidate as it stood before any later results; never rewritten.",
           "teams": [{"team": n, "rank": t["rank"], "source": "candidate", "record": t.get("record")}
                     for n, t in sorted(c["teams"].items(), key=lambda x: x[1]["rank"])]}
    with open(arch, "a") as f:
        f.write(json.dumps(row) + "\n")
    print("candidate weekly freeze: %s (cutoff %s, results through %s)"
          % (row["week"], sunday, row["results_through_pt"]))
    return "frozen"


if __name__ == "__main__":
    sys.exit(main())
