#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROVENANCE + AVAILABILITY TRUTH PASS (2026-08-31).

Two walls, both behavioral (the page's OWN functions run under node --
source-string proofs are what let the Watch Now duplication and the a.ep
comparator survive their guards):

A. A corrected result can never wear the feed's badge. The generic
   "official scoreboard" tag misattributes the very evidence that fixed
   SMU-UC Davis; a corrected fixture renders a correction-aware label
   naming the evidencing schools, and an ordinary feed final keeps the
   generic tag.

B. Availability truth. A current sourced status (Wollard) and a sourced
   match incident (Heaney) are DIFFERENT claims: an incident can never
   render as a current-out designation, a status can never exceed its
   source's words (no season-ending, no hospital, no diagnosis), and the
   global "none currently" copy cannot render while either exists.
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def jsfn(src, name):
    """Extract `function name(...) {...}` -- comment- and string-aware.

    The non-greedy-regex extractor truncated at inner functions and a
    comment-blind matcher lost sync on a quote inside /* */ (both paid
    for on 2026-08-27); this one tracks both.
    """
    m = re.search(r"function %s\s*\(" % re.escape(name), src)
    if not m:
        return None
    i = src.index("{", m.end() - 1)
    depth, j, n = 0, i, len(src)
    instr, esc_n, comment = None, False, None
    while j < n:
        ch = src[j]
        if comment:
            if comment == "//" and ch == "\n":
                comment = None
            elif comment == "/*" and src[j:j + 2] == "*/":
                comment = None
                j += 1
        elif instr:
            if esc_n:
                esc_n = False
            elif ch == "\\":
                esc_n = True
            elif ch == instr:
                instr = None
        elif ch in "'\"`":
            instr = ch
        elif src[j:j + 2] == "//":
            comment = "//"
        elif src[j:j + 2] == "/*":
            comment = "/*"
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def node(js):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True,
                           timeout=60)
        return r.returncode, r.stdout, r.stderr
    finally:
        os.unlink(path)


