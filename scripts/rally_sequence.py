#!/usr/bin/env python3
"""Rally sequences from ncaa.com play-by-play -- evidence first, inference labelled.

Bounded rally-data audit, work order 071 (2026-11-04). Pure functions; no I/O.

THE FEED. ncaa.com /game/{id}/play-by-play logs scored events with a running
homeScore/visitorScore, a `teamId` and a `playText` ("Kill by X (from Y).",
"Service error.", "Ace by X."). Starters/substitution lines carry no score.

WHAT IS OBSERVED vs DERIVED (every derived field says so):
  * rally WINNER  -- observed: the side whose score rose by one on a scored event.
  * a same-side +2 jump (one event missing) -- the two points are DERIVED as that
    side's; the missing event's type, player and server stay UNKNOWN.
  * SERVING TEAM  -- DERIVED from "the rally winner serves next" for every
    rally after the first in a set, provided no unresolved gap precedes it.
    ⚠ The FIRST serve of a set is UNKNOWN unless the first point is an ace
    (server = winner) or a service error (server = the other side): those
    events name the server directly (OBSERVED). Nothing else assumes it.
  * Any rally ending in an ace / service error checks the derived server
    independently (that is the validation the audit reports).
  * A gap where both sides moved, a score that goes backwards, or a sequence
    that does not end at the official set score is NOT repaired: the set is
    flagged and its serving phase is not used.
Python 3.9.
"""
import re

ACE = re.compile(r"\bace\b", re.I)
SERR = re.compile(r"\bservice error\b|\bserve error\b|\bserving error\b", re.I)


def point_events(period):
    """The scored events of one set, in feed order, verbatim (the evidence)."""
    out = []
    for s in period.get("playbyplayStats") or []:
        for p in s.get("plays") or []:
            if p.get("homeScore") is None or p.get("visitorScore") is None:
                continue
            out.append({"team_id": s.get("teamId"), "clock": p.get("clock") or s.get("clock"),
                        "text": p.get("playText") or "", "home": int(p["homeScore"]),
                        "visit": int(p["visitorScore"])})
    return out


def serve_hint(ev, home_id, visit_id):
    """'home'/'visit' if the event itself names the server, else None.
    Ace: the server won the point. Service error: the server lost it.
    The point winner is taken from the SCORE, never from the label alone."""
    t = ev.get("text") or ""
    win = ev.get("_winner")
    if not win:
        return None
    if ACE.search(t) and not SERR.search(t):
        return win
    if SERR.search(t):
        return "visit" if win == "home" else "home"
    return None


def sequence(period, final_home, final_visit, home_id, visit_id):
    """One set -> {evidence, rallies, flags}. Never invents a rally detail."""
    ev = point_events(period)
    rallies, flags = [], []
    ph = pv = 0
    gap_open = False
    for e in ev:
        dh, dv = e["home"] - ph, e["visit"] - pv
        if dh < 0 or dv < 0:
            flags.append("score_backwards")
            gap_open = True
            ph, pv = e["home"], e["visit"]
            continue
        if (dh, dv) == (0, 0):
            flags.append("duplicate_event")
            continue
        if dh and dv:
            flags.append("gap_both_sides")            # unrecoverable
            gap_open = True
            ph, pv = e["home"], e["visit"]
            continue
        side = "home" if dh else "visit"
        n = dh or dv
        for k in range(n - 1):                          # missing events, same side
            rallies.append({"winner": side, "derived_winner": True, "text": None,
                            "event_unknown": True})
            flags.append("gap_same_side")
        e2 = dict(e, _winner=side)
        rallies.append({"winner": side, "derived_winner": False, "text": e["text"],
                        "serve_hint": serve_hint(e2, home_id, visit_id)})
        ph, pv = e["home"], e["visit"]
    reconciled = (ph, pv) == (final_home, final_visit)
    if not reconciled:
        flags.append("final_mismatch")
    # serving team: rally i (i>0) is served by the winner of rally i-1
    first_known = None
    if rallies and rallies[0].get("serve_hint"):
        first_known = rallies[0]["serve_hint"]
    usable = reconciled and not gap_open
    checks = agree = 0
    for i, r in enumerate(rallies):
        if i == 0:
            r["server"] = first_known
            r["server_basis"] = "observed (ace/service error)" if first_known else "unknown (first serve)"
        else:
            r["server"] = rallies[i - 1]["winner"] if usable else None
            r["server_basis"] = "derived (previous rally winner)" if usable else "unusable set"
            if usable and r.get("serve_hint"):
                checks += 1
                agree += (r["serve_hint"] == r["server"])
    return {"evidence": ev, "rallies": rallies, "flags": sorted(set(flags)),
            "reconciled": reconciled, "usable": usable,
            "serve_checks": checks, "serve_agree": agree,
            "points": len(rallies), "observed_points": sum(1 for r in rallies if not r["derived_winner"])}


def phase_counts(seq):
    """Known-serving rallies only: per side, served/won and received/won."""
    c = {"home": {"srv": 0, "srv_won": 0, "rcv": 0, "rcv_won": 0},
         "visit": {"srv": 0, "srv_won": 0, "rcv": 0, "rcv_won": 0}}
    unknown = 0
    for r in seq["rallies"]:
        s = r.get("server")
        if s not in ("home", "visit"):
            unknown += 1
            continue
        o = "visit" if s == "home" else "home"
        c[s]["srv"] += 1
        c[o]["rcv"] += 1
        if r["winner"] == s:
            c[s]["srv_won"] += 1
        else:
            c[o]["rcv_won"] += 1
    return c, unknown


def match_record(gid, payload, linescores, home_id, visit_id, fetched_utc, source):
    """The stored record: original scored events per set + derived sequence + provenance."""
    sets = []
    periods = payload.get("periods") or []
    for i, p in enumerate(periods):
        fh = fv = None
        if i < len(linescores):
            try:
                fh, fv = int(linescores[i]["home"]), int(linescores[i]["visit"])
            except (TypeError, ValueError, KeyError):
                pass
        sq = sequence(p, fh, fv, home_id, visit_id)
        sets.append(dict(sq, set=p.get("periodNumber") or i + 1, final=[fh, fv]))
    return {"game_id": str(gid), "source": source, "fetched_utc": fetched_utc,
            "home_id": home_id, "visit_id": visit_id, "tier": "DERIVED",
            "note": "evidence = verbatim scored events; rallies = derived, flagged per field",
            "sets": sets}
