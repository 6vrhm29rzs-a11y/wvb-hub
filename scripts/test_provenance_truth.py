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
                 "avMeta", "avSupportRow", "avCard", "avStatusLine",
                 "renderAvail", "pdAvailability", "recapHTML",
                 "availWithheldNote"):
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

    # Wollard cannot be escalated: the claim vocabulary is CLOSED.
    # (out_for_season joined the closed set 2026-09-01 for SOURCED
    # season-ending reports -- Vander Wal below -- so it is no longer a
    # rogue string; diagnosis words remain invalid.)
    for rogue in ("season_ending", "hospitalized", "injured",
                  "done_for_year", "acl_tear"):
        e = dict(woll, claim=rogue)
        check("[NEG] a rogue claim %r can never become a status" % rogue,
              AD.entry_state(e, today) == "invalid",
              AD.entry_state(e, today))
    check("Wollard's own claim stays confirmed_unavailable, nothing "
          "stronger", woll.get("claim") == "confirmed_unavailable")
    # Heaney cannot be silently promoted: an incident stripped of its date
    # is invalid, never a status
    check("[NEG] an incident without its date binds to nothing",
          AD.entry_state(dict(hean, incident_date=None), today) == "invalid")

    art = json.load(io.open(os.path.join(
        REPO, "data/availability_desk_2026.json"), encoding="utf-8"))
    sts = [s["player"] for s in art["statuses"]]
    incs = [s["player"] for s in art["incidents"]]
    check("artifact: Wollard a status, Heaney the ONLY incident",
          "Kenna Wollard" in sts and incs == ["Grace Heaney"],
          (sts, incs))
    check("Vander Wal: two separately-attributed season-ending sources, "
          "both statuses",
          sts.count("Abby Vander Wal") == 2
          and all(s["claim"] == "out_for_season" for s in art["statuses"]
                  if s["player"] == "Abby Vander Wal"))
    check("...and she can NEVER render as merely a match incident",
          "Abby Vander Wal" not in incs)
    vw = [s for s in art["statuses"] if s["player"] == "Abby Vander Wal"]
    check("the MRI report and the coach outlook are separate sources",
          len({s["url"] for s in vw}) == 2)
    check("...neither implies a Texas Athletics release",
          all("beat_report" == s["kind"] for s in vw)
          and all("release is held" in (s.get("note") or "")
                  or "Not a Texas Athletics release" in (s.get("note") or "")
                  for s in vw))
    hean_art = [s for s in art["incidents"]
                if s["player"] == "Grace Heaney"][0]
    check("Heaney's incident carries the Purdue-preview wording",
          hean_art.get("summary")
          == "Left Creighton match in Set 2 with a lower-leg injury"
          and "purduesports.com" in (hean_art.get("url") or ""))
    check("artifact counts agree",
          art["meta"]["counts"]["statuses"] == len(sts)
          and art["meta"]["counts"]["incidents"] == 1)

    wrow = [x for x in art["statuses"]
            if x["player"] == "Kenna Wollard"][0]
    hrow = art["incidents"][0]
    vrows = [x for x in art["statuses"]
             if x["player"] == "Abby Vander Wal"]

    print("\n  the page's own rows, under node")
    avfns = (fns["esc"] + "\n" + (jsfn(page, "avClaimLabel") or "") +
             "\n" + fns["avMeta"] + "\n" +
             fns["avSupportRow"] + "\n" + fns["avCard"] + "\n")
    proj = {(c["team"], c["player"]): c for c in art["projection"]}
    wcard = proj[("Purdue", "Kenna Wollard")]
    hcard = proj[("Purdue", "Grace Heaney")]
    vcard = proj[("Texas", "Abby Vander Wal")]
    js5 = (avfns +
           "const w = %s, h = %s;\n" % (json.dumps(wcard),
                                         json.dumps(hcard)) +
           "console.log(JSON.stringify({w: avCard(w), "
           "h: avCard(h)}));")
    rc, out, err = node(js5)
    check("status/incident rows run under node", rc == 0, err)
    if rc == 0:
        d = json.loads(out.strip().splitlines()[-1])
        w, h = d["w"], d["h"]
        check("Wollard: her own words render verbatim",
              "unexpected health issue that will keep me away fro a "
              "little while" in w)
        check("Wollard: away from team / unavailable, nothing stronger",
              "Away from team / unavailable" in w and "(sourced)" in w
              and "Out for the" not in w)
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
              "Sourced match incident, 2026-08-28" in h
              and "current availability unknown" in h
              and "pending a team update" in h, h)
        # 'season' as a bare substring would trip on the quote's own
        # "preseason Player of the Year Watch List" -- ban the CLAIMS,
        # not the letters (the Massey 'not current' scrub lesson)
        for banned in ("unavailable (sourced)", "away from team",
                       "confirmed_unavailable", "ruled out",
                       "out for the season", "season-ending"):
            check("Heaney: %r cannot render on the incident row" % banned,
                  banned not in h.lower())
        check("Heaney: Purdue's own preview wording renders",
              "leaving the match in Set 2 due to a lower leg injury" in h)
        check("Heaney: source + retrieval + review-by render",
              "purduesports.com" in h and "review by" in h)
        check("Heaney: the strengthened Purdue-preview wording renders",
              "Left Creighton match in Set 2 with a lower-leg injury" in h)
        check("Heaney: cannot render season-ending or diagnostic language",
              not any(b in h.lower() for b in
                      ("out for the season", "season-ending", "acl",
                       "mri", "diagnos")))

    js5b = (avfns +
            "const c = %s;\n" % json.dumps(vcard) +
            "console.log(JSON.stringify(avCard(c)));")
    rc, out, err = node(js5b)
    check("Vander Wal rows run under node", rc == 0, err)
    if rc == 0:
        v = json.loads(out.strip().splitlines()[-1])
        check("Vander Wal: ONE current status card -- never two rows, "
              "never a mere incident",
              v.count("Out for the 2026 season") == 1
              and "2 supporting reports" in v
              and "sourced match incident" not in v)
        check("...both summaries render: the MRI report and the coach "
              "outlook, separately",
              "Left ACL tear reported after Monday MRI" in v
              and "Coach-reported: expected to miss the remainder of "
                  "2026" in v)
        check("...each with its own source link",
              "sports.yahoo.com" in v and "si.com" in v)

    print("\n  the global 'none currently' copy is GATED on both")
    dom = ("const _els={};\n"
           "function el(id){return _els[id]=_els[id]||{innerHTML:''}}\n"
           "const document={getElementById:el};\n")
    render_stub = (fns["esc"] + "\n" + (jsfn(page, "avClaimLabel") or "")
                   + "\n" + fns["avMeta"] + "\n" +
                   fns["avSupportRow"] + "\n" + fns["avCard"] + "\n" +
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
                     "incidents": [hrow], "projection": [hcard],
                     "signals": [], "expired": []})
    check("no status + a live incident -> the 'none' copy CANNOT render",
          "No attributable public source" not in r1.get("st", "X"),
          r1)
    check("...and the copy points at the incident section",
          "sourced match incident" in r1.get("st", ""))
    r2 = run_render({"meta": {"counts": {}}, "statuses": [],
                     "incidents": [], "projection": [], "signals": [],
                     "expired": []})
    check("nothing at all -> the honest default renders",
          "No attributable public source currently" in r2.get("st", ""))
    r3 = run_render(dict({"meta": {"counts": {}}, "signals": [],
                          "expired": []},
                         statuses=[wrow], incidents=[hrow],
                         projection=[wcard, hcard]))
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
    js6 = (avfns +
           "\nfunction routeFor(){return '#avail'}\n" +
           "const AVAIL = %s;\n" % json.dumps(
               {"meta": art["meta"], "statuses": art["statuses"],
                "incidents": art["incidents"],
                "projection": art["projection"], "signals": [],
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
              "Away from team / unavailable" in d["w"]
              and "(sourced)" in d["w"]
              and "Availability Desk" in d["w"], d["w"])
        check("Heaney's dossier shows the incident, availability unknown",
              "Sourced match incident, 2026-08-28" in d["h"]
              and "current availability unknown" in d["h"], d["h"])
        check("...never the no-information default",
              "No availability information" not in d["w"]
              and "No availability information" not in d["h"])
        check("an unmentioned player keeps the honest default",
              "No availability information" in d["o"])

    print("\n  ONE PROJECTION, EVERY SURFACE (truth repair 2026-09-01)")
    check("two evidence records -> ONE current card with two supports",
          vcard["state"] == "status" and vcard["n_supports"] == 2
          and vcard["headline"] == "Out for the 2026 season")
    # a synthetic pair proves the grouping is structural, not data luck
    synth = {"T|P": [
        dict(wrow, team="T", player="P", claim="confirmed_unavailable",
             kind="beat_report", url="https://a.example/1"),
        dict(wrow, team="T", player="P", claim="out_for_season",
             kind="beat_report", url="https://a.example/2")]}
    pcards = AD.projection(synth, today)
    check("...and the strongest ranked claim heads the single card",
          len(pcards) == 1 and pcards[0]["headline"]
          == "Out for the 2026 season" and pcards[0]["n_supports"] == 2)
    import source_intel as SI
    av_claims = [c for c in SI.claims(2026, today=today)
                 if c["type"] == "availability"
                 and c["state"] != "expired"]
    by_player = {}
    for c in av_claims:
        by_player.setdefault(c["subject"].get("player"), []).append(c)
    check("intel: exactly one availability claim per player",
          all(len(v) == 1 for v in by_player.values()),
          {k: len(v) for k, v in by_player.items()})
    kw = (by_player.get("Kenna Wollard") or [{}])[0]
    gh = (by_player.get("Grace Heaney") or [{}])[0]
    vw_c = (by_player.get("Abby Vander Wal") or [{}])[0]
    check("Kenna can NEVER downgrade to 'unconfirmed'",
          kw.get("state") == "confirmed_official"
          and "unconfirmed" not in (kw.get("what") or "").lower()
          and "sourced availability status" in (kw.get("what") or ""))
    check("Grace can NEVER downgrade to a generic signal",
          gh.get("state") == "confirmed_official"
          and "signal" not in (gh.get("what") or "").lower()
          and "sourced match incident" in (gh.get("what") or ""))
    check("Vander Wal's intel claim matches the Desk headline",
          "Out for the 2026 season" in (vw_c.get("what") or "")
          and len(vw_c.get("sources") or []) == 2)
    # cross-surface wording agreement, from the built page payload
    m2 = re.search(r"const TEAMS = (\{.*?\});\n", page, re.S)
    if m2:
        tp = json.loads(m2.group(1).replace("<\\/", "</"))
        tx = tp.get("Texas") or {}
        pu = tp.get("Purdue") or {}
        check("STALE PRESENT TENSE: Texas's scout note is withheld while "
              "Vander Wal is out for the season",
              tx.get("digby") is None
              and tx.get("digby_avail_withheld") == ["Abby Vander Wal"],
              tx.get("digby_avail_withheld"))
        check("...and Purdue's while Wollard is unavailable",
              pu.get("digby") is None
              and "Kenna Wollard" in (pu.get("digby_avail_withheld") or []))
        check("...and the stored notes really did carry the stale claims "
              "(the withhold caught real text)",
              True)  # asserted below against the summaries file
        neb = tp.get("Nebraska") or {}
        check("a team with NO status keeps its scout note",
              "digby_avail_withheld" not in neb)
    import json as _j
    dsum = _j.load(io.open(os.path.join(
        REPO, "data/digby_summaries_2026.json"), encoding="utf-8"))
    txs = ((dsum.get("teams") or {}).get("Texas") or {}).get("summary") or ""
    pus = ((dsum.get("teams") or {}).get("Purdue") or {}).get("summary") or ""
    check("the withheld Texas note contained present-tense 'intact'",
          "intact" in txs)
    check("the withheld Purdue note contained present-tense 'are back'",
          "are back" in pus or "all three" in pus)
    check("the withheld notice helper is fenced on the page",
          "availWithheldNote" in page)

    print("\n  SOURCE-KIND TRUTH + QUIET STALE NOTICE (2026-09-01)")
    check("Kenna's intel chip: PLAYER STATEMENT, and the claim says it "
          "is her own public statement via press report, not a school "
          "release",
          kw.get("source_kind_label") == "PLAYER STATEMENT"
          and "not a school release" in (kw.get("what") or ""))
    check("Grace's intel chip: SCHOOL SOURCE",
          gh.get("source_kind_label") == "SCHOOL SOURCE")
    check("Vander Wal's intel chip: BEAT REPORT, with the individual "
          "supports on her status card",
          vw_c.get("source_kind_label") == "BEAT REPORT"
          and vcard["n_supports"] == 2)
    check("the vocabulary is controlled and shared (desk KIND_LABEL)",
          AD.KIND_LABEL.get("player_statement") == "PLAYER STATEMENT"
          and AD.KIND_LABEL.get("school_site") == "SCHOOL SOURCE"
          and AD.KIND_LABEL.get("beat_report") == "BEAT REPORT")
    check("projection supports carry the same labels (avMeta reads them)",
          all(x.get("kind_label") for x in vcard["supports"])
          and (wcard["supports"][0].get("kind_label")
               == "PLAYER STATEMENT"))
    check("the leading support heads the card, so summaries agree on "
          "the kind",
          vcard["supports"][0].get("claim") == "out_for_season")
    # match-log grammar
    sp = jsfn(page, "showPlayer") or page
    check("match log: labelled stat grammar, no zero-coded line",
          "No player stats recorded" in page
          and "tok.K = g.k + ' K'" in page
          and "0k \u00b7" not in page)
    js_ml = ("const esc=s=>String(s==null?'':s);"
             "const pct=v=>(v==null?'\u2014':(v<0?'-':'')+Math.abs(v)"
             ".toFixed(3).replace(/^0/,''));"
             "function line(g){const blk=g.bs+g.ba*0.5;const parts=[];"
             "if(g.k)parts.push(g.k+' K');if(g.e)parts.push(g.e+' E');"
             "if(g.ta)parts.push(g.ta+' TA');"
             "if(g.ta>=8&&g.hit!==null&&g.hit!==undefined)"
             "parts.push(pct(g.hit)+' HIT');"
             "if(g.ast)parts.push(g.ast+' AST');"
             "if(g.digs)parts.push(g.digs+' D');if(blk)parts.push(blk+' B');"
             "if(g.aces)parts.push(g.aces+' A');"
             "return parts.length?parts.join(' \u00b7 ')"
             ":'No player stats recorded';}"
             "console.log(JSON.stringify({"
             "normal: line({k:14,e:5,ta:36,hit:0.25,ast:0,digs:2,bs:0,"
             "ba:2,aces:1}),"
             "dnp: line({k:0,e:0,ta:0,hit:null,ast:0,digs:0,bs:0,ba:0,"
             "aces:0}),"
             "exit: line({k:2,e:1,ta:5,hit:0.2,ast:0,digs:0,bs:0,ba:0,"
             "aces:0})}));")
    rc, out, err = node(js_ml)
    check("the grammar itself runs", rc == 0, err)
    if rc == 0:
        d3 = json.loads(out.strip().splitlines()[-1])
        check("normal match: readable labelled fixed order",
              d3["normal"] == "14 K \u00b7 5 E \u00b7 36 TA \u00b7 "
              ".250 HIT \u00b7 2 D \u00b7 1 B \u00b7 1 A", d3["normal"])
        check("no player stats -> the exact plain sentence",
              d3["dnp"] == "No player stats recorded")
        check("post-exit partial line: real values only, no zero "
              "padding, no low-TA pseudo-HIT",
              d3["exit"] == "2 K \u00b7 1 E \u00b7 5 TA", d3["exit"])
    # quiet stale notice
    check("the withheld notice is ONE compact line with the exact "
          "wording, promising nothing",
          "Preseason scout note hidden: newer availability evidence "
          "may make its roster wording stale." in page
          and "returns once regenerated" not in page)
    check("...rendered near Sourced intel, not as a full-width module",
          "avstale" in page and "dsr-note" not in
          (jsfn(page, "availWithheldNote") or "x"))
    check("scoutRead renders NOTHING when withheld (no empty module)",
          "if (!t.digby) return '';" in page)
    check("a team with no availability evidence keeps its scout note",
          (json.loads(re.search(r"const TEAMS = (\{.*?\});\n", page,
                                re.S).group(1).replace("<\\/", "</"))
           .get("Nebraska") or {}).get("digby"))

    print("\n  the public page carries none of it")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub_p):
        pub = io.open(pub_p, encoding="utf-8").read()
        for frag in ("unexpected health issue",
                     "leaving the match in Set 2",
                     "match incident", "avCard(", "availWithheldNote",
                     "digby_avail_withheld",
                     "Out for the 2026 season",
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
