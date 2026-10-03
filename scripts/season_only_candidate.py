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
    try:
        cur = json.load(open(out))
        if cur.get("data_through_epoch") == ep and str(cur.get("lambda")) == LAM and str(cur.get("earned_weight")) == KE and str(cur.get("ramp_w0")) == W0 and cur.get("ballast_active") is True and cur.get("height_term") is False and len(cur.get("start_parts") or []) == 4 and cur.get("structure") \
                and cur.get("fit_used") == "c093.fit_both+T" and cur.get("fifth_set_weight") == 0.5 and cur.get("opp_uncertainty_s0") == 96 and cur.get("theta_sd") and "--force" not in sys.argv:   # ⚠ was ==3 parts / 0.75: never matched, so every cycle refroze       # the frozen file must record the fit that ran
            print("season-only candidate: already at Current POWER's cut-off -- unchanged")
            return 0
    except (IOError, ValueError):
        pass
    r = subprocess.run([sys.executable, WORK, "freeze", LAM, str(ep), KE, W0, PP] + ([HT] if HT else []), cwd=REPO,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    print((r.stdout or "").strip().splitlines()[-1:] or ["(no output)"])
    if r.returncode == 0:
        weekly_freeze(out)
    return 0 if r.returncode == 0 else 1


def weekly_freeze(cand_path):
    """PRIVATE weekly archive of the candidate (Cody made it the private default 2026-09-28):
    one row per capture week, Mondays only, append-only, same shape as data/rankings_history
    (week = the ISO week that just COMPLETED; captured_utc = when the row was taken). The
    board's movement column for the candidate basis reads this file."""
    import datetime as _dt
    from zoneinfo import ZoneInfo
    now = _dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.weekday() != 0:
        return
    arch = os.path.join(DIR, "rankings_history_candidate.jsonl")
    cap_week = "%d-W%02d" % now.isocalendar()[:2]
    if os.path.exists(arch):
        for l in open(arch):
            try:
                r = json.loads(l)
                if r.get("captured_utc") and "%d-W%02d" % _dt.datetime.strptime(r["captured_utc"][:10], "%Y-%m-%d").isocalendar()[:2] == cap_week:
                    return
            except (ValueError, KeyError):
                continue
    c = json.load(open(cand_path))
    done = now.date() - _dt.timedelta(days=1)
    row = {"week": "%d-W%02d" % done.isocalendar()[:2], "track": "candidate_weekly", "cutoff": str(done),
           "captured_utc": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "date": str(now.date()), "season": 2026,
           "source": "candidate", "version": c.get("version"), "data_through_epoch": c.get("data_through_epoch"),
           "note": "Append-only private archive of the 2026 candidate, frozen Mondays; never rewritten.",
           "teams": [{"team": n, "rank": t["rank"], "source": "candidate", "record": t.get("record")}
                     for n, t in sorted(c["teams"].items(), key=lambda x: x[1]["rank"])]}
    with open(arch, "a") as f:
        f.write(json.dumps(row) + "\n")
    print("candidate weekly freeze: %s (captured %s)" % (row["week"], cap_week))


if __name__ == "__main__":
    sys.exit(main())
