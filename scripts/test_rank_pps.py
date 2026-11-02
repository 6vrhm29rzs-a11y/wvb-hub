"""Box-score rates beside POWER on the Rankings tab (Cody, 2026-10-28):
PPS, opponent PPS, PPS spread, Hit%, opponent Hit%, Hit spread -- in that
order, directly after Power. Every value is checked BY VALUE against the
team page's own team_season_stats() row; a team without box scores shows a
dash, never a number."""
import json, os, re, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = []
def check(label, ok, extra=""):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL %s" % (extra,))); ok or bad.append(label)

page = os.path.join(REPO, "Cody", "START-HERE.html")
if not os.path.exists(page):
    print("  --   no private page in this checkout; skipping"); sys.exit(0)
h = open(page, encoding="utf-8").read()
ORDER = ["c-pow", "c-pps", "c-opps", "c-dpps", "c-hit", "c-ohit", "c-dhit"]
ths = re.findall(r'<th class="n (c-[a-z]+)"', h)
i = ths.index("c-pow") if "c-pow" in ths else -1
check("headers run Power, PPS, Opp, ±, Hit%, Opp, ±", ths[i:i + 7] == ORDER, ths[i:i + 7])

CLS = ["pps", "opps", "dpps", "hitp", "ohit", "dhit"]
cell = r'<td class="n %s"[^>]*>((?:<span[^>]*>[^<]*</span>)|[^<]*)</td>'
pat = re.compile(r'data-team="([^"]+)" tabindex.*?' + "".join(cell % c for c in CLS))
rows = pat.findall(h)
check("every ranked row carries all six cells, in order", len(rows) >= 340, len(rows))

def num(v):
    v = v.replace("&minus;", "-").replace("+", "")
    try:
        return float(v)
    except ValueError:
        return None

m = re.search(r'const TEAMS = (\{.*?\});\n', h)
T = json.loads(m.group(1)) if m else {}
checked = 0
for r in rows:
    t, vals = __import__("html").unescape(r[0]), [num(x) for x in r[1:]]
    st = (T.get(t) or {}).get("tstats") or {}
    own, opp = st.get("own") or {}, st.get("opp") or {}
    exp = [own.get("pps"), opp.get("pps"),
           None if own.get("pps") is None or opp.get("pps") is None else own["pps"] - opp["pps"],
           own.get("hit"), opp.get("hit"),
           None if own.get("hit") is None or opp.get("hit") is None else own["hit"] - opp["hit"]]
    tol = [0.006, 0.006, 0.011, 0.0006, 0.0006, 0.0011]
    for k, (a, b, tl) in enumerate(zip(vals, exp, tol)):
        if b is None:
            if a is not None:
                check("%s %s: a number where the team page has none" % (t, CLS[k]), False, a); break
        elif a is None or abs(a - b) > tl:
            check("%s %s matches the team page" % (t, CLS[k]), False, (a, b)); break
    else:
        checked += 1
check("all six values match the team page, by value", checked == len(rows), "%d of %d" % (checked, len(rows)))
check("[+] the comparison saw real numbers", sum(1 for r in rows if num(r[1]) is not None) >= 300)
hv = [num(r[4]) for r in rows if num(r[4]) is not None]
check("Hit% values are fractions between -1 and 1", hv and all(-1 <= x <= 1 for x in hv))
# ── SORTABLE (2026-10-28) ──────────────────────────────────────────────
check("every Rankings header is wired to the sort",
      "document.querySelectorAll('.rk3 thead tr:last-child th').forEach((th, i)" in h
      and "th.addEventListener('click', flip)" in h)
check("a phone-reachable Sort control exists (headers are hidden there)",
      "sel.id = 'rksort'" in h)
check("a team with no value always sorts last, in both directions",
      "if (x === null) return 1;" in h and "if (y === null) return -1;" in h)
check("Top N follows the active sort", "RK_POS.get(tr)" in h)
check("ranks and opponent figures read low-first",
      "new Set(['rk', 'c-opps', 'c-ohit', 'c-res', 'c-avca'])" in h)
check("[NEG] the sort never reads a cell by a stale index past the row",
      "const td = tr.children[col];\n  if (!td) return null;" in h)
if bad:
    print("FAILED: %d check(s)" % len(bad)); sys.exit(1)
print("ALL RANKINGS-RATES GUARDS PASS")
