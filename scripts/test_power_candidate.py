#!/usr/bin/env python3
"""POWER candidate v1 (mail 055): OFF by default, never writes the live file,
equal-set margin and neutral-site rule behave exactly as specified."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
FAIL = []
def check(n, ok, x=""):
    print("  %-70s %s%s" % (n, "ok" if ok else "FAIL", ("  " + x) if x else ""))
    if not ok: FAIL.append(n)
env = dict(os.environ, WVB_SEASON="2026")
env.pop("WVB_POWER_CANDIDATE", None); env.pop("WVB_POWER_NEUTRAL", None)
r = subprocess.run([sys.executable, os.path.join(HERE, "digby_top25.py")], env=dict(env, WVB_POWER_CANDIDATE="1"),
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
check("candidate mode refuses to run without a separate output path", r.returncode != 0 and b"requires WVB_DIGBY_OUT" in r.stdout)
LIVE = os.path.join(REPO, "data", "digby_top25_2026.json")
before = os.path.getmtime(LIVE)
tmpd = tempfile.mkdtemp()
link = os.path.join(tmpd, "alias.json"); os.symlink(LIVE, link)
rel = os.path.relpath(LIVE, os.getcwd())
for label, path, flag in (("explicit live path", LIVE, "WVB_POWER_CANDIDATE"), ("symlink alias", link, "WVB_POWER_CANDIDATE"),
                          ("relative alias", rel, "WVB_POWER_CANDIDATE"), ("neutral-only switch, live path", LIVE, "WVB_POWER_NEUTRAL"),
                          ("equal-set-only switch, live path", LIVE, "WVB_POWER_EQS")):
    rr = subprocess.run([sys.executable, os.path.join(HERE, "digby_top25.py")], env=dict(env, **{flag: "1", "WVB_DIGBY_OUT": path}),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    check("guard rejects the live file via %s" % label, rr.returncode != 0 and b"refuses to write the LIVE" in rr.stdout)
check("...and the live file was not touched", os.path.getmtime(LIVE) == before)
sys.path.insert(0, HERE)
os.environ.pop("WVB_POWER_CANDIDATE", None)
import importlib, digby_top25 as D
ls = [{"home": 25, "visit": 20}, {"home": 20, "visit": 25}, {"home": 25, "visit": 22}, {"home": 23, "visit": 25}, {"home": 15, "visit": 10}]
check("live margin = raw average over sets (hand-computed 1.20)", abs(D._set_margin(ls) - 1.2) < 1e-12, "%.4f" % D._set_margin(ls))
os.environ["WVB_POWER_CANDIDATE"] = "1"; os.environ["WVB_DIGBY_OUT"] = tempfile.mktemp()
D2 = importlib.reload(D)
exp = (5 - 5 + 3 - 2 + 5 * 25.0 / 15.0) / 5.0            # hand-computed: 5th set x25/15
check("candidate margin: 5th set scaled x25/15 (hand-computed 1.8667)", abs(D2._set_margin(ls) - exp) < 1e-12, "%.4f" % D2._set_margin(ls))
check("candidate: four-set match unchanged by equal-set", abs(D2._set_margin(ls[:4]) - 0.25) < 1e-12)
check("candidate turns the neutral-site rule on", D2.NEUTRAL_SITE_CANDIDATE)
os.environ.pop("WVB_POWER_CANDIDATE"); os.environ.pop("WVB_DIGBY_OUT")
D3 = importlib.reload(D2)
check("[NEG] default mode: neutral rule off, raw margin", not D3.NEUTRAL_SITE_CANDIDATE and abs(D3._set_margin(ls) - 1.2) < 1e-12,
      "%s %.4f" % (D3.NEUTRAL_SITE_CANDIDATE, D3._set_margin(ls)))
live = json.load(open(os.path.join(REPO, "data", "digby_top25_2026.json")))
cands = [os.path.join(REPO, "Cody", "data", "power_candidate", "v1_%s.json" % n) for n in ("EQS", "NEU", "BOTH")]
if all(os.path.exists(c) for c in cands):
    check("home advantage held FIXED across candidate variants (%s)" % live["meta"].get("home_advantage_pts_per_set"),
          all(json.load(open(c))["meta"].get("home_advantage_pts_per_set") == live["meta"].get("home_advantage_pts_per_set") for c in cands))
check("live file carries no candidate method stamp", "CANDIDATE" not in str(live["meta"].get("method", "")))
print("FAILED: %s" % FAIL if FAIL else "ALL POWER-CANDIDATE CHECKS HOLD"); sys.exit(1 if FAIL else 0)
