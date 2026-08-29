#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Result Confidence Ledger: what each final's evidence actually is.

"Official feed final" and "independently cross-source confirmed" are
different claims, and this module keeps them apart (review round 7). Five
field-level states, weakest to strongest:

  official        -- the canonical official scoreboard says final. TRUE for
                     every final by construction; the floor, not a boast.
  reconciled      -- the held records agree with each other: the set line,
                     the winner and the set tally are internally coherent,
                     and a held box score names both teams. Still ONE source.
  confirmed       -- a second ATTRIBUTABLE public source (a school site, a
                     gamebook) supports the specific field. A second NCAA
                     endpoint is the same source wearing a different URL and
                     can never produce this state.
  disputed        -- attributable sources conflict on a field. Displayed as
                     "result under review" with both claims shown; and
                     test_confidence.py FAILS while any dispute stands, so
                     the pipeline halts loudly instead of silently consuming
                     it. (The stated policy: raw history is never rewritten,
                     and a red suite is the quarantine -- the architecture
                     has no per-match exclusion hook in the rating, and
                     inventing one silently would change ranking math, which
                     this phase must not do.)
  pending         -- no second source held yet. The honest NORMAL state.

Evidence lives per match AND per field in data/raw/2026/result_evidence.json
(the fixture-correction ledger's discipline, extended): an entry supports
only the fields it lists, so a source confirming the 3-1 says nothing about
the box score. Duplicate URLs count once. An entry past its review_by, or
one recorded attempted_unverifiable, supports nothing.

Writes data/result_confidence_%SEASON%.json. Run after build_dataset.
"""

import datetime
import json
import os
import sys

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:                                      # noqa: BLE001
    PT = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
FIELDS = ("result", "sets", "box", "venue")


def load(p, default=None):
    path = os.path.join(REPO, p)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) \
        else default


def entry_supports(e, field, today=None):
    """Does this evidence entry support `field` RIGHT NOW?

    Field-scoped (no spill), never an NCAA endpoint, never an unverifiable
    attempt, and never past its review date.
    """
    if not isinstance(e, dict):
        return False
    if e.get("status") not in ("confirms", "conflicts"):
        return False
    if e.get("kind") == "ncaa_official":
        return False                       # same source, different URL
    if field not in (e.get("fields") or []):
        return False
    rb = e.get("review_by")
    if rb and today and str(rb) < str(today):
        return False                       # stale: back to pending
    return True


def field_state(entries, field, base, today=None):
    """One field's state, lifted from that field's own BASE by evidence.

    ⚠ THE BASE IS PER FIELD, NEVER A SHARED BOOLEAN (review round 8). The
    first version passed one internal-coherence flag for all four fields,
    so a coherent SCORELINE rendered "venue: reconciled" -- set arithmetic
    cannot corroborate where a match was played. Each caller computes its
    own base; this function only lifts it to confirmed/disputed on
    field-specific evidence. One source can never confirm; a conflict
    outranks everything."""
    seen = set()
    confirms = conflicts = 0
    for e in entries or []:
        if not entry_supports(e, field, today):
            continue
        u = e.get("url")
        if u in seen:
            continue                       # exact duplicate source: once
        seen.add(u)
        if e.get("status") == "conflicts":
            conflicts += 1
        else:
            confirms += 1
    if conflicts:
        return "disputed"
    if confirms >= 1:
        return "confirmed"
    return base


def internally_reconciled(g):
    """Held records agree with each other: set line vs winner vs tally."""
    ls = [l for l in (g.get("linescores") or []) if l.get("home") is not None]
    if not ls:
        return False
    aw = hw = 0
    for l in ls:
        a, h = int(l.get("visit") or 0), int(l.get("home") or 0)
        if a > h:
            aw += 1
        elif h > a:
            hw += 1
    ts = g.get("teams") or []
    if len(ts) != 2:
        return False
    # ⚠ TEAM ORDER IS NOT AWAY-FIRST in this file -- use the is_home flag.
    # Assuming ts[0] was the away side scored every final as incoherent
    # (0 of 207 reconciled), which was the CHECK being wrong, not the data.
    home = [t for t in ts if t.get("is_home")]
    away = [t for t in ts if not t.get("is_home")]
    if len(home) != 1 or len(away) != 1:
        return False
    win = str(g.get("winner_team_id"))
    if aw == hw:
        return False
    return (aw > hw) == (win == str(away[0].get("team_id")))


def box_teams():
    """gid -> (n_distinct_team_ids, max sets a row claims): enough to say a
    HELD box is internally coherent with the match -- presence alone is not
    coherence."""
    out = {}
    path = os.path.join(REPO, "data", "raw", str(SEASON), "playerbox.jsonl")
    if not os.path.exists(path):
        return out
    for ln in open(path, encoding="utf-8"):
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        rows = rec.get("rows") or []
        tids = set(str(r.get("team_id")) for r in rows if r.get("team_id"))
        mx = 0
        for r in rows:
            try:
                mx = max(mx, int(float(r.get("gp") or 0)))
            except (TypeError, ValueError):
                pass
        out[str(rec.get("game_id"))] = (len(tids), mx)
    return out


def duplicate_candidates(finals):
    """AUDIT CANDIDATES, never removals (round 11): pairs of finals with the
    same unordered teams, the same winner, an identical ordered set line, a
    start-time gap under 36 hours AND a quality asymmetry (placeholder-hour
    start, missing venue, or missing box on exactly one side). A real
    doubleheader or a repeat tournament meeting fails the identical-set-line
    test in practice and, even when it would not, nothing here changes a
    count -- a candidate waits for authoritative evidence in the
    duplicate-listings ledger. Same-teams-same-score-nearby is only ever a
    review trigger."""
    by_pair = {}
    for g in finals:
        key = tuple(sorted([g["a"], g["h"]]))
        by_pair.setdefault(key, []).append(g)
    out = []
    for key, gs in by_pair.items():
        if len(gs) < 2:
            continue
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                a, b = gs[i], gs[j]
                if a.get("winner") != b.get("winner"):
                    continue
                if a.get("setline") != b.get("setline") or not a.get("setline"):
                    continue
                if abs((a.get("ep") or 0) - (b.get("ep") or 0)) > 36 * 3600:
                    continue
                asym = (bool(a.get("placeholder")) != bool(b.get("placeholder"))
                        or bool(a.get("venue")) != bool(b.get("venue"))
                        or bool(a.get("has_box")) != bool(b.get("has_box")))
                if not asym:
                    continue
                out.append({"pair": list(key),
                            "gids": [a["gid"], b["gid"]],
                            "setline": a.get("setline"),
                            "gap_hours": round(abs((a.get("ep") or 0)
                                                   - (b.get("ep") or 0))
                                               / 3600.0, 1),
                            "status": "candidate duplicate \u2014 "
                                      "verification pending"})
    return out


def build():
    doc = load("data/data_%d.json" % SEASON) or {}
    ev = (load("data/raw/%d/result_evidence.json" % SEASON) or {}) \
        .get("evidence") or {}
    id2n = dict((str(t["team_id"]), t.get("name_short"))
                for t in (doc.get("teams") or []))
    # exhibition team ids are not in the dataset's team table; their names
    # come from the hand-maintained exhibitions ledger rather than blanks
    exh_names = {}
    for _gid, _e in ((load("data/raw/%d/exhibitions.json" % SEASON) or {})
                     .get("exhibitions") or {}).items():
        _t = _e.get("teams") or []
        if len(_t) == 2:
            exh_names[str(_gid)] = _t
    today = datetime.date.today().isoformat()
    boxes = box_teams()
    try:
        from dupes import duplicate_gids
        dup_of = duplicate_gids(SEASON)
    except Exception:                                  # noqa: BLE001
        dup_of = {}
    _cand_src = []
    rows, counts = [], {"finals": 0, "official_only": 0, "reconciled": 0,
                        "confirmed": 0, "disputed": 0, "pending_second": 0}
    for g in (doc.get("games") or []):
        if g.get("state") != "F":
            continue
        counts["finals"] += 1
        gid = str(g.get("game_id"))
        rec = internally_reconciled(g)
        entries = ev.get(gid) or []
        nsets = len([l for l in (g.get("linescores") or [])
                     if l.get("home") is not None])
        # ⚠ EACH FIELD EARNS ITS OWN BASE. Result and sets may cite the set
        # line's coherence with the official winner; the BOX is reconciled
        # only when a held box actually agrees with the match (two teams,
        # max player sets == the match's set count); the VENUE can never be
        # lifted by score arithmetic -- it is official when the feed carried
        # a location and unavailable when it did not, until a venue-specific
        # source exists.
        bt = boxes.get(gid)
        bases = {
            "result": "reconciled" if rec else "official",
            "sets": "reconciled" if rec else "official",
            "box": ("reconciled" if bt and bt[0] == 2 and nsets
                    and bt[1] == nsets else "official"),
            "venue": ("official" if (g.get("location") or {}).get("venue")
                      else "unavailable"),
        }
        states = dict((f, field_state(entries, f, bases[f], today))
                      for f in FIELDS)
        overall = ("disputed" if "disputed" in states.values()
                   else "confirmed" if states["result"] == "confirmed"
                   else "reconciled" if rec else "official")
        srcs = [e for e in entries if isinstance(e, dict)
                and e.get("status") in ("confirms", "conflicts")]
        attempted = sum(1 for e in entries if isinstance(e, dict)
                        and e.get("status") == "attempted_unverifiable")
        checked = max([e.get("retrieved") or "" for e in entries] or [""])
        ts = g.get("teams") or []
        _fallback = exh_names.get(gid) or ["", ""]
        _ep = int(g.get("start_time_epoch") or 0)
        _et_hour = datetime.datetime.utcfromtimestamp(_ep).hour - 4 if _ep else None
        _cand_src.append({
            "gid": gid,
            "a": id2n.get(str(([t for t in ts if not t.get("is_home")] or
                               [{}])[0].get("team_id")), "") or _fallback[0],
            "h": id2n.get(str(([t for t in ts if t.get("is_home")] or
                               [{}])[0].get("team_id")), "") or _fallback[1],
            "winner": str(g.get("winner_team_id") or ""),
            "setline": tuple((l.get("visit"), l.get("home"))
                             for l in (g.get("linescores") or [])
                             if l.get("home") is not None),
            "ep": _ep,
            "placeholder": (_et_hour is not None and 0 <= (_et_hour % 24) < 7),
            "venue": (g.get("location") or {}).get("venue"),
            "has_box": gid in boxes,
        })
        rows.append({
            "duplicate_of": dup_of.get(gid) or None,
            "gid": gid,
            "a": id2n.get(str(([t for t in ts if not t.get("is_home")] or
                               [{}])[0].get("team_id")), "") or _fallback[0],
            "h": id2n.get(str(([t for t in ts if t.get("is_home")] or
                               [{}])[0].get("team_id")), "") or _fallback[1],
            "exh": gid in exh_names,
            # ⚠ PACIFIC, like every date on this page: a 9pm ET Friday
            # final is already Saturday in UTC, and rendered as such it
            # disagrees with every other surface showing the same match.
            "d": (datetime.datetime.fromtimestamp(
                int(g.get("start_time_epoch") or 0), PT).strftime("%Y-%m-%d")
                if PT else datetime.datetime.utcfromtimestamp(
                int(g.get("start_time_epoch") or 0)).strftime("%Y-%m-%d")),
            "overall": overall, "states": states,
            # ⚠ INDEPENDENT CORROBORATION, distinct from the official
            # scoreboard record every final has -- "0 sources" beside
            # "every final is official" read as a contradiction (round 8).
            # n_attempted keeps "tried, unreadable" visibly separate from
            # "none tried".
            "n_indep": len(set(e.get("url") for e in srcs)),
            "n_attempted": attempted,
            "last_checked": checked or None,
            "sources": [{"url": e.get("url"), "kind": e.get("kind"),
                         "school": e.get("school"),
                         "text": e.get("text"), "fields": e.get("fields"),
                         "status": e.get("status"),
                         "retrieved": e.get("retrieved")}
                        for e in entries if isinstance(e, dict)],
        })
        if overall == "disputed":
            counts["disputed"] += 1
        elif overall == "confirmed":
            counts["confirmed"] += 1
        elif overall == "reconciled":
            counts["reconciled"] += 1
        else:
            counts["official_only"] += 1
    counts["pending_second"] = counts["finals"] - counts["confirmed"] \
        - counts["disputed"]
    counts["duplicate_listings"] = sum(1 for r in rows if r["duplicate_of"])
    cands = [c for c in duplicate_candidates(_cand_src)
             if not any(gid in dup_of for gid in c["gids"])]
    counts["duplicate_candidates_pending"] = len(cands)
    json.dump({"meta": {"season": SEASON,
                        "note": "review candidates only; nothing here "
                                "changes a count"},
               "candidates": cands},
              open(os.path.join(REPO, "data",
                                "duplicate_candidates_%d.json" % SEASON),
                   "w"), indent=1)
    out = {"meta": {"season": SEASON, "source_tier": "DERIVED",
                    "generated_at_utc": datetime.datetime.utcnow().replace(
                        microsecond=0).isoformat() + "Z",
                    "counts": counts},
           "finals": rows}
    dst = os.path.join(REPO, "data", "result_confidence_%d.json" % SEASON)
    json.dump(out, open(dst, "w"), indent=1)
    print("confidence: %(finals)d finals -- %(confirmed)d cross-source "
          "confirmed, %(disputed)d disputed, %(reconciled)d internally "
          "reconciled, %(official_only)d official-only" % counts)
    return 0


if __name__ == "__main__":
    sys.exit(build())
