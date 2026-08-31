#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXTERNAL REFERENCE SOURCES -- roles, freshness, and the discrepancy queue.

Built 2026-08-31 for the ballot. The audit that forced it: the hub's
Massey field was a hand-held PRESEASON capture rendering under a label
that never said so, and FIGstats' public RPI page carried a fresh
'Generated' stamp beside an SMU record (1-0, later 2-0) that its own
timestamp implied was current while the hub's evidence-qualified count
said 3-0. A fresh source timestamp is not proof of complete ingestion.

THE ROLES, fixed (rendered on the page from this table so the words
cannot drift from the code):
  * Hub POWER / resume / records: the hub's own evidence-qualified
    counting corpus only.
  * Official school / live-stat evidence: may corroborate or correct a
    result -- through the existing ledger process only.
  * FIGstats RPI: external, UNOFFICIAL resume-reference signal. Never a
    result authority, never a correction source, never a Power input.
  * Massey: external strength-reference SNAPSHOT. Never a Power input,
    never a result source.

A mismatch between an external reference and the hub is a
SOURCE-COMPARISON FACT -- it is displayed, linked to its evidence, and
changes nothing. This module has NO writer: it reads snapshots and the
season data and returns display rows. It must never import a correction
writer, and no rating module may import it (guarded both ways in
test_external_refs.py).

