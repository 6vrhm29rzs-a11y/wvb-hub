#!/usr/bin/env python3
"""Private POWER v2 preview (mail 058): private-only, parity with the frozen
file, no downstream consumer, and rollback = file absent -> nothing emitted."""
import glob, json, os, re, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
ok = True
def check(c, msg):
    global ok
    print(("PASS " if c else "FAIL ") + msg); ok = ok and bool(c)
src = open(os.path.join(REPO, "scripts", "build_hub.py")).read()
check('"" if PUBLIC or not v2_preview_payload() else V2P_BTN' in src, "button emitted only on a private build with a frozen file")
check('"" if PUBLIC or not v2_preview_payload() else' in src.split('"{{V2P_JS}}"')[1][:80], "script emitted only on a private build")
check('"POWER v2 &mdash; preview"' in src and '"const V2P ="' in src, "public gate carries the preview markers (build aborts on leak)")
readers = [p for p in glob.glob(os.path.join(REPO, "scripts", "*.py"))
           if "v2_preview" in open(p, errors="ignore").read()
           and os.path.basename(p) not in ("build_hub.py", "test_v2_preview.py")]
check(not readers, "no other script reads the preview file %s" % readers)
shared = src.split("const RULER_VIEWS = {};")[0][-3000:] + src.split("function renderPoll(which) {")[1][:6000]
check("v2p" not in shared and "V2P" not in shared, "shared ruler code names no preview view")
# rollback: file absent -> payload None
import build_hub as B
B._V2P_CACHE[:] = []
real = B.load
B.load = lambda rel: None if "v2_preview" in rel else real(rel)
check(B.v2_preview_payload() is None, "file absent -> preview payload None (placeholders render empty)")
B.load = real; B._V2P_CACHE[:] = []
fz = os.path.join(REPO, "Cody", "data", "power_candidate", "v2_preview.json")
page = os.path.join(REPO, "Cody", "START-HERE.html")
if os.path.exists(fz) and os.path.exists(page):
    html = open(page, encoding="utf-8").read()
    m = re.search(r"const V2P = (\{.*?\});\n", html)
    check(m, "private page carries the preview payload")
    if m:
        emb, frozen = json.loads(m.group(1)), json.load(open(fz))
        check(emb["teams"] == frozen["teams"] and emb["version"] == frozen["version"],
              "embedded ranks/values identical to the frozen file (%s)" % frozen["version"])
        check(len(emb["teams"]) + len(emb["unrated"]) == 348, "every D-I team rated or explicitly unrated")
        cur = json.load(open(os.path.join(REPO, "data", "digby_top25_2026.json")))
        check(emb["current"]["rank"] == dict((r["team"], r["rank"]) for r in cur["all"]),
              "current column = current POWER ranks, unchanged")
    for p in ("data/digby_top25_2026.json", "output/vb_dashboard.html"):
        t = open(os.path.join(REPO, p), encoding="utf-8", errors="ignore").read()
        check("v2-preview" not in t and "const V2P" not in t, "%s carries no preview value" % p)
else:
    print("SKIP page checks: private page or frozen file absent (CI / rollback)")
print("ALL V2 PREVIEW CHECKS HOLD" if ok else "V2 PREVIEW CHECKS FAILED"); sys.exit(0 if ok else 1)
