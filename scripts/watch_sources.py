#!/usr/bin/env python3
"""Daily check of the sources that can change how this build behaves.

  python3 scripts/watch_sources.py            check all, record changes
  python3 scripts/watch_sources.py --list     print what is watched

Cody 2026-09-26: "texts and links to things we should be tracking for,
recording, analyzing, and adapting at all time ... so that we're always
using up-to-date information". The list is ops/watch/watchlist.json (tracked,
no secrets). State and findings are PRIVATE, in Cody/watch/:
  state.json      last-seen items per source
  changes.jsonl   append-only log of every detected change
  CHANGES.md      newest-first readable summary, with each source's why/on_change
A source that fails to fetch is recorded as a failure, never as "no change".
Read-only against the internet (GET only); no source is on the no-scrape list.
Python 3.9 target.
"""
import datetime
import hashlib
import io
import json
import os
import re
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = os.path.join(REPO, "ops", "watch", "watchlist.json")
DIR = os.path.join(REPO, "Cody", "watch")
STATE = os.path.join(DIR, "state.json")
LOG = os.path.join(DIR, "changes.jsonl")
MD = os.path.join(DIR, "CHANGES.md")
UA = {"User-Agent": "wvb-hub/0.1 (personal project watch)"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def items_apple(src):
    d = json.loads(get(src["fetch"]))
    out = []
    for sec in d.get("topicSections") or []:
        for ident in sec.get("identifiers") or []:
            r = (d.get("references") or {}).get(ident) or {}
            if r.get("title"):
                out.append({"title": r["title"],
                            "link": "https://developer.apple.com" + (r.get("url") or "")})
    return out


def items_endoflife(src):
    out = []
    for c in json.loads(get(src["fetch"]))[:6]:
        out.append({"title": "Python %s: latest %s, EOL %s" % (c.get("cycle"), c.get("latest"), c.get("eol")),
                    "link": src["url"]})
    return out


def _gh(path):
    """GitHub's public REST API over plain HTTPS (unauthenticated: 60/hour is
    far above the handful of calls a day). The gh CLI segfaulted (exit -11)
    inside this process on 2026-09-26, so it is not used here."""
    return json.loads(get("https://api.github.com/" + path))


def items_gh_releases(src):
    return [{"title": "%s (%s)" % (x.get("name") or x.get("tag_name"), (x.get("published_at") or "")[:10]),
             "link": x.get("html_url")} for x in _gh("repos/%s/releases?per_page=5" % src["fetch"])]


def items_gh_commits(src):
    return [{"title": "%s: %s" % ((x.get("commit", {}).get("author", {}).get("date") or "")[:10],
                                  (x.get("commit", {}).get("message") or "").splitlines()[0][:120]),
             "link": x.get("html_url")} for x in _gh("repos/%s/commits?per_page=5" % src["fetch"])]


def items_rss(src):
    xml = get(src["fetch"])
    out = []
    for block in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", xml, re.S)[:30]:
        t = re.search(r"<title[^>]*>(.*?)</title>", block, re.S)
        l = re.search(r"<link[^>]*?href=\"([^\"]+)\"", block) or re.search(r"<link>(.*?)</link>", block, re.S)
        title = re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", t.group(1) if t else "").strip()
        if not title:
            continue
        flt = src.get("filter")
        if flt and not any(f in (title + block[:2000]).lower() for f in flt):
            continue
        out.append({"title": title[:160], "link": (l.group(1).strip() if l else src["url"])})
    return out


def items_html_hash(src):
    html = get(src["fetch"])
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    ver = re.search(r"Version:\s*([0-9][0-9.\-]*)", text)
    pub = re.search(r"Published:\s*([0-9\-]+)", text)
    return [{"title": "version %s, published %s (page hash %s)" % (
        ver.group(1) if ver else "?", pub.group(1) if pub else "?",
        hashlib.sha256(text.encode()).hexdigest()[:10]), "link": src["url"]}]


KINDS = {"apple_docs": items_apple, "endoflife": items_endoflife, "gh_releases": items_gh_releases,
         "gh_commits": items_gh_commits, "rss": items_rss, "html_hash": items_html_hash}


def main():
    sources = json.load(open(LIST))["sources"]
    if "--list" in sys.argv:
        for s in sources:
            print("%-22s %s\n    why: %s" % (s["id"], s["url"], s["why"]))
        return 0
    os.makedirs(DIR, exist_ok=True)
    try:
        state = json.load(open(STATE))
    except (IOError, ValueError):
        state = {}
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    found, failures = [], []
    for s in sources:
        items, err = None, None
        for _attempt in (1, 2):                     # one retry: transient network blips
            try:
                items = KINDS[s["kind"]](s)
                break
            except Exception as e:                        # noqa: BLE001
                err = "%s: %s" % (type(e).__name__, str(e)[:180])
        if items is None:
            failures.append({"id": s["id"], "error": err})
            continue
        seen = set((state.get(s["id"]) or {}).get("titles") or [])
        first = s["id"] not in state
        new = [x for x in items if x["title"] not in seen]
        state[s["id"]] = {"titles": sorted(seen | set(x["title"] for x in items)), "checked_utc": now}
        if new and not first:
            for x in new:
                found.append({"at": now, "source": s["id"], "name": s["name"], "title": x["title"],
                              "link": x["link"], "why": s["why"], "on_change": s["on_change"]})
        elif first:
            found.append({"at": now, "source": s["id"], "name": s["name"], "title": "(baseline recorded: %d items)" % len(items),
                          "link": s["url"], "why": s["why"], "on_change": s["on_change"], "baseline": True})
    with io.open(LOG, "a", encoding="utf-8") as f:
        for x in found:
            f.write(json.dumps(x) + "\n")
        for x in failures:
            f.write(json.dumps(dict(x, at=now, failure=True)) + "\n")
    json.dump(state, open(STATE, "w"), indent=1)
    # readable summary, newest first
    rows = [json.loads(l) for l in io.open(LOG, encoding="utf-8") if l.strip()]
    lines = ["# Watched sources: what changed", "",
             "Checked daily. Newest first. Each change says why it matters to this build and what to do.",
             "Source list: `ops/watch/watchlist.json`. Last check: %s UTC." % now, ""]
    fails_now = [r for r in rows if r.get("failure") and r["at"] == now]
    if fails_now:
        lines.append("**Could not check this run:** " + ", ".join("%s (%s)" % (r["id"], r["error"][:60]) for r in fails_now))
        lines.append("")
    for r in reversed([r for r in rows if not r.get("failure")][-200:]):
        tag = " _(baseline)_" if r.get("baseline") else ""
        lines.append("- **%s** · %s · [%s](%s)%s  \n  Why: %s  \n  Do: %s"
                     % (r["at"][:10], r["name"], r["title"], r["link"], tag, r["why"], r["on_change"]))
    io.open(MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    real = [x for x in found if not x.get("baseline")]
    print("watch: %d sources checked, %d new items, %d baselines, %d failures"
          % (len(sources) - len(failures), len(real), len(found) - len(real), len(failures)))
    for x in real[:20]:
        print("  NEW %s: %s" % (x["source"], x["title"]))
    for x in failures:
        print("  FAILED %s: %s" % (x["id"], x["error"][:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