ACCESS: masseyratings.com is Cloudflare-challenged and on the no-scrape
hook. ncaastats.figstats.net's robots.txt disallows every non-named
agent ('User-agent: * / Disallow: /'), so it is ALSO on the no-scrape
hook and is never fetched by script -- both snapshots are manual,
browser-reviewed captures with their provenance recorded in the file.
"""

import io
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))

MASSEY_PATH = "Cody/data/massey_2026_preseason.txt"
FIG_PATH = "Cody/data/figstats_snapshots.jsonl"
MASSEY_SNAP_PATH = "Cody/data/massey_snapshots.jsonl"

ROLES = (
    ("Hub POWER / RÉSUMÉ", "the hub's own evidence-qualified "
     "counting corpus; the only input to any hub number"),
    ("Official school / live-stat evidence", "may corroborate or correct "
     "a result, through the Result Ledger process only"),
    ("FIGstats unofficial RPI", "external resume-reference signal only -- "
     "never a result authority, correction source, or Power input"),
    ("Massey preseason snapshot", "external strength-reference snapshot "
     "only -- never a Power input or result source"),
)


def massey_meta():
    """What the Massey file actually is, read from its own header.

    Absent header facts render as their honest absence -- 'capture date
    not held' is a state, never a guessed date.
    """
    p = os.path.join(REPO, MASSEY_PATH)
    out = {"label": "Massey preseason snapshot",
           "captured": None, "captured_display": "capture date not held",
           "thru": None, "truncated_at": None, "held": os.path.exists(p)}
    if not out["held"]:
        return out
    head = "".join(io.open(p, encoding="utf-8").readlines()[:8])
    m = re.search(r"Captured (\d{4}-\d{2}-\d{2})", head)
    if m:
        out["captured"] = m.group(1)
        out["captured_display"] = "captured %s" % m.group(1)
    m = re.search(r'"Using games thru ([^"]+)"', head)
    if m:
        out["thru"] = m.group(1)
    m = re.search(r"TRUNCATED AT RANK (\d+)", head)
    if m:
        out["truncated_at"] = int(m.group(1))
    return out


def massey_latest():
    """The most recent CURRENT Massey browser-reviewed snapshot, or None.

    A different thing from massey_meta() (the preseason capture that
    feeds the board's reference column): this is a dated, hashed,
    browser-reviewed read of the live ratings page, disclosure-only.
    The two states must never blur -- 'current browser-reviewed
    snapshot' vs 'preseason snapshot' is the difference between a
    Saturday data horizon and an August 15 one.
    """
    p = os.path.join(REPO, MASSEY_SNAP_PATH)
    if not os.path.exists(p):
        return None
    last = None
    for ln in io.open(p, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            try:
                last = json.loads(ln)
            except ValueError:
                continue
    return last


def fig_latest():
    """The most recent FIGstats snapshot record, or None."""
    p = os.path.join(REPO, FIG_PATH)
    if not os.path.exists(p):
        return None
    last = None
    for ln in io.open(p, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            try:
                last = json.loads(ln)
            except ValueError:
                continue
    return last


# FIG spells names its own way; norm() plus the State/Saint folds cover
# most, and the rest are explicit aliases. An unmatched name is SKIPPED
# and counted -- never guessed (R8).
FIG_ALIASES = {
    # keyed on the FOLDED form (_ref_norm output) of FIG's spelling,
    # mapped to the folded form of the hub's spelling. An entry earns its
    # place by a live unmatched row, never speculation.
    "ipfw": "purdue fort wayne",
    "houston baptist": "houston christian",
    "texas rio grande": "utrgv",
    "ark little rock": "little rock",
    "texas arlington": "ut arlington",
    "nebraska omaha": "omaha",
    "tenn martin": "ut martin",
    "southern university": "southern u",
    "st johns n y": "st johns ny",
    "st marys cal": "st marys ca",
    "citadel": "the citadel",
    "s c upstate": "usc upstate",
    "southern ill edwa": "siue",           # FIG truncates Edwardsville
    "southeast mo sta": "southeast mo st", # FIG truncates State
    "central conn st": "central conn st",
    "loyola marymount": "lmu ca",
    "unc wilmington": "uncw",
    "cal st bakersfield": "csu bakersfield",
    "miss": "ole miss",
    "charleston southern": "charleston so",
    "tex a and m commerce": "east texas a and m",
    "umkc": "kansas city",
    "seattle": "seattle u",
    "southern indiana": "southern ind",
    "army": "army west point",
    "fla intl": "fiu",
    "appalachian st": "app st",
    "college of charleston": "col of charleston",
    "long island": "liu",
    "miami fla": "miami fl",
    "iupui": "iu indy",
    "stephen f austin": "sfa",
    "fairleigh dickinson": "fdu",
    "la monroe": "ulm",
    "northern arizona": "northern ariz",
    "northern ill": "niu",
    "fla gulf coast": "fgcu",
    "cal st northridge": "csun",
    "northern iowa": "uni",
    "maryland eastern shore": "umes",
    "la lafayette": "la",
    "lamar": "lamar university",
    "east tenn st": "etsu",
    "ill chicago": "uic",
    "conn": "uconn",
    "loyola ill": "loyola chicago",
    "albany n y": "ualbany",
    "incarnate word": "uiw",
    "miss valley": "miss val",
    "miami ohio": "miami oh",
    # ⚠ NC STATE, THE COLLISION THE FALLBACK COMMENT SAID COULD NOT HAPPEN
    # (caught 2026-08-31): the hub spells it 'NC State' -> 'nc st', so
    # FIG's 'North Carolina State' missed directly and the trailing-st
    # drop landed it on NORTH CAROLINA -- two FIG rows on one hub team,
    # silently. The alias fixes the join; the fallback now also REFUSES
    # to strip into a key another FIG row already owns.
    "north caro st": "nc st",
}


# ncaa.com (the hub's spellings) abbreviates state names where FIG spells
# them out. The contraction is applied to BOTH sides, so 'Eastern Mich.'
# and 'Eastern Michigan' land on one key without either side being
# special-cased.
_CONTRACT = {
    "michigan": "mich", "illinois": "ill", "mississippi": "miss",
    "tennessee": "tenn", "washington": "wash", "colorado": "colo",
    "alabama": "ala", "kentucky": "ky", "connecticut": "conn",
    "missouri": "mo", "arkansas": "ark", "florida": "fla",
    "carolina": "caro", "virginia": "va", "georgia": "ga",
    "louisiana": "la", "atlantic": "atl", "international": "intl",
}


def _ref_norm(name):
    import sys
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    from reconcile_2025 import norm
    n = norm(name)
    n = re.sub(r"\bstate\b", "st", n)
    n = re.sub(r"\bsaint\b", "st", n)
    n = " ".join(_CONTRACT.get(w, w) for w in n.split())
    return n


_fig_norm = _ref_norm
_hub_norm = _ref_norm


def hub_records():
    """team display name -> 'W-L' from the hub's counting corpus (D-I
    finals that count; the same list the standings tally from)."""
    import sys
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import season_counts as SC
    doc = json.load(io.open(os.path.join(
        REPO, "data", "data_%d.json" % SEASON), encoding="utf-8"))
    id2n = {str(t["team_id"]): t.get("name_short")
            for t in doc.get("teams") or []}
    d1 = {str(t["team_id"]) for t in doc.get("teams") or []
          if t.get("division") == 1}
    games = doc.get("games") or []
    wl = {}
    for g in SC.countable(games, SEASON, d1_only=True):
        win = str(g.get("winner_team_id"))
        for t in g.get("teams") or []:
            tid = str(t.get("team_id"))
            if tid not in d1:
                continue
            nm = id2n.get(tid)
            if not nm:
                continue
            w, l = wl.get(nm, (0, 0))
            wl[nm] = (w + 1, l) if tid == win else (w, l + 1)
    return {nm: "%d-%d" % r for nm, r in wl.items()}


def discrepancies(fig=None, hub=None):
    """External-reference mismatch rows. READ-ONLY, display-only.

    Each row is a source-comparison fact: FIG's displayed W-L vs the
    hub's evidence-qualified counting W-L. NOT a claim that the hub is
    right by default, and never an input to anything.
    """
    fig = fig if fig is not None else fig_latest()
    if not fig:
        return {"items": [], "matched": 0, "unmatched": [],
                "fig": None}
    hub = hub if hub is not None else hub_records()
    hub_by_norm = {}
    for nm, rec in hub.items():
        hub_by_norm[_hub_norm(nm)] = (nm, rec)
    # every FIG key up front, so the trailing-st fallback can refuse to
    # strip into a key ANOTHER FIG row already owns (the NC State trap)
    fig_keys = set()
    for row in fig.get("rows") or []:
        if row.get("team") and row.get("parse") != "failed":
            k = _fig_norm(row["team"])
            fig_keys.add(FIG_ALIASES.get(k, k))
    items, unmatched, matched = [], [], 0
    taken = {}                       # hub team -> fig team that claimed it
    collisions = []                  # two FIG rows on one hub team = a
                                     # join error, surfaced, never absorbed
    for row in fig.get("rows") or []:
        team = row.get("team")
        if not team or row.get("parse") == "failed":
            continue
        key = _fig_norm(team)
        key = FIG_ALIASES.get(key, key)
        got = hub_by_norm.get(key)
        if not got and key.endswith(" st") and key[:-3] not in fig_keys:
            # FIG says 'Sam Houston State' where the hub says 'Sam
            # Houston'. Safe only when the stripped key is not itself a
            # FIG team -- 'north caro st' stripping into North Carolina
            # is exactly the wrong-team join R8 exists for.
            got = hub_by_norm.get(key[:-3])
        if not got:
            unmatched.append(team)
            continue
        hub_nm, hub_rec = got
        if hub_nm in taken:
            collisions.append((taken[hub_nm], team, hub_nm))
            continue
        taken[hub_nm] = team
        matched += 1
        if (row.get("record") or "").strip() != hub_rec:
            items.append({
                "team": hub_nm, "fig_team": team,
                "fig_record": row.get("record"),
                "fig_rank": row.get("rank"),
                "hub_record": hub_rec,
            })
    items.sort(key=lambda x: (x["fig_rank"] or 9999))
    return {"items": items, "matched": matched, "unmatched": unmatched,
            "matched_names": sorted(taken),
            "collisions": collisions,
            "fig": {k: fig.get(k) for k in
                    ("retrieved_utc", "publisher_generated", "url",
                     "source_label", "content_sha256", "n_rows",
                     "variant")}}


def absent_from_fig(universe, d=None):
    """Hub teams the held FIG snapshot does not list.

    An absent team is 'not listed in held FIG snapshot' -- never an
    unranked team, a bad RPI, or a reference mismatch. Computed against
    the hub's own team universe (the board's 348), passed in so this
    module invents no membership list of its own.
    """
    d = d if d is not None else discrepancies()
    if not d.get("fig"):
        return []
    have = {_hub_norm(n) for n in d.get("matched_names") or []}
    return [t for t in universe if _hub_norm(t) not in have]


if __name__ == "__main__":
    mm = massey_meta()
    print("Massey: %s, %s%s" % (mm["label"], mm["captured_display"],
          (", truncated at rank %d" % mm["truncated_at"])
          if mm["truncated_at"] else ""))
    d = discrepancies()
    f = d["fig"]
    if f:
        print("FIG: generated %s (publisher) / retrieved %s (hub), %d rows"
              % (f["publisher_generated"], f["retrieved_utc"], f["n_rows"]))
    print("matched %d, unmatched %d, mismatches %d"
          % (d["matched"], len(d["unmatched"]), len(d["items"])))
    for it in d["items"][:12]:
        print("  REFERENCE MISMATCH: %(team)s -- FIGstats %(fig_record)s; "
              "hub %(hub_record)s" % it)
    if d["unmatched"]:
        print("  unmatched FIG names:", ", ".join(d["unmatched"][:12]))
