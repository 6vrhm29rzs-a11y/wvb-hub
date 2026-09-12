#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest a MANUALLY CAPTURED Massey NCAA-D1 women's volleyball ratings table.

⚠ DOES NOT FETCH. masseyratings.com is on the no-scrape hook (third-party
ratings we hold no licence to republish). The input is text read out of
Cody's own browser while reading the page normally -- the manual-snapshot
route Massey and FIGstats have always used here.

⚠ AND MASSEY BLOCKS THE FILE ROUTE THAT WORKS FOR EVOLLVE. A blob download
is refused by its CSP (measured 2026-09-12: the same three lines that produce
a file on evollve.net produce nothing here), so the table comes across as
text rather than as a saved file. Worth knowing before re-inventing it.

EXTERNAL REFERENCE ONLY -- nothing here feeds POWER, Digby, the resume or any
rating, and that boundary is guarded in both directions by test_external_refs.

Columns, in Massey's own order:
  Team~Conf | Rec~Pct | Delta | Rat | Pwr | HFA | SoS | SSF | EW | EL
Three of those are quantities this project has listed as gaps and never
computed: HFA is a PER-TEAM home advantage, SoS is schedule strength played
and SSF schedule strength still to come.
"""
import hashlib
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "Cody", "data", "massey_snapshots.jsonl")

# Massey's own spellings, where they differ from the hub's beyond what
# _ref_norm already folds. Each is a DIFFERENT NAME for the same school, not
# a guess: kept explicit so an unmatched row stays visible rather than being
# absorbed by a loose rule (the NC State / North Carolina collision).
ALIASES = {
    "abilene chr": "abilene christian",
    "appalachian st": "app st",
    "army": "army west point",
    "c mich": "central mich",
    "cent ark": "central ark",
    "conn": "uconn",
    "e ill": "eastern ill",
    "e ky": "eastern ky",
    "e mich": "eastern mich",
    "e wash": "eastern wash",
    "fl atl": "fla atl",
    "fla intl": "fiu",
    "g wash": "george wash",
    "houston chr": "houston christian",
    "incarnate word": "uiw",
    "lamar": "lamar university",
    "miss": "ole miss",
    "mo kc": "kansas city",
    "n colo": "northern colo",
    "n ill": "niu",
    "n ky": "northern ky",
    "nc a and t": "n c a and t",
    "nc central": "n c central",
    "northern iowa": "uni",
    "s caro st": "south caro st",
    "s ill": "southern ill",
    "sc upstate": "usc upstate",
    "se la": "southeastern la",
    "se mo st": "southeast mo st",
    "st johns": "st johns ny",
    "tam c christi": "a and m corpus christi",
    "unc wilmington": "uncw",
    "w caro": "western caro",
    "w ill": "western ill",
    "w mich": "western mich",
    "alcorn st": "alcorn",
    "american univ": "american",
    "ark little rock": "little rock",
    "cs bakersfield": "csu bakersfield",
    "cs fullerton": "cal st fullerton",
    "cs northridge": "csun",
    "cs sacramento": "sacramento st",
    "cal baptist": "california baptist",
    "central conn": "central conn st",
    "citadel": "the citadel",
    "coastal car": "coastal caro",
    "col charleston": "col of charleston",
    "f dickinson": "fdu",
    "il chicago": "uic",
    "iupui": "iu indy",
    "kennesaw": "kennesaw st",
    "kent": "kent st",
    "liu brooklyn": "liu",
    "loy marymount": "lmu ca",
    "loyola md": "loyola maryland",
    "md e shore": "umes",
    "ms valley st": "miss val",
    "mtsu": "middle tenn",
    "mcneese st": "mcneese",
    "n dakota st": "north dakota st",
    "ne omaha": "omaha",
    "nicholls st": "nicholls",
    "northern arizona": "northern ariz",
    "northwestern la": "northwestern st",
    "pfw": "purdue fort wayne",
    "s dakota st": "south dakota st",
    "sf austin": "sfa",
    "suny albany": "ualbany",
    "sam houston st": "sam houston",
    "seattle": "seattle u",
    "southern indiana": "southern ind",
    "southern univ": "southern u",
    "tn martin": "ut martin",
    "tx southern": "texas southern",
    "usc": "southern california",
    "ut san antonio": "utsa",
    "wi green bay": "green bay",
    "wi milwaukee": "milwaukee",
    "wku": "western ky",
}


def parse(path):
    rows = []
    for line in io.open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        c = line.split("|")
        if len(c) != 10:
            raise SystemExit("row has %d fields, expected 10: %r" % (len(c), line[:80]))
        team, _, conf = c[0].partition("~")
        rec, _, pct = c[1].partition("~")

        def vr(cell):
            if "~" in cell:
                a, _, b = cell.partition("~")
                try:
                    return float(b), int(a)
                except ValueError:
                    return None, None
            try:
                return float(cell), None
            except ValueError:
                return None, None

        rat, rat_rank = vr(c[3])
        pwr, pwr_rank = vr(c[4])
        sos, sos_rank = vr(c[6])
        ssf, ssf_rank = vr(c[7])
        try:
            hfa = float(c[5])
        except ValueError:
            hfa = None
        try:
            ew, el = float(c[8]), float(c[9])
        except ValueError:
            ew = el = None
        rows.append({"team_raw": team.strip(), "conf": conf.strip(),
                     "record": rec.strip(), "win_pct": float(pct) if pct else None,
                     "delta": c[2].strip() or None,
                     "rating": rat, "rating_rank": rat_rank,
                     "power": pwr, "power_rank": pwr_rank,
                     "home_adv": hfa,
                     "sos": sos, "sos_rank": sos_rank,
                     "sched_strength_future": ssf, "ssf_rank": ssf_rank,
                     "expected_wins": ew, "expected_losses": el})
    return rows


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/massey_raw.txt"
    through = os.environ.get("MASSEY_THROUGH", "Using games thru Fri, Sep 11, 2026")
    rows = parse(src)

    from external_refs import _ref_norm
    hub = json.load(io.open(os.path.join(REPO, "data", "data_%d.json" % SEASON),
                            encoding="utf-8"))
    by_key = {}
    for t in (hub.get("teams") or []):
        n = t.get("name_short") if isinstance(t, dict) else None
        if n:
            by_key.setdefault(_ref_norm(n), n)

    hit = 0
    for r in rows:
        k = _ref_norm(r["team_raw"])
        k = ALIASES.get(k, k)
        r["hub_team"] = by_key.get(k) or by_key.get(_ref_norm(k))
        if r["hub_team"]:
            hit += 1

    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    snap = {
        "source_label": "Massey current browser-reviewed snapshot",
        "role": "external strength reference -- never a POWER input or result source",
        "url": "https://masseyratings.com/cvol/ncaa-d1/ratings",
        "retrieved_utc": os.environ.get("MASSEY_RETRIEVED", ""),
        "publisher_through": through,
        "publisher_through_note": ("the page's own header line, verbatim -- the "
                                   "source's data horizon, DISTINCT from "
                                   "retrieved_utc, never collapsed into one date"),
        "access": ("manual browser review in Cody's own Chrome; masseyratings.com "
                   "is on the no-scrape hook and is never fetched"),
        "parser": "browser transcription -> scripts/ingest_massey.py",
        "status": "ok",
        "content_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "content_sha256_of": "the parsed rows, sorted (%d teams)" % len(rows),
        "coverage": "%d listed, %d resolved to hub teams, %d unresolved"
                    % (len(rows), hit, len(rows) - hit),
        "n_rows": len(rows), "n_listed": len(rows),
        "rows": [dict(r, rank=r.get("rating_rank"), team=r["team_raw"]) for r in rows],
    }
    with io.open(OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
    print("massey snapshot: %d rows, %d resolved, %d unresolved"
          % (len(rows), hit, len(rows) - hit))
    if snap["unresolved"]:
        print("  unresolved:", ", ".join(snap["unresolved"]))
    print("  ->", OUT)


if __name__ == "__main__":
    main()