def main():
    page = io.open(PAGE, encoding="utf-8").read()
    fns = {}
    for name in ("esc", "corrSchools", "provenanceTag", "tdLatestFinal",
                 "avMeta", "avStatusRow", "avIncidentRow", "avStatusLine",
                 "renderAvail", "pdAvailability", "recapHTML"):
        fns[name] = jsfn(page, name)
        if not fns[name]:
            check("page function %s extracted" % name, False, "missing")
            return finish()

    m = re.search(r"const CONFIDENCE = (.*?);\n", page)
    conf = json.loads(m.group(1)) if m else {}
    m = re.search(r"const AVAIL = (.*?);\n", page)
    avail = json.loads(m.group(1)) if m else {}

    print("A. CORRECTED-RESULT PROVENANCE (the page's own renderers)")
    corr_row = [r for r in conf.get("finals", [])
                if r.get("result_corrected")]
    check("the real payload carries a corrected final", bool(corr_row))

    stub = {"finals": [
        {"gid": "111", "result_corrected": True, "overall": "corrected",
         "corr_evidence": [{"school": "SMU"}, {"school": "UC Davis"}]},
        {"gid": "222", "overall": "reconciled"},
        {"gid": "333", "overall": "confirmed"}]}
    js = (fns["esc"] + "\n" + fns["corrSchools"] + "\n" +
          fns["provenanceTag"] + "\n" +
          "const CONFIDENCE = %s;\n" % json.dumps(stub) +
          "console.log(JSON.stringify({c: provenanceTag('111'), "
          "n: provenanceTag('222'), real: null}));")
    rc, out, err = node(js)
    check("provenanceTag runs under node", rc == 0, err)
    if rc == 0:
        d = json.loads(out.strip().splitlines()[-1])
        check("a corrected fixture CANNOT render bare 'official "
              "scoreboard'", "official scoreboard" not in d["c"].lower())
        check("...it names the evidencing schools",
              "CORRECTED · SMU + UC Davis official evidence" in d["c"],
              d["c"])
        check("...and points at the Result Ledger for the drill",
              "Result Ledger" in d["c"])
        check("a normal feed final KEEPS the generic tag",
              d["n"] == '<i class="rcsrctag">official scoreboard</i>',
              d["n"])

    # the REAL payload, end to end
    js2 = (fns["esc"] + "\n" + fns["corrSchools"] + "\n" +
           fns["provenanceTag"] + "\n" +
           "const CONFIDENCE = %s;\n" % json.dumps(
               {"finals": conf.get("finals", [])}) +
           "console.log(provenanceTag('6626259'));")
    rc, out, err = node(js2)
    check("SMU-UC Davis renders the correction-aware tag on the real "
          "payload", rc == 0 and
          "CORRECTED · SMU + UC Davis official evidence" in out, out or err)

    # (the recap's "match-aligned box" tag is a DIFFERENT claim -- box
    # provenance, not result provenance -- and correctly stays its own)
    check("recapHTML never hard-codes the result badge (one definition, "
          "in provenanceTag)",
          "official scoreboard" not in fns["recapHTML"]
          and "provenanceTag(gid)" in fns["recapHTML"])

    # the team-log chip
    js3 = (fns["esc"] + "\n" + fns["corrSchools"] + "\n" +
           "function logo(){return ''}\n" +
           "const CONFIDENCE = %s;\n" % json.dumps(stub) +
           fns["tdLatestFinal"] + "\n" +
           "const t={played:[{gid:'111',mine:3,theirs:2,opp:'X',home:1,"
           "sets:[[27,25]]}]};\n"
           "const t2={played:[{gid:'333',mine:3,theirs:0,opp:'Y',home:0,"
           "sets:[[25,20]]}]};\n"
           "console.log(JSON.stringify({c:tdLatestFinal(t,'A'),"
           "n:tdLatestFinal(t2,'B')}));")
    rc, out, err = node(js3)
    check("team-log chip runs under node", rc == 0, err)
    if rc == 0:
        d = json.loads(out.strip().splitlines()[-1])
        check("a corrected latest final wears the CORRECTED chip",
              "CORRECTED · SMU + UC Davis official evidence" in d["c"],
              d["c"])
        check("an ordinary confirmed final keeps its own chip",
              "Cross-source" in d["n"] and "CORRECTED" not in d["n"])

    # ledger drill: the feed's record is marked SUPERSEDED for a corrected row
    check("ledger drill marks the feed's claim superseded on a corrected "
          "row", "SUPERSEDED for the" in page
          and "r.result_corrected" in page)

    print("\n  [NEG] negative controls -- each mutation must be caught")
    broken = fns["provenanceTag"].replace("r.result_corrected",
                                          "false && r.result_corrected")
    js4 = (fns["esc"] + "\n" + fns["corrSchools"] + "\n" + broken + "\n" +
           "const CONFIDENCE = %s;\n" % json.dumps(stub) +
           "console.log(provenanceTag('111'));")
    rc, out, err = node(js4)
    check("[NEG] a provenanceTag stripped of its corrected branch fails "
          "the invariant",
          rc == 0 and "official scoreboard" in out
          and "CORRECTED" not in out)

    print("\nB. AVAILABILITY TRUTH")
    import availability_desk as AD
    ev = json.load(io.open(os.path.join(
        REPO, "data/raw/2026/availability_evidence.json"),
        encoding="utf-8"))["players"]
    woll = ev["Purdue|Kenna Wollard"][0]
    hean = ev["Purdue|Grace Heaney"][0]
    today = "2026-08-31"

    check("Wollard's entry is a current sourced STATUS",
          AD.entry_state(woll, today) == "status",
          AD.entry_state(woll, today))
    check("Heaney's entry is a sourced match INCIDENT, not a status",
          AD.entry_state(hean, today) == "incident",
          AD.entry_state(hean, today))
    check("...so it can never join the sourced-status count",
          AD.entry_state(hean, today) != "status")

    # Wollard cannot be escalated: the claim vocabulary is CLOSED
    for rogue in ("season_ending", "out_for_season", "hospitalized",
                  "injured", "done_for_year"):
        e = dict(woll, claim=rogue)
        check("[NEG] a rogue claim %r can never become a status" % rogue,
              AD.entry_state(e, today) == "invalid",
              AD.entry_state(e, today))
    # Heaney cannot be silently promoted: an incident stripped of its date
    # is invalid, never a status
    check("[NEG] an incident without its date binds to nothing",
          AD.entry_state(dict(hean, incident_date=None), today) == "invalid")

    art = json.load(io.open(os.path.join(
        REPO, "data/availability_desk_2026.json"), encoding="utf-8"))
    sts = [s["player"] for s in art["statuses"]]
    incs = [s["player"] for s in art["incidents"]]
    check("artifact: Wollard is the status, Heaney the incident",
          sts == ["Kenna Wollard"] and incs == ["Grace Heaney"],
          (sts, incs))
    check("artifact counts agree",
          art["meta"]["counts"]["statuses"] == 1
          and art["meta"]["counts"]["incidents"] == 1)

    wrow = art["statuses"][0]
    hrow = art["incidents"][0]

    print("\n  the page's own rows, under node")
    avfns = (fns["esc"] + "\n" + fns["avMeta"] + "\n" +
             fns["avStatusRow"] + "\n" + fns["avIncidentRow"] + "\n")
    js5 = (avfns +
           "const w = %s, h = %s;\n" % (json.dumps(wrow), json.dumps(hrow)) +
           "console.log(JSON.stringify({w: avStatusRow(w), "
           "h: avIncidentRow(h)}));")
    rc, out, err = node(js5)
    check("status/incident rows run under node", rc == 0, err)
    if rc == 0:
        d = json.loads(out.strip().splitlines()[-1])
        w, h = d["w"], d["h"]
        check("Wollard: her own words render verbatim",
              "unexpected health issue that will keep me away fro a "
              "little while" in w)
        check("Wollard: away from team / unavailable, nothing stronger",
              "away from team / unavailable (sourced)" in w.lower()
              or "Away from team / unavailable (sourced)" in w)
        for banned in ("season-ending", "season ending", "hospital",
                       "surgery", "diagnos", "out for the season",
                       "torn", "acl"):
            check("Wollard: %r cannot render" % banned,
                  banned not in w.lower())
        check("Wollard: source link + retrieval + effective + review-by "
              "all render",
              "sports.yahoo.com" in w and "retrieved 2026-08-31" in w
              and "effective 2026-08-27" in w and "review by 2026-09-13" in w,
              w)
        check("Heaney: dated incident, availability stated UNKNOWN",
              "sourced match incident, 2026-08-28" in h
              and "current availability unknown" in h
              and "pending a team update" in h, h)
        for banned in ("unavailable (sourced)", "away from team",
                       "confirmed_unavailable", "ruled out", "season"):
            check("Heaney: %r cannot render on the incident row" % banned,
                  banned not in h.lower())
        check("Heaney: the recap's exact sentence renders",
              "midway through the second set due to injury" in h)
        check("Heaney: source + retrieval + review-by render",
              "cloudfront.net" in h and "review by 2026-09-06" in h)

    print("\n  the global 'none currently' copy is GATED on both")
    dom = ("const _els={};\n"
           "function el(id){return _els[id]=_els[id]||{innerHTML:''}}\n"
           "const document={getElementById:el};\n")
    render_stub = (fns["esc"] + "\n" + fns["avMeta"] + "\n" +
                   fns["avStatusRow"] + "\n" + fns["avIncidentRow"] + "\n" +
                   dom)

    def run_render(avail_obj, fn_src=None):
        js = (render_stub +
              "const AVAIL = %s;\n" % json.dumps(avail_obj) +
              (fn_src or fns["renderAvail"]) + "\nrenderAvail();\n" +
              "console.log(JSON.stringify({st:_els['avstatuses'].innerHTML,"
              "inc:(_els['avincidents']||{}).innerHTML||''}));")
        rc, out, err = node(js)
        return (json.loads(out.strip().splitlines()[-1])
                if rc == 0 else {"err": err})

    r1 = run_render({"meta": {"counts": {}}, "statuses": [],
                     "incidents": [hrow], "signals": [], "expired": []})
    check("no status + a live incident -> the 'none' copy CANNOT render",
          "No attributable public source" not in r1.get("st", "X"),
          r1)
    check("...and the copy points at the incident section",
          "sourced match incident" in r1.get("st", ""))
    r2 = run_render({"meta": {"counts": {}}, "statuses": [],
                     "incidents": [], "signals": [], "expired": []})
    check("nothing at all -> the honest default renders",
          "No attributable public source currently" in r2.get("st", ""))
    r3 = run_render(dict({"meta": {"counts": {}}, "signals": [],
                          "expired": []},
                         statuses=[wrow], incidents=[hrow]))
    check("both exist -> both sections carry their rows",
          "Kenna Wollard" in r3.get("st", "")
          and "Grace Heaney" in r3.get("inc", ""))
    broken_render = fns["renderAvail"].replace(
        "(AVAIL.incidents || []).length\n", "false\n", 1)
    if broken_render != fns["renderAvail"]:
        rb = run_render({"meta": {"counts": {}}, "statuses": [],
                         "incidents": [hrow], "signals": [], "expired": []},
                        fn_src=broken_render)
        check("[NEG] a renderAvail blinded to incidents fails the gate",
              "No attributable public source" in rb.get("st", ""))
    else:
        check("[NEG] mutation target found in renderAvail", False)

    print("\n  the player dossier links the evidence")
    js6 = (fns["esc"] + "\n" + "function routeFor(){return '#avail'}\n" +
           "const AVAIL = %s;\n" % json.dumps(
               {"meta": art["meta"], "statuses": art["statuses"],
                "incidents": art["incidents"], "signals": [],
                "expired": []}) +
           fns["pdAvailability"] + "\n" +
           "console.log(JSON.stringify({"
           "w: pdAvailability({name:'Kenna Wollard', team:'Purdue'}),"
           "h: pdAvailability({name:'Grace Heaney', team:'Purdue'}),"
           "o: pdAvailability({name:'Nobody Here', team:'Nowhere'})}));")
    rc, out, err = node(js6)
    check("pdAvailability runs under node", rc == 0, err)
    if rc == 0:
        d = json.loads(out.strip().splitlines()[-1])
        check("Wollard's dossier shows the sourced status + desk link",
              "Away from team / unavailable (sourced)" in d["w"]
              and "Availability Desk" in d["w"], d["w"])
        check("Heaney's dossier shows the incident, availability unknown",
              "Sourced match incident, 2026-08-28" in d["h"]
              and "current availability unknown" in d["h"], d["h"])
        check("...never the no-information default",
              "No availability information" not in d["w"]
              and "No availability information" not in d["h"])
        check("an unmentioned player keeps the honest default",
              "No availability information" in d["o"])

    print("\n  the public page carries none of it")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub_p):
        pub = io.open(pub_p, encoding="utf-8").read()
        for frag in ("unexpected health issue",
                     "midway through the second set",
                     "match incident", "avIncidentRow",
                     "current availability unknown"):
            check("public page lacks %r" % frag, frag not in pub)

    return finish()


def finish():
    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL PROVENANCE + AVAILABILITY TRUTH GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
