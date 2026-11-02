"""Guards for the availability desk's OUT LATELY list (2026-10-28).

A regular whose team's latest judgeable matches show no action is listed;
a serve-only specialist is NOT absent; a truncated team box (<6 players with
an action) is never judged; negative controls prove each guard can trip."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import availability_desk as A

bad = []
def check(label, ok):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL")); ok or bad.append(label)

def row(first, last, gp=3, **k):
    r = {"first": first, "last": last, "team_id": "1", "gp": gp}
    r.update(k); return r

def team_box(extra):
    base = [row("P", "Lay%d" % i, kills=2, atts=5) for i in range(6)]
    return A.participation(base + extra)

# serve-only = appeared (the Vivian Campbell shape)
f = A.participation([row("Viv", "Server", serve_atts=7)])[0]
check("a serve-only line counts as an appearance", f["state"] == "appeared")
f = A.participation([row("Ann", "Passer", recv_atts=12)])[0]
check("a receive-only line counts as an appearance", f["state"] == "appeared")
f = A.participation([row("Zed", "Bench")])[0]
check("[NEG] gp with no action stays zero_action", f["state"] == "zero_action")

def scenario(last_two_listed=True, truncate=False):
    games, date_of = {}, {}
    for i in range(8):
        gid = "g%d" % i; date_of[gid] = 1000 + i
        star = [row("Sam", "Star", kills=9, atts=20)] if i < 6 else (
            [row("Sam", "Star")] if last_two_listed else [])
        if truncate and i >= 6:
            games[gid] = A.participation([row("P", "Lay0", kills=1, atts=2)] + star)
        else:
            games[gid] = team_box(star)
    return A.out_lately({"T": games}, date_of)

r = scenario()
check("a regular missing the last 2 is listed", r.get("T") and r["T"][0]["streak"] == 2)
check("...with each miss's box state",
      r and [m["state"] for m in r["T"][0]["missed"]] == ["zero_action"] * 2)
r = scenario(last_two_listed=False)
check("not-in-box misses are recorded as not_listed",
      r and [m["state"] for m in r["T"][0]["missed"]] == ["not_listed"] * 2)
r = scenario(truncate=True)
check("[NEG] truncated boxes are never judged", not r)
# the bench player (never a regular) is never listed
check("only regulars are listed",
      all(x["player"] == "Sam Star" for x in scenario()["T"]))

if bad:
    print("FAILED: %d check(s)" % len(bad)); sys.exit(1)
print("ALL OUT-LATELY GUARDS PASS")
