#!/usr/bin/env python3
"""Result-truth renderers that survive the 2026-11-04 cleanup -- run, not read.

test_provenance_truth.py was retired with the Availability desk (it extracted
availability functions first and could no longer run). Its result-truth half
still guards KEPT pages, so it is carried forward here and extended to every
result/time claim still visible after the cleanup. Each renderer is EXECUTED
under node on stub data and on the real payload, and each carries a negative
control: a renderer with its branch removed must fail the same invariant.

  A. provenanceTag  -- CORRECTED badge vs ordinary "official scoreboard"
  B. tdLatestFinal  -- team page latest-final chip: corrected / under review /
                       cross-source confirmed / plain
  C. rvMark         -- Scores ledger verification marks (two schools, one
                       school, held, sources disagree, unverified = nothing)
  D. tdisNote       -- disputed start time on Scores rows and team fixtures
  E. the slim CONFIDENCE payload keeps everything A-C read

Python 3.9. Run: python3 scripts/test_corrected_badge.py
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
FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:200]))
    if not ok:
        FAILS.append(label)


def jsfn(src, name):
    """`function name(...) {...}`, comment- and string-aware (the non-greedy
    regex extractor truncated at inner functions, 2026-08-27)."""
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


def last_json(out):
    return json.loads(out.strip().splitlines()[-1])


STUB = {"finals": [
    {"gid": "111", "result_corrected": True, "overall": "corrected",
     "corr_evidence": [{"school": "SMU"}, {"school": "UC Davis"}]},
    {"gid": "222", "overall": "reconciled"},
    {"gid": "333", "overall": "confirmed"},
    {"gid": "444", "overall": "disputed"},
    {"gid": "501", "verify": {"v": "VERIFIED_BOTH"}},
    {"gid": "502", "verify": {"v": "CORROBORATED_ONE"}},
    {"gid": "503", "verify": {"v": "SCHOOL_CONFLICT"}},
    {"gid": "504", "verify": {"v": "UNVERIFIED"}},
    {"gid": "505", "verify": {"v": "HELD_ONE_REPORTS"}}]}


def main():
    import build_hub as B
    import pageconst as PC

    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(page_p):
        page_p = os.path.join(REPO, "output", "vb_dashboard.html")
    page = io.open(page_p, encoding="utf-8").read() if os.path.exists(page_p) else ""
    check("a built page is available", bool(page))
    if not page:
        return finish()

    fns = {}
    for name in ("esc", "corrSchools", "provenanceTag", "tdLatestFinal",
                 "rvMark", "rvWording", "tdisNote"):
        fns[name] = jsfn(page, name)
        check("page function %s present" % name, bool(fns[name]))
    if not all(fns.values()):
        return finish()
    base = fns["esc"] + "\n" + fns["corrSchools"] + "\n"
    stub_js = "const CONFIDENCE = %s;\n" % json.dumps(STUB)
    conf = PC.find(page, "CONFIDENCE") or {}

    print("\nA. CORRECTED-RESULT BADGE (provenanceTag)")
    rc, out, err = node(base + fns["provenanceTag"] + "\n" + stub_js +
                        "console.log(JSON.stringify({c: provenanceTag('111'),"
                        " n: provenanceTag('222')}));")
    check("provenanceTag runs under node", rc == 0, err)
    if rc == 0:
        d = last_json(out)
        check("a corrected final CANNOT render bare 'official scoreboard'",
              "official scoreboard" not in d["c"].lower(), d["c"])
        check("...it names the evidencing schools",
              "CORRECTED · SMU + UC Davis official evidence" in d["c"], d["c"])
        check("...and no longer points at the retired Result Ledger",
              "Result Ledger" not in d["c"], d["c"])
        check("an ordinary final KEEPS the generic tag",
              d["n"] == '<i class="rcsrctag">official scoreboard</i>', d["n"])
    rc, out, err = node(base + fns["provenanceTag"] + "\n" +
                        "const CONFIDENCE = %s;\n" % json.dumps(conf) +
                        "console.log(provenanceTag('6626259'));")
    check("SMU-UC Davis renders CORRECTED on the REAL slim payload",
          rc == 0 and "CORRECTED · SMU + UC Davis official evidence" in out,
          out or err)
    broken = fns["provenanceTag"].replace("r.result_corrected",
                                          "false && r.result_corrected")
    rc, out, err = node(base + broken + "\n" + stub_js +
                        "console.log(provenanceTag('111'));")
    check("[NEG] provenanceTag without its corrected branch is caught",
          broken != fns["provenanceTag"] and rc == 0
          and "CORRECTED" not in out)

    print("\nB. TEAM PAGE LATEST-FINAL CHIP (tdLatestFinal)")

    def chip(fn_src, gid):
        js = (base + "function logo(){return ''}\n" + stub_js + fn_src + "\n" +
              "const t={played:[{gid:'%s',mine:3,theirs:2,opp:'X',home:1,"
              "sets:[[27,25],[20,25],[25,22],[25,23]]}]};\n"
              "console.log(JSON.stringify(tdLatestFinal(t,'A')));" % gid)
        rc, out, err = node(js)
        return (last_json(out) if rc == 0 else None), err

    c, err = chip(fns["tdLatestFinal"], "111")
    check("tdLatestFinal runs under node", c is not None, err)
    if c is not None:
        check("a corrected latest final wears the CORRECTED chip",
              "CORRECTED · SMU + UC Davis official evidence" in c, c)
        check("...and its score is shown mine-first, as delivered",
              "W 3–2" in c and "27–25" in c, c)
        u, _ = chip(fns["tdLatestFinal"], "444")
        check("a disputed latest final says 'Result under review'",
              u and "Result under review" in u and "CORRECTED" not in u, u)
        k, _ = chip(fns["tdLatestFinal"], "333")
        check("a confirmed final says 'Cross-source confirmed'",
              k and "Cross-source" in k and "CORRECTED" not in k, k)
        p, _ = chip(fns["tdLatestFinal"], "222")
        check("an ordinary final carries no confidence chip",
              p and "rcstate" not in p, p)
    broken = fns["tdLatestFinal"].replace("r.overall === 'disputed'",
                                          "false")
    u2, _ = chip(broken, "444")
    check("[NEG] a chip renderer that drops the disputed branch is caught",
          broken != fns["tdLatestFinal"] and u2 is not None
          and "Result under review" not in u2)

    print("\nC. SCORES VERIFICATION MARKS (rvMark)")
    rv = base + fns["rvWording"] + "\nlet RVQ = null;\n" + fns["rvMark"] + "\n"
    rc, out, err = node(rv + stub_js + "console.log(JSON.stringify("
                        "['501','502','503','504','505','999'].map(rvMark)));")
    check("rvMark runs under node", rc == 0, err)
    if rc == 0:
        m = last_json(out)
        check("two schools -> ✓✓", ">✓✓</span>" in m[0], m[0])
        check("one school -> ✓", ">✓</span>" in m[1], m[1])
        check("a school conflict -> ⚠ sources disagree",
              "sources disagree" in m[2] and "bad" in m[2], m[2])
        check("UNVERIFIED and unknown render NOTHING", m[3] == "" and m[5] == "",
              (m[3], m[5]))
        check("a held match says held, never 'disagree'",
              ">held<" in m[4] and "disagree" not in m[4], m[4])
        check("no mark points at the retired Result Ledger",
              all("Result Ledger" not in x for x in m))
    broken = fns["rvMark"].replace("v === 'UNVERIFIED'", "false")
    rc, out, err = node(base + fns["rvWording"] + "\nlet RVQ = null;\n" +
                        broken + "\n" + stub_js +
                        "console.log(JSON.stringify(rvMark('504')));")
    check("[NEG] rvMark that stops suppressing UNVERIFIED is caught",
          broken != fns["rvMark"] and rc == 0 and last_json(out) != "")
    check("the Scores rows still call rvMark on finals",
          "rvMark(m.gid)" in page and "st === 'final'" in page)

    print("\nD. DISPUTED START TIME (tdisNote)")
    td = {"school_asked": "Wisconsin", "school_epoch": 1793926800,
          "minutes_apart": 60}
    rc, out, err = node(fns["esc"] + "\n" + fns["tdisNote"] + "\n" +
                        "console.log(JSON.stringify([tdisNote({tdis:%s}),"
                        "tdisNote({tdis:null}), tdisNote(null)]));" % json.dumps(td))
    check("tdisNote runs under node", rc == 0, err)
    if rc == 0:
        t = last_json(out)
        check("a disputed time renders the school's time, labelled",
              'class="tdisq"' in t[0] and "Wisconsin lists" in t[0]
              and "60 minutes later" in t[0], t[0])
        check("no dispute renders nothing", t[1] == "" and t[2] == "", t[1:])
    broken = fns["tdisNote"].replace("if (!d || !d.school_epoch) return '';",
                                     "return '';")
    rc, out, err = node(fns["esc"] + "\n" + broken + "\n" +
                        "console.log(JSON.stringify(tdisNote({tdis:%s})));"
                        % json.dumps(td))
    check("[NEG] a tdisNote that drops the flag is caught",
          broken != fns["tdisNote"] and rc == 0 and last_json(out) == "")
    check("Scores rows render it on upcoming matches",
          "(st === 'upcoming' ? tdisNote(m) : '')" in page)
    check("team fixture lists render it", "tdisNote(f))" in page)

    print("\nE. THE SLIM PAYLOAD KEEPS WHAT A-C READ")
    art = os.path.join(REPO, "data", "result_confidence_2026.json")
    doc = json.load(open(art)) if os.path.exists(art) else {"finals": []}
    slim = B._confidence_slim(doc)
    full = doc.get("finals") or []
    n_corr = sum(1 for r in full if r.get("result_corrected"))
    n_disp = sum(1 for r in full if r.get("overall") == "disputed")
    check("every corrected final survives (%d)" % n_corr,
          sum(1 for r in slim["finals"] if r.get("result_corrected")) == n_corr)
    check("every disputed final survives (%d)" % n_disp,
          sum(1 for r in slim["finals"] if r.get("overall") == "disputed") == n_disp)
    check("every correcting school survives",
          sum(len(r.get("corr_evidence") or []) for r in slim["finals"]) ==
          sum(len([e for e in r.get("corr_evidence") or [] if e.get("school")])
              for r in full if r.get("result_corrected") or r.get("overall") == "disputed"))
    n_ver = sum(1 for r in full if (r.get("verify") or {}).get("v"))
    check("every verifier verdict survives (%d)" % n_ver,
          sum(1 for r in slim["finals"] if r.get("verify")) == n_ver)
    check("the page ships the slim payload, not the artifact",
          isinstance(conf, dict) and len(conf.get("finals") or []) == len(full)
          and not any("states" in r for r in conf.get("finals") or []))
    return finish()


def finish():
    if FAILS:
        print("\nFAILED: %d" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        sys.exit(1)
    print("\nALL RESULT-TRUTH CHECKS PASSED")


if __name__ == "__main__":
    main()
