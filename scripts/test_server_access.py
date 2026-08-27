#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for who may reach the hub's private endpoints.

⚠ TWO LOCKS, AND NEITHER IS LOOSENED HERE.
  1. The process binds to 127.0.0.1. Nothing on a network can reach it. A
     reverse proxy in front of localhost is the only route a phone ever has.
  2. The Host header is checked, because the bind cannot see a DNS-rebinding
     page: the browser resolves a name the attacker controls to 127.0.0.1 and
     fetches these endpoints as same-origin. The attacker's own name arrives in
     Host, which is what makes that visible.

⚠ WHAT THIS PHASE FOUND. The check was a hardcoded tuple of four localhost
forms, and TWO endpoints never called it at all -- GET /api/ballot, which
returns saved ballot history, and GET /api/live. It is now an exact-match
allowlist, empty by default, applied to all six.

Python 3.9 target. Run: python3 scripts/test_server_access.py
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


class FakeHeaders(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def handler_with(host, trusted=""):
    """The real _is_trusted, against a synthetic request. No socket, no bind."""
    import importlib
    os.environ["WVB_TRUSTED_HOSTS"] = trusted
    import live_server
    importlib.reload(live_server)
    h = live_server.Handler.__new__(live_server.Handler)
    h.headers = FakeHeaders({"Host": host} if host is not None else {})
    return h


def main():
    print("SERVER ACCESS CONTROL\n")
    src = open(os.path.join(REPO, "scripts", "live_server.py"),
               encoding="utf-8").read()

    # ── 1. THE BIND IS UNCHANGED ────────────────────────────────────────
    print("1. THE FIRST LOCK: THE BIND")
    check("the server binds to 127.0.0.1",
          'ThreadingHTTPServer(("127.0.0.1", port), Handler)' in src)
    # ⚠ THE ONE LINE THAT WOULD UNDO EVERYTHING ELSE.
    check("[-] it never binds to a routable address",
          '"0.0.0.0"' not in src and '"::"' not in src,
          "binding wide makes every guard below cosmetic")

    # ── 2. EVERY ENDPOINT IS GUARDED ────────────────────────────────────
    print("\n2. EVERY PRIVATE ENDPOINT CHECKS THE HOST")
    for meth in ("do_GET", "do_POST"):
        blk = src[src.index("def %s" % meth):]
        m = re.search(r"\n    def (?!%s)" % meth, blk)
        blk = blk[:m.start()] if m else blk[:6000]
        for mm in re.finditer(r'== "(/api/[a-z]+)":', blk):
            ep = mm.group(1)
            nxt = blk.find('== "/api/', mm.end())
            body = blk[mm.end(): nxt if nxt > 0 else mm.end() + 800]
            guarded = "_is_trusted()" in body or "_is_local()" in body \
                or "_save_ballot()" in body
            check("  %-5s %-13s is guarded" % (meth[3:], ep), guarded)
    sb = src[src.index("def _save_ballot"):][:1000]
    check("  POST  /api/ballot  is guarded inside _save_ballot",
          "_is_trusted()" in sb or "_is_local()" in sb)

    # ── 3. THE ALLOWLIST ────────────────────────────────────────────────
    print("\n3. WHO IS TRUSTED")
    for host in ("127.0.0.1", "localhost", "::1"):
        check("localhost form %-12s is trusted" % host,
              handler_with(host)._is_trusted())
    # ⚠ EMPTY BY DEFAULT: out of the box nothing new is trusted.
    check("[-] a tailnet host is NOT trusted by default",
          not handler_with("mac.tailnet-1234.ts.net")._is_trusted(),
          "the allowlist must start empty")
    TS = "mac.tailnet-1234.ts.net"
    check("[+] ...and IS trusted once configured",
          handler_with(TS, TS)._is_trusted())
    check("[+] ...case-insensitively, as hostnames are",
          handler_with(TS.upper(), TS)._is_trusted())
    check("[+] ...and with a port, which Host may carry",
          handler_with(TS + ":443", TS)._is_trusted())

    print("\n3b. LOOKALIKES ARE REFUSED (exact match, never a suffix test)")
    # ⚠ THESE ARE THE REASON IT IS NOT endswith() OR `in`.
    for bad, why in (
            ("evil.ts.net", "a different host on the same public suffix"),
            ("ts.net.evil.com", "the trusted name as a PREFIX of an attacker's"),
            ("mac.tailnet-1234.ts.net.evil.com", "trusted name then a suffix"),
            ("evilmac.tailnet-1234.ts.net", "trusted name with a prefix glued on"),
            ("", "no Host header at all"),
            ("attacker.example", "an unrelated name")):
        check("[NEG] %-34s refused" % bad[:34] or "(empty)",
              not handler_with(bad, TS)._is_trusted(), why)
    check("[NEG] a missing Host header is refused",
          not handler_with(None, TS)._is_trusted())

    print("\n3c. A MALFORMED ALLOWLIST ENTRY IS DROPPED, NOT GUESSED AT")
    import importlib
    os.environ["WVB_TRUSTED_HOSTS"] = ""
    import live_server
    importlib.reload(live_server)
    for raw, why in (("*.ts.net", "a wildcard"),
                     ("https://mac.ts.net", "a scheme"),
                     ("mac.ts.net/path", "a path"),
                     ("mac.ts.net:443", "a port in the entry")):
        check("[NEG] entry with %-22s is dropped" % why,
              not live_server._parse_trusted(raw), repr(raw))
    check("[+] a plain hostname survives parsing",
          live_server._parse_trusted(" Mac.TS.net , ") == frozenset({"mac.ts.net"}))
    check("[+] ...and several, comma separated",
          len(live_server._parse_trusted("a.ts.net,b.ts.net")) == 2)

    # ── 4. THE KEY NEVER LEAVES THE PROCESS ─────────────────────────────
    print("\n4. THE API KEY")
    check("the key is read from the environment", "ANTHROPIC_API_KEY" in src)
    # ⚠ THE MEANINGFUL FORM OF THIS CHECK. The first version sliced the source
    # at the last "_json" and searched the remainder -- which tested almost
    # nothing and passed or failed on where a helper happened to sit. What
    # matters is that the key is never put into a response body or a header.
    code = re.sub(r"#.*", "", src)
    leaks = re.findall(r"(?:_json|wfile\.write|send_header)\([^)]*ANTHROPIC[^)]*\)", code)
    check("[-] the key is never written into a response", not leaks, str(leaks[:1]))
    check("[+] ...over a file that really does read it",
          "os.environ" in code and "ANTHROPIC_API_KEY" in code)

    os.environ.pop("WVB_TRUSTED_HOSTS", None)
    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL SERVER ACCESS GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
