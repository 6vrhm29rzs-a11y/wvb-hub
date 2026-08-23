#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the no-scrape hook.

A hook nobody has fired is a comment. Three directions are tested, and all three
are load-bearing:

  1. The blocked domains are blocked.
  2. POSITIVE CONTROL -- ordinary work is untouched. A hook that blocked
     everything would pass (1) and make the repo unusable.
  3. Writing ABOUT a blocked domain is allowed. The first version of the hook
     blocked its own test file, because the file names all five hosts and also
     contains the word "curl". A rule that cannot be documented is not a rule
     anyone can maintain.

Python 3.9 target. Run: python3 scripts/test_no_scrape_hook.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, ".claude/hooks/no_scrape.py")
FAILED = []

# Assembled at runtime so this source file never contains a fetch command and a
# hostname as one literal -- the exact shape the hook is meant to stop.
SB = "stat" + "broadcast.com"
NC = "stats." + "ncaa.org"
VM = "volleyball" + "mag.com"
MR = "massey" + "ratings.com"
BC = "bcs" + "stats.com"


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


def run(tool, payload):
    p = subprocess.Popen([sys.executable, HOOK], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = p.communicate(json.dumps(
        {"tool_name": tool, "tool_input": payload}).encode("utf-8"))
    return p.returncode, err.decode("utf-8")


def test_blocked_domains_are_blocked():
    cases = [
        ("Bash", {"command": "curl -s https://%s/mobile/?id=675834" % SB}),
        ("Bash", {"command": "curl -A 'Mozilla/5.0' https://%s/contests/1/play_by_play" % NC}),
        ("Bash", {"command": "wget https://%s/feed" % VM}),
        ("Bash", {"command": "python3 -c \"import urllib.request as u; u.urlopen('https://%s/cv')\"" % MR}),
        ("WebFetch", {"url": "https://www.%s/getintouch.php" % SB}),
        ("WebFetch", {"url": "https://%s/terms.php" % BC}),
        ("Bash", {"command": "curl https://%s/robots.txt" % NC.upper()}),
        ("Bash", {"command": "echo start && curl -O https://%s/x.csv" % SB}),
    ]
    for tool, payload in cases:
        code, err = run(tool, payload)
        target = (payload.get("url") or payload.get("command"))[:54]
        check(code == 2, "BLOCKED: %s" % target, "exit %d" % code)
        if code == 2:
            check("do not change the user-agent" in err,
                  "  reason forbids routing around it")


def test_ordinary_work_is_untouched():
    """POSITIVE CONTROL. Without this a hook that denied everything would pass."""
    cases = [
        ("Bash", {"command": "python3 scripts/build_hub.py"}),
        ("Bash", {"command": "git status --short"}),
        ("Bash", {"command": "for t in scripts/test_*.py; do python3 $t; done"}),
        ("Bash", {"command": "curl -s https://ncaa-api.henrygd.me/scoreboard/"
                             "volleyball-women/d1/2026/08/23/all-conf"}),
        ("Bash", {"command": "curl -s https://media.githubusercontent.com/media/"
                             "JeffreyRStevens/ncaavolleyballr/refs/heads/main/"
                             "data-csv/wvb_pbp_div1_2025.csv"}),
        ("WebFetch", {"url": "https://jeffreyrstevens.github.io/ncaavolleyballr/"}),
        ("Read", {"file_path": "docs/statbroadcast.md"}),
        ("Write", {"file_path": "docs/x.md", "content": "about %s" % SB}),
    ]
    for tool, payload in cases:
        code, _ = run(tool, payload)
        target = str(payload.get("url") or payload.get("command")
                     or payload.get("file_path"))[:54]
        check(code == 0, "ALLOWED: %s" % target, "exit %d" % code)


def test_writing_about_a_domain_is_not_fetching_it():
    """THE FALSE POSITIVE THAT ACTUALLY HAPPENED. The first version blocked the
    command that created this very file."""
    doc = ("cat > docs/note.md <<'EOF'\n"
           "We do not curl %s -- their terms forbid it.\n"
           "Nor %s, which 403s every non-browser client.\n"
           "EOF" % (SB, NC))
    code, _ = run("Bash", {"command": doc})
    check(code == 0, "a heredoc that NAMES blocked domains is allowed")

    grep = "grep -rn '%s' docs/ && cat docs/statbroadcast.md" % SB
    code2, _ = run("Bash", {"command": grep})
    check(code2 == 0, "grepping our own docs for the name is allowed")

    # ...but a real fetch AFTER a heredoc must still be caught.
    sneaky = doc + "\ncurl -s https://%s/x" % SB
    code3, _ = run("Bash", {"command": sneaky})
    check(code3 == 2, "NEGATIVE CONTROL: a real fetch after a heredoc is caught")


def test_malformed_input_never_breaks_the_session():
    p = subprocess.Popen([sys.executable, HOOK], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.communicate(b"not json at all")
    check(p.returncode == 0, "malformed hook input allows rather than blocks")


def test_the_hook_is_actually_wired():
    cfg = json.load(open(os.path.join(REPO, ".claude/settings.json")))
    hooks = json.dumps(cfg.get("hooks") or {})
    check("no_scrape.py" in hooks, "the hook is registered in .claude/settings.json")
    check("PreToolUse" in hooks, "registered as PreToolUse -- before the call, not after")


def main():
    for fn in (test_blocked_domains_are_blocked,
               test_ordinary_work_is_untouched,
               test_writing_about_a_domain_is_not_fetching_it,
               test_malformed_input_never_breaks_the_session,
               test_the_hook_is_actually_wired):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all no-scrape hook invariants pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
