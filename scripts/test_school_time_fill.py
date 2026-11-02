"""Guards for the placeholder fill (Cody, 2026-10-28): when the feed's start
time is only its midnight placeholder, the school's own published time is
shown, marked as the school's. A REAL feed time is never overwritten, Hawaii's
genuine late starts survive, and a school time a day away is refused."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_hub as B

bad = []
def check(label, ok):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL")); ok or bad.append(label)

FEED = 1793343600                        # a 3:00 AM ET placeholder
SCHOOL = FEED - 5 * 3600                 # 10:00 PM ET the evening before
rows = [{"gid": "g1", "feed_epoch": FEED, "school_epoch": SCHOOL},
        {"gid": "far", "feed_epoch": FEED, "school_epoch": FEED + 3 * 86400}]

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "data"))
json.dump({"disagreements": rows},
          open(os.path.join(tmp, "data", "fixture_time_check_%d.json" % B.SEASON), "w"))
B.REPO = tmp
B._SCHOOL_TIME.update(mtime=None, map={})

t = B.listed_time("3:00 AM ET", "UCLA", FEED, "g1")
check("a placeholder takes the school's time", t.startswith("7:00 PM PT"))
check("...and says it is the school's", t.endswith(B.SCHOOL_TIME_MARK))
check("[NEG] no school answer stays TBA",
      B.listed_time("3:00 AM ET", "UCLA", FEED, "nope") == "TBA")
check("[NEG] a school time days away is refused",
      B.listed_time("3:00 AM ET", "UCLA", FEED, "far") == "TBA")
real = B.listed_time("7:00 PM ET", "UCLA", FEED + 16 * 3600, "g1")
check("[NEG] a real feed time is never overwritten",
      not real.endswith(B.SCHOOL_TIME_MARK))
check("Hawaii's genuine 1:00 AM ET start survives",
      not B.listed_time("1:00 AM ET", "Hawaii", FEED, "g1")
      .endswith(B.SCHOOL_TIME_MARK))
check("every listed_time call site passes the game id",
      "listed_time(g.get(\"startTime\"), h, g.get(\"startTimeEpoch\"))"
      not in open(B.__file__).read())

check("a placeholder EPOCH behind a real-looking string is caught",
      B.listed_time("10:00 PM ET", "UCLA", FEED, "g1").endswith(B.SCHOOL_TIME_MARK))
check("the scoreboard's real epoch beats a placeholder canonical one",
      B.best_epoch(FEED, FEED + 19 * 3600, "UCLA") == FEED + 19 * 3600)
check("[NEG] a real canonical epoch is kept",
      B.best_epoch(FEED + 16 * 3600, FEED + 19 * 3600, "UCLA") == FEED + 16 * 3600)

if bad:
    print("FAILED: %d check(s)" % len(bad)); sys.exit(1)
print("ALL SCHOOL-TIME FILL GUARDS PASS")
