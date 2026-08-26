#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the Film Room / voting notebook.

⚠ WHAT IS AT STAKE. This feature stores Cody's own observations about named
athletes, his links, and his takeaways. None of it may reach the published
page, a rating, a projection, the ballot file, Digby's facts, or git. The
notebook itself never leaves the browser; the risk is the CODE, which names
what is recorded and would enumerate a private feature on a public page exactly
as the ballot's selector names once did.

Python 3.9 target. Run: python3 scripts/test_filmroom.py
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    print("FILM ROOM GUARDS\n")
    src = open(os.path.join(SCRIPTS, "build_hub.py"), encoding="utf-8").read()
    priv_p = os.path.join(REPO, "Cody", "START-HERE.html")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    priv = open(priv_p, encoding="utf-8").read() if os.path.exists(priv_p) else ""
    pub = open(pub_p, encoding="utf-8").read() if os.path.exists(pub_p) else ""

    print("1. EVERY LAYER IS FENCED")
    fences = [("<!-- FILMROOM-HTML-BEGIN -->", "<!-- FILMROOM-HTML-END -->"),
              ("/* FILMROOM-JS-BEGIN */", "/* FILMROOM-JS-END */"),
              ("/* FILMROOM-CSS-BEGIN */", "/* FILMROOM-CSS-END */"),
              ("/* FILMROOM-ROUTE-BEGIN */", "/* FILMROOM-ROUTE-END */"),
              ("<!-- FILMROOM-MENU-BEGIN -->", "<!-- FILMROOM-MENU-END -->"),
              ("/* FILMROOM-WIRE-BEGIN */", "/* FILMROOM-WIRE-END */")]
    inside = ""
    for a, b in fences:
        # It appears twice by design: once as the fence, once in the list
        # strip_private() walks. Fewer than two means one of them is missing.
        check("fence %-24s is drawn AND stripped" % a.strip("<!-/* "),
              src.count(a) >= 1 and src.count(b) >= 1
              and (a in src[src.find("def strip_private"):]
                   or a.replace("<!-- ", "").replace(" -->", "")
                   in src[src.find("def strip_private"):]),
              "count %d/%d" % (src.count(a), src.count(b)))
        m = re.search(re.escape(a) + r".*?" + re.escape(b), src, re.S)
        if m:
            inside += m.group(0)
    # ⚠ strip_private() AND THE MARKER LIST LEGITIMATELY NAME EVERY FENCE.
    # That is their job -- they are what removes the feature. Counting those
    # mentions as leaks failed six fence checks and four symbol checks against
    # a build that was behaving correctly. The stripper is excluded before the
    # "only inside a fence" question is asked.
    outside = src
    for a, b in fences:
        outside = re.sub(re.escape(a) + r".*?" + re.escape(b), "", outside,
                         flags=re.S)
    _sp = outside.find("def strip_private")
    if _sp >= 0:
        outside = outside[:_sp] + outside[outside.find("\ndef ", _sp + 10):]
    _pm = outside.find("PRIVATE_MARKERS")
    if _pm >= 0:
        outside = outside[:_pm] + outside[outside.find("]", _pm):]

    # ⚠ NOT ONE FILM-ROOM SYMBOL MAY LIVE OUTSIDE ITS FENCE. This is the check
    # that would have caught the ballot's stylesheet surviving four review
    # passes: the markup was fenced, the rules were not.
    for sym in ("FR_KEY", "wvb.filmroom", "function frLoad", "function frAdd",
                "function frRender", "function frEntry", ".fr-entry{",
                ".fr-chip{", 'id="v-film"', "Film Room"):
        check("[-] %-20s appears ONLY inside a fence" % sym, sym not in outside,
              "found outside")
    check("[+] ...and the fences really contain them", "FR_KEY" in inside)

    print("\n2. THE PUBLIC BUILD HAS NONE OF IT")
    if not pub:
        print("  (no public build -- skipping)")
    else:
        for sym in ("FR_KEY", "wvb.filmroom", "filmroom", "frLoad", "frAdd",
                    "frEntry", "frRender", 'id="v-film"', "Film Room",
                    "FILMROOM", "Pre-match", "During match", "Post-match",
                    "Watched myself", "Community discussion"):
            check("public: no %r" % sym, sym not in pub)
        for sym in ("frExport", "frExportDoc", "wvb.filmroom", "frCopyLegacy",
                    "frDownload", "Download JSON", "Copy JSON",
                    "filmroom-", "FR_FORMAT"):
            check("public: no export symbol %r" % sym, sym not in pub)
        fr_css = re.findall(r"\.fr-[a-z0-9-]*\s*[{,]", pub)
        check("public: not one .fr-* CSS rule", not fr_css,
              "%d found" % len(fr_css))
        check("public: the route is gone", "'film-room'" not in pub
              and "film:'film-room'" not in pub)
        # [+] POSITIVE CONTROL -- the private page really has all of it.
        if priv:
            have = sum(1 for x in ("FR_KEY", 'id="v-film"', ".fr-entry{",
                                   "function frRender")
                       if x in priv)
            check("[+] the PRIVATE page carries every layer", have == 4,
                  "%d of 4" % have)

    print("\n3. NOTES REACH NOTHING THAT COMPUTES")
    # ⚠ THE DATA-FLOW PROOF. No module that produces a number may even mention
    # the notebook -- not its key, not its functions, not its storage.
    for mod in ("rating_2025.py", "digby_top25.py", "project_2026.py",
                "project_field.py", "simulate_season_2026.py",
                "build_rankings_board.py", "ballots.py", "digby.py",
                "digby_chat.py", "snapshot_rankings.py", "weekly.py",
                "fixture_disposition.py", "live_server.py", "live_detail.py"):
        p2 = os.path.join(SCRIPTS, mod)
        if not os.path.exists(p2):
            continue
        body = open(p2, encoding="utf-8").read()
        hit = [t for t in ("filmroom", "FR_KEY", "frLoad", "frAdd", "fr-entry")
               if t in body]
        check("[-] %-26s never touches the notebook" % mod, not hit, str(hit))

    # And inside the page, no ranking/ballot/prediction path may read FR.
    fr_readers = re.findall(r"(function \w+)\([^)]*\)\s*\{[^}]*\bFR\b", src)
    bad = [f for f in fr_readers
           if not re.match(r"function (fr[A-Z]\w*|frLoad|frSave)", f)]
    check("[-] only fr* functions read the notebook", not bad, str(bad[:3]))

    print("\n4. NOTHING IS FETCHED, NOTHING IS POSTED")
    check("a pasted link is stored, never requested",
          "the page is never fetched or copied" in src)
    for bad_call in ("fetch(n.url", "fetch(note.url", "XMLHttpRequest",
                     "navigator.sendBeacon"):
        check("[-] the notebook never calls %r" % bad_call,
              bad_call not in inside)
    check("[-] no third-party host is contacted from the notebook",
          not re.search(r"fetch\(['\"]https?://", inside))

    print("\n5. AN OBSERVATION IS NOT A FACT")
    # ⚠ THE ONE CHECKABLE THING A NOTE MAY CARRY IS A FROZEN CHIP, AND IT
    # CARRIES ITS DATE. A chip that silently re-read the payload would turn a
    # month-old note into a claim about today.
    check("frozen chips exist", "function frFreezeTeam" in src)
    check("...and are stamped when taken", "at: new Date().toISOString()" in src)
    check("...and are labelled as frozen", "Frozen from the hub" in src)
    check("...and the stamp is rendered", "esc(String(f.at" in src)
    # No note ever becomes a reason, a rating or a recommendation.
    fr_js = inside
    for word in ("recommend", "you should", "suggests that", "proves",
                 "therefore rank", "auto-fill", "autofill"):
        check("[-] the notebook never says %r" % word,
              word not in fr_js.lower())

    print("\n5b. EXPORT GOES TO THIS DEVICE AND NOWHERE ELSE")
    ex = inside
    check("export exists", "function frExport(" in ex)
    check("...and is versioned", "FR_FORMAT = 'wvb.filmroom'" in src
          and "FR_VERSION = 1" in src)
    check("...and stamps when it was taken", "exported: new Date()" in ex)

    # ⚠ EVERY NOTE FIELD IS CARRIED. An export that quietly dropped a field is
    # a backup that loses work without saying so.
    m = re.search(r"notes: FR\.map\(n => \((\{.*?\})\)\)", ex, re.S)
    body = m.group(1) if m else ""
    check("[+] the note mapping was found", bool(body))
    for field in ("id", "created", "ctx", "title", "body", "teams", "players",
                  "gid", "src", "url", "facts"):
        check("   export carries %-8s" % field, (field + ":") in body)

    # ⚠ NO NETWORK PATH, AT ALL.
    for bad in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket",
                "form.submit", "action="):
        check("[-] export never uses %r" % bad, bad not in ex)
    check("[-] no host is named anywhere in the notebook",
          not re.search(r"https?://[a-z]", ex))

    print("\n5c. THE DOWNLOAD IS NOT CLAIMED TO HAVE LANDED")
    # ⚠ A PAGE-INITIATED DOWNLOAD CAN BE REFUSED WITH NO ERROR AND NO EVENT.
    # Saying "saved" would be a confident statement about something the
    # browser never told us.
    dl = ex[ex.index("function frDownload("):]
    dl = dl[:dl.index("\nfunction ")]
    check("frDownload reports the ATTEMPT, not the outcome",
          "RETURNS WHETHER THE ATTEMPT WAS MADE" in dl)
    check("the status says 'started', never 'saved'",
          "Download started" in ex and "File saved" not in ex
          and "Saved to your" not in ex)
    check("...and points at the fallback in the same breath",
          "use Copy instead" in ex)

    print("\n5d. BLOCKED ROUTES FAIL HONESTLY")
    check("the clipboard has a legacy fallback", "function frCopyLegacy" in ex)
    check("...and both are wrapped so a denial cannot throw",
          ex.count("catch (e) { return false; }") >= 2)
    check("when both fail the JSON is shown to copy by hand",
          "function frShowRaw" in ex and "select all and copy it" in ex)
    check("...and it is pre-selected", "ta.select();" in ex)
    # ⚠ THE MESSAGE NAMES ONLY WHAT WAS TRIED.
    check("a failed Copy does not claim saving was attempted",
          "mode === 'copy'" in ex
          and "The clipboard is not available in this browser." in ex)
    check("an empty notebook says so rather than exporting nothing",
          "There is nothing to export yet." in ex)

    print("\n6. FAIL-SOFT PRIVACY, THE SAME AS MY BOARD")
    check("storage failure is caught", "FR_OK = false" in src)
    check("...and reported honestly, not as an empty notebook",
          "not letting the page store anything" in src)
    check("...and distinguished from a genuinely empty one",
          "Your notebook is empty" in src)
    check("the key is namespaced like My Board's",
          "'wvb.filmroom.v1'" in src)

    print("\n7. THE PHONE CAN CAPTURE QUICKLY")
    phone = "\n".join(re.findall(r"@media \(max-width:560px\)\{(.*?)\n\}", src,
                                 re.S))
    check("the two-column form collapses", ".fr-row{grid-template-columns:1fr}"
          in phone.replace(" ", ""))
    check("the search field takes the full width", ".fr-bar input[type=search]"
          in phone)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL FILM ROOM GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
