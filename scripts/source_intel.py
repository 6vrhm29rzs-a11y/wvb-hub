#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOURCE INTELLIGENCE FOUNDATION v1 — one claims layer over the ledgers.

No new crawling. The six evidence ledgers already practice evidence-first
capture (url + exact excerpt + retrieval time + per-field support + review
dates); this module UNIFIES them into claims with seven states and feeds a
bounded "What changed" area on Today. See docs/source_intel_inventory.md
for the measured source inventory that scoped this.

THE STATES (a claim carries exactly one):
  confirmed_official    an official source establishes it (school site,
                        official box/gamebook, or the classification
                        ledgers' own proof rules)
  corroborated          two or more INDEPENDENT attributable sources agree
  official_unconfirmed  the official feed asserts it; nothing else yet
  community_signal      a forum/eye-test lead. NEVER promotes by
                        repetition; never renders as more than a signal
  conflicting           attributable sources disagree; shown, not chosen
  expired               evidence past its review date on a claim that
                        still needed it
  inaccessible          an attempt was made and the source was unreadable
                        -- recorded, establishes nothing

RANKING SEPARATION (hard rule): nothing in the rating chain reads this
module or its artifact. Source intelligence explains context; any future
quantitative use needs its own approved model-input contract. Guarded in
test_source_intel.py.

Python 3.9 target.
"""

import datetime
import hashlib
import io
import json
import os
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RECENT_HOURS = 72          # the "since the last refresh" window, stated
FEED_CAP = 5               # bounded by design -- never a news feed

STATES = ("confirmed_official", "corroborated", "official_unconfirmed",
          "community_signal", "conflicting", "expired", "inaccessible")

STATE_LABEL = {
    "confirmed_official": "confirmed by an official source",
    "corroborated": "corroborated by independent sources",
    "official_unconfirmed": "official record; confirmation pending",
    "community_signal": "community signal — a lead, not a fact",
    "conflicting": "sources conflict — shown, not chosen",
    "expired": "evidence past its review date",
    "inaccessible": "source attempted, unreadable",
}


def _load(path):
    p = os.path.join(REPO, path)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except ValueError:
        return {}


def _cid(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts)
                        .encode("utf-8")).hexdigest()[:12]


def _short(text, n):
    """Cut at a word boundary with an ellipsis -- a title chopped
    mid-word ('W&M's offi') reads as a rendering bug."""
    t = (text or "").strip()
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + " \u2026"


def _src(url, excerpt, retrieved, source_class):
    return {"url": url, "excerpt": (excerpt or "")[:400],
            "retrieved": retrieved, "source_class": source_class}


# what each claim TYPE establishes -- and therefore what its sources do
# NOT establish, said on the drill so a reader cannot over-read a citation
SCOPE = {
    "result_correction": "the winner and set line of this one match",
    "result_confirmation": "the result of this one match",
    "result_conflict": "that sources disagree about this result",
    "fixture_update": "the corrected schedule fields only",
    "fixture_conflict": "that official sources disagree on one field",
    "fixture_evidence": "a schedule reading, now past its review date",
    "duplicate_listing": "that the feed listed one meeting twice",
    "classification": "that this match is an exhibition",
    "availability": "one player's availability for the stated dates",
    "verification_attempt": "nothing -- the attempt is recorded",
}


def _claim(cid, ctype, subject, what, state, why, sources,
           public, priority, route=None, effective=None, review_by=None,
           source_kind=None, source_kind_label=None):
    assert state in STATES, state
    out = {"id": cid, "type": ctype, "subject": subject, "what": what,
           "state": state, "state_label": STATE_LABEL[state], "why": why,
           "scope": SCOPE.get(ctype),
           "sources": sources, "public": bool(public),
           "priority": int(priority), "route": route,
           "effective": effective, "review_by": review_by}
    if source_kind:
        # the controlled source-kind vocabulary (availability_desk.
        # KIND_LABEL): a player statement, a school source and a beat
        # report are different kinds of evidence and the chip says which
        out["source_kind"] = source_kind
        out["source_kind_label"] = source_kind_label or source_kind
    return out


# ---- per-ledger derivations -------------------------------------------

def _from_result_corrections(season):
    out = []
    doc = _load("data/raw/%d/result_corrections.json" % season)
    for gid, c in (doc.get("corrections") or {}).items():
        srcs = [_src(e.get("url"), e.get("text"), e.get("retrieved"),
                     "official_school")
                for e in (c.get("evidence") or []) if e.get("text")]
        out.append(_claim(
            _cid("rcorr", gid), "result_correction",
            {"kind": "match", "gid": str(gid)},
            "Result corrected: %s" % _short(c.get("established"), 110),
            "confirmed_official",
            "the feed's record was incomplete or wrong; %d named official "
            "source(s) supply the result" % len(srcs),
            srcs, public=True, priority=90,
            route={"match": str(gid), "ledger": True}))
    return out


def _from_fixture_ledger(season, today):
    out = []
    import ledger as LG
    L = LG.load(today=today)
    for gid, c in (L.get("corrections") or {}).items():
        fields = sorted((c.get("fields") or {}).keys())
        sup = c.get("support") or {}
        srcs = [_src(v.get("url"), v.get("text"), v.get("retrieved"),
                     "official_school")
                for v in sup.values()][:3]
        out.append(_claim(
            _cid("fx", gid, ",".join(fields)), "fixture_update",
            {"kind": "match", "gid": str(gid)},
            "%s corrected for %s" % (
                " / ".join(fields), c.get("matchup") or "a fixture"),
            "confirmed_official",
            "the school's own page contradicts the feed on %s; every "
            "overridden field carries its own citation" % ", ".join(fields),
            srcs, public=True, priority=70,
            route={"match": str(gid)}, review_by=c.get("review_by")))
    for gid, cfs in (L.get("conflicts") or {}).items():
        for cf in cfs:
            srcs = [_src((cl.get("support") or {}).get("url"),
                         (cl.get("support") or {}).get("text"),
                         (cl.get("support") or {}).get("retrieved"),
                         "official_school") for cl in cf.get("claims") or []]
            out.append(_claim(
                _cid("fxconf", gid, cf.get("field")), "fixture_conflict",
                {"kind": "match", "gid": str(gid)},
                "Official sources disagree on this fixture's %s"
                % cf.get("field"),
                "conflicting",
                "two attributable official sources make different claims; "
                "both are preserved and the fact renders unavailable",
                srcs, public=True, priority=95,
                route={"match": str(gid)}))
    for gid, sts in (L.get("stale") or {}).items():
        for st in sts:
            out.append(_claim(
                _cid("fxstale", gid, st.get("kind")), "fixture_evidence",
                {"kind": "match", "gid": str(gid)},
                "A schedule reading for %s passed its review date"
                % (st.get("matchup") or "a fixture"),
                "expired",
                "a schedule claim is perishable; this one was not "
                "re-verified by its review date",
                [], public=True, priority=20,
                route={"match": str(gid)}, review_by=st.get("review_by")))
    return out


def _from_duplicates(season):
    out = []
    doc = _load("data/raw/%d/duplicate_listings.json" % season)
    for gid, d in (doc.get("duplicates") or {}).items():
        srcs = [_src(e.get("url"), e.get("text"), e.get("retrieved"),
                     "official_school")
                for e in (d.get("evidence") or []) if e.get("text")]
        _teams = d.get("teams") or []
        _who = ("%s v %s" % tuple(_teams[:2])) if len(_teams) == 2 \
            else "a match"
        out.append(_claim(
            _cid("dup", gid), "duplicate_listing",
            {"kind": "match", "gid": str(gid), "teams": _teams},
            "%s was listed twice by the feed; the copy is excluded "
            "from every count" % _who,
            "corroborated" if len(srcs) >= 2 else "confirmed_official",
            "both schools' official schedules establish exactly one "
            "meeting" if len(srcs) >= 2 else
            "established from official schedule evidence",
            srcs, public=True, priority=60,
            route={"match": str(d.get("duplicate_of") or gid),
                   "ledger": True}))
    return out


def _from_exhibitions(season):
    out = []
    import exhibitions as EXH
    try:
        led = EXH.ledger(season)
    except ValueError:
        return out
    for gid, e in led.items():
        fmt = EXH._nonstandard_targets(e.get("sets_to") or [])
        ce = e.get("classification_evidence") or {}
        srcs = ([_src(ce.get("url"), ce.get("text"), ce.get("retrieved"),
                      "official_school")] if ce.get("text") else [])
        out.append(_claim(
            _cid("exh", gid), "classification",
            {"kind": "match", "gid": str(gid),
             "teams": e.get("teams") or []},
            "%s v %s is an exhibition — counts toward nothing"
            % tuple((e.get("teams") or ["?", "?"])[:2]),
            "confirmed_official",
            ("its format proves it: sets to %s cannot be an NCAA result"
             % fmt) if fmt else "an official source labels it explicitly",
            srcs, public=True, priority=50,
            route={"match": str(gid)}))
    return out


def _from_result_evidence(season):
    out = []
    doc = _load("data/raw/%d/result_evidence.json" % season)
    for gid, entries in (doc.get("evidence") or {}).items():
        ok = [e for e in entries if e.get("status") == "confirms"]
        bad = [e for e in entries if e.get("status") == "conflicts"]
        tried = [e for e in entries
                 if e.get("status") == "attempted_unverifiable"]
        if bad:
            out.append(_claim(
                _cid("rev-c", gid), "result_conflict",
                {"kind": "match", "gid": str(gid)},
                "An attributable source disputes this result",
                "conflicting",
                "shown, never chosen; the Result Ledger holds both claims",
                [_src(e.get("url"), e.get("text"), e.get("retrieved"),
                      e.get("kind") or "official_school") for e in bad],
                public=True, priority=95,
                route={"match": str(gid), "ledger": True}))
        elif len({e.get("url") for e in ok}) >= 2:
            out.append(_claim(
                _cid("rev", gid), "result_confirmation",
                {"kind": "match", "gid": str(gid)},
                "Result cross-source confirmed",
                "corroborated",
                "%d independent attributable sources agree with the "
                "official record" % len({e.get("url") for e in ok}),
                [_src(e.get("url"), e.get("text"), e.get("retrieved"),
                      e.get("kind") or "official_school")
                 for e in ok][:3],
                public=True, priority=30,
                route={"match": str(gid), "ledger": True}))
        elif tried and not ok:
            out.append(_claim(
                _cid("rev-t", gid), "verification_attempt",
                {"kind": "match", "gid": str(gid)},
                "Independent confirmation attempted; source unreadable",
                "inaccessible",
                "the attempt is recorded and establishes nothing",
                [_src(e.get("url"), e.get("note") or "no readable result",
                      e.get("retrieved"), e.get("kind") or "official_school")
                 for e in tried][:2],
                public=True, priority=10,
                route={"match": str(gid), "ledger": True}))
    return out


def _from_availability(season, today):
    """⚠ PRIVATE, ALL OF IT. Availability is an AVAIL-fenced feature and a
    community observation is Cody's own words -- none of it may reach the
    published page. public=False is the value-level filter the public
    build applies.

    ⚠ ONE CLAIM PER PLAYER, FROM THE CANONICAL PROJECTION (truth repair,
    2026-09-01). The old per-entry loop predated match incidents and the
    out_for_season claim: Wollard's sourced status rendered as
    "UNCONFIRMED" and Heaney's school-sourced incident fell through to a
    generic community "SIGNAL" -- two surfaces contradicting the Desk.
    availability_desk.projection() is THE state; this function only
    translates it into intel vocabulary:
      status   -> confirmed_official ("PLAYER: <headline> -- sourced
                  availability status")
      incident -> confirmed_official ("sourced match incident; current
                  availability unknown")
      signal   -> community_signal, exactly as before."""
    out = []
    try:
        import availability_desk as AD
    except Exception:
        return out
    if today is None:
        today = datetime.date.today().isoformat()
    doc = _load("data/raw/%d/availability_evidence.json" % season)
    for c in AD.projection((doc.get("players") or {}), today):
        team, player = c["team"], c["player"]
        sup = c.get("supports") or []
        lead_kind = (sup[0].get("kind") if sup else None)
        kind_label = (sup[0].get("kind_label") if sup else None)
        if c["state"] == "status":
            state = "confirmed_official"
            title = "%s (%s): %s -- sourced availability status" % (
                player, team, c.get("headline"))
            if lead_kind == "player_statement":
                # her own public statement, via a press report -- NOT a
                # school athletics release, and the label must not imply one
                title += (" (the player's own public statement, via press "
                          "report -- not a school release)")
        elif c["state"] == "incident":
            state = "confirmed_official"
            title = ("%s (%s): sourced match incident -- %s; current "
                     "availability unknown" % (player, team,
                                               c.get("headline")))
        else:
            state = "community_signal"
            title = "%s (%s): availability signal" % (player, team)
        official = state == "confirmed_official"
        out.append(_claim(
            _cid("avail", "%s|%s" % (team, player),
                 (sup[0].get("retrieved") if sup else "")),
            "availability",
            {"kind": "player", "team": team, "player": player},
            title, state, STATE_LABEL[state],
            [_src(e.get("url"), e.get("quote") or e.get("note"),
                  e.get("retrieved"),
                  "official_school" if official else "community")
             for e in sup],
            public=False,
            priority=80 if official else 45,
            route={"team": team},
            effective=(sup[0].get("effective") if sup else None),
            review_by=(sup[0].get("review_by") if sup else None),
            source_kind=lead_kind, source_kind_label=kind_label))
    # expired evidence keeps its history claim, one per entry, as before
    for key, evs in (doc.get("players") or {}).items():
        team, _, player = key.partition("|")
        for ev in evs or []:
            if AD.entry_state(ev, today) == "expired":
                out.append(_claim(
                    _cid("avail", key, ev.get("retrieved")),
                    "availability",
                    {"kind": "player", "team": team, "player": player},
                    "%s (%s): availability signal" % (player, team),
                    "expired", STATE_LABEL["expired"],
                    [_src(ev.get("url"), ev.get("quote") or ev.get("note"),
                          ev.get("retrieved"), "community")],
                    public=False, priority=20,
                    route={"team": team},
                    effective=ev.get("effective"),
                    review_by=ev.get("review_by")))
    return out


# ---- assembly ----------------------------------------------------------

def claims(season=SEASON, today=None):
    # type: (int, Optional[str]) -> List[Dict]
    out = []
    out += _from_result_corrections(season)
    out += _from_fixture_ledger(season, today)
    out += _from_duplicates(season)
    out += _from_exhibitions(season)
    out += _from_result_evidence(season)
    out += _from_availability(season, today)
    # ⚠ A COMMUNITY CLAIM CANNOT BE PROMOTED BY REPETITION -- there is no
    # aggregation step here at all: states come from each ledger's own
    # rules, and nothing counts signals.
    for c in out:
        assert c["state"] in STATES
        assert not (c["state"] in ("confirmed_official", "corroborated")
                    and all(s.get("source_class") == "community"
                            for s in c["sources"]) and c["sources"]), \
            "a community-only claim may never be confirmed: %s" % c["id"]
    return out


FEED_PATH = os.path.join(REPO, "data", "intel_feed_%d.jsonl" % SEASON)


def _now_utc():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def first_seen(all_claims, feed_path=None, now=None):
    """Append-only first-seen ledger: 'since the last refresh' needs a
    memory, and an append-only file of (id, first_seen) is the smallest
    honest one. Never rewritten; a claim's first appearance is a fact."""
    path = feed_path or FEED_PATH
    seen = {}
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
                seen[r["id"]] = r["first_seen"]
            except (ValueError, KeyError):
                continue
    new = [c for c in all_claims if c["id"] not in seen]
    if new:
        stamp = now or _now_utc()
        with io.open(path, "a", encoding="utf-8") as fh:
            for c in new:
                fh.write(json.dumps({"id": c["id"],
                                     "first_seen": stamp}) + "\n")
                seen[c["id"]] = stamp
    return seen


def what_changed(all_claims, seen, now=None, cap=FEED_CAP,
                 recent_hours=RECENT_HOURS):
    """The bounded Today feed: recent, priority-ranked, capped -- and
    EMPTY rather than padded when nothing material happened."""
    now_dt = datetime.datetime.strptime(now or _now_utc(),
                                        "%Y-%m-%dT%H:%M:%SZ")
    out = []
    for c in all_claims:
        fs = seen.get(c["id"])
        if not fs:
            continue
        try:
            dt = datetime.datetime.strptime(fs, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
        age_h = (now_dt - dt).total_seconds() / 3600.0
        if 0 <= age_h <= recent_hours:
            out.append(dict(c, first_seen=fs))
    # ⚠ NEWEST DAY FIRST, THEN PRIORITY. Priority alone buried five
    # freshly-discovered duplicate listings (a records fix) under two-day-
    # old result corrections -- "what changed" answers SINCE WHEN before
    # it answers HOW MUCH.
    out.sort(key=lambda c: (c["first_seen"][:10], c["priority"],
                            c["first_seen"]), reverse=True)
    # ⚠ AT MOST TWO PER CLAIM TYPE: five result corrections must not crowd
    # five freshly-evidenced duplicate listings out of a five-slot feed --
    # a bounded feed earns its bound by being REPRESENTATIVE, not by
    # showing one class of news
    picked, per_type = [], {}
    for c in out:
        t = c["type"]
        if per_type.get(t, 0) >= 2:
            continue
        per_type[t] = per_type.get(t, 0) + 1
        picked.append(c)
        if len(picked) >= cap:
            break
    return picked


def build(season=SEASON, today=None, now=None):
    all_claims = claims(season, today)
    seen = first_seen(all_claims, now=now)
    feed = what_changed(all_claims, seen, now=now)
    doc = {
        "meta": {"season": season, "generated_at_utc": now or _now_utc(),
                 "n_claims": len(all_claims), "feed_cap": FEED_CAP,
                 "recent_hours": RECENT_HOURS,
                 "states": {s: sum(1 for c in all_claims
                                   if c["state"] == s) for s in STATES}},
        "claims": all_claims,
        "feed": feed,
    }
    p = os.path.join(REPO, "data", "source_intel_%d.json" % season)
    json.dump(doc, io.open(p, "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    return doc


if __name__ == "__main__":
    d = build()
    m = d["meta"]
    print("source intel: %d claims -- %s" % (
        m["n_claims"],
        ", ".join("%s %d" % (k, v) for k, v in m["states"].items() if v)))
    print("what changed (<=%d, %dh): %d item(s)"
          % (m["feed_cap"], m["recent_hours"], len(d["feed"])))
    for c in d["feed"]:
        print("  [%s] %s" % (c["state"], c["what"][:90]))
