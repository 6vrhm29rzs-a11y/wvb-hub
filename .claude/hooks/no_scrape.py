#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Block fetches to sources this project may not scrape. PreToolUse hook.

WHY A HOOK AND NOT A RULE IN CLAUDE.MD. The no-scrape list is otherwise enforced
by the assistant remembering it. That has worked, but it is the wrong kind of
guarantee for a rule with legal weight: it depends on judgement at the moment of
writing a command, in a long session. A hook is a mechanical invariant -- the
same move every other guard in this repo makes.

THE LIST, AND WHY EACH ONE IS ON IT:
  * statbroadcast.com / bcsstats.com -- terms grant access only "through the
    standard StatBroadcast web interface" for personal use, and expressly
    prohibit collecting or deriving data "whether manually or through automated
    or semi-automated means" without prior written consent. They 403 non-browser
    clients, which is them enforcing it.
  * stats.ncaa.org -- returns 403 to non-browser clients, robots.txt included.
    NOT a licence question: the identical data is published as MIT-licensed CSVs
    by the ncaavolleyballr author, so a permissioned route already exists.
  * volleyballmag.com -- Cloudflare 403 on every page; getting past it would
    mean forging a browser fingerprint.
  * masseyratings.com -- third-party ratings we hold no licence to republish.

WHAT IT DELIBERATELY DOES NOT BLOCK. Writing about these domains. The first
version blocked its own test file, because the file's text contains both a
hostname and the word "curl" -- a false positive that would make documenting the
rule impossible. Heredoc bodies and quoted file content are stripped before
scanning, so `cat > doc.md <<EOF ... EOF` is prose, not a request.

This guards the routine path, not every conceivable one -- a determined
rephrasing gets through, and that is fine. It is a guard against forgetting, and
forgetting is the actual failure mode.

Exit 2 = block, with the reason shown to the model. Anything else = allow.
"""

import json
import re
import sys

BLOCKED = {
    "statbroadcast.com": "terms permit only human browsing of their own web interface",
    "bcsstats.com": "same operator and terms as StatBroadcast",
    "stats.ncaa.org": "blocks non-browser clients; the same data is published as "
                      "MIT-licensed CSVs by ncaavolleyballr",
    "volleyballmag.com": "Cloudflare-blocked; getting past it means forging a browser",
    "masseyratings.com": "third-party ratings we hold no licence to republish",
    "figstats.net": ("robots.txt disallows every non-named agent "
                     "('User-agent: * / Disallow: /', measured 2026-08-31); "
                     "snapshots are manual browser reviews only"),
}

# The command has to actually be a fetch. Matching a bare hostname is not
# enough -- this file mentions all five and must not block itself.
# re.M matters: without it "^" anchors only to the START OF THE COMMAND, so a
# fetch on any later line is invisible. Found by the negative control -- a real
# curl placed after a heredoc sailed through the first version.
FETCHY = re.compile(
    r"(?:^|[|;&\n]|\$\(|`)\s*(?:sudo\s+)?(curl|wget|httpie|http|xh|aria2c|lynx|w3m)\b"
    r"|urlopen|requests\.get|urlretrieve|httpx\.|aiohttp",
    re.I | re.M)

# Heredoc bodies are CONTENT, not a request. `cat > x.md <<'EOF' ... EOF`
# writes prose that may name any of these domains.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\2$",
                     re.S | re.M)


def strip_content(cmd):
    """Remove heredoc bodies so writing about a domain is not fetching it."""
    return HEREDOC.sub(" <<HEREDOC_BODY_STRIPPED> ", cmd or "")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:                                   # noqa: BLE001
        return 0                                        # never break the session

    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}

    if tool == "WebFetch":
        haystack = str(ti.get("url") or "")
    elif tool == "Bash":
        haystack = strip_content(str(ti.get("command") or ""))
        if not FETCHY.search(haystack):
            return 0                                    # not a network command
    else:
        return 0

    low = haystack.lower()
    for host, why in sorted(BLOCKED.items()):
        if host in low:
            sys.stderr.write(
                "BLOCKED by .claude/hooks/no_scrape.py: %s must not be fetched "
                "programmatically -- %s.\n"
                "This is a standing project rule, not a transient error. Do not "
                "retry, do not change the user-agent, and do not route around "
                "it. If the data is genuinely needed, ask Cody; the permissioned "
                "alternatives are recorded in docs/statbroadcast.md and "
                "CLAUDE.md.\n" % (host, why))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
