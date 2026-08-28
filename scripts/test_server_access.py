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
    if not check_compression():
        FAILS.append("the page is served compressed, text only, on request")
    if not check_tailnet_binding():
        FAILS.append("tailnet listener binds only its own tailnet address")
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL SERVER ACCESS GUARDS PASS")
    return 0



def check_tailnet_binding():
    """The tailnet listener may not become a LAN listener.

    ⚠ THE WHOLE POINT IS THE INTERFACE IT IS NOT ON. Cody asked for the hub on
    his phone from anywhere, which Tailscale gives, and explicitly ruled out
    binding 0.0.0.0, exposing the LAN, and opening router ports. Verified live
    when this was built: the tailnet IP and the MagicDNS name both answer 200,
    and the machine's own LAN address (192.168.1.26) refuses the connection.
    ⚠ Tailscale SERVE is not used -- the App Store build cannot run it -- and
    FUNNEL must never be, because Funnel is the public internet.
    """
    src = open(os.path.join(REPO, "scripts/live_server.py"),
               encoding="utf-8").read()
    ok = True
    for bad in ('ThreadingHTTPServer(("0.0.0.0"', "ThreadingHTTPServer((''",
                'ThreadingHTTPServer(("",'):
        if bad in src:
            print("  FAIL binds a wildcard address: %s" % bad)
            ok = False
    # ⚠ CHECK WHAT IT RUNS, NOT WHAT IT SAYS. The first version searched for
    # the word "funnel" and tripped on the comment that promises never to use
    # it. Scope the check to actual invocations: the only tailscale subcommand
    # this server may ever run is `status`.
    import re as _re
    for m in _re.finditer(r"\[\s*cand\s*,\s*([^\]]*)\]", src):
        args = m.group(1)
        if "funnel" in args or "serve" in args:
            print("  FAIL live_server invokes tailscale %s" % args)
            ok = False
    if 'subprocess' in src and '"status", "--json"' not in src:
        print("  FAIL the tailscale call is not the read-only status call")
        ok = False
    # the second listener must come from tailscale_self(), never from a
    # user-supplied host that could be anything
    if "WVB_TAILNET" in src and "tailscale_self()" not in src:
        print("  FAIL the tailnet listener does not resolve its own address")
        ok = False
    if "globals()[\"TRUSTED_HOSTS\"]" in src and "frozenset(" not in src:
        print("  FAIL the allowlist stopped being a frozenset")
        ok = False
    print("  %-64s %s" % ("tailnet listener binds only its own tailnet address",
                          "ok" if ok else "FAIL"))
    return ok



def check_compression():
    """The page must go over the wire compressed, and unchanged.

    ⚠ THE PHONE WAS PULLING 10.5 MB WHEN 1.6 MB WOULD DO. GitHub Pages gzips
    this page to 1.5 MB; SimpleHTTPRequestHandler compresses nothing, and the
    LOCAL server is the one Cody's phone reads over Tailscale -- so every visit
    pulled the whole uncompressed page over cellular. Measured after the fix:
    10,484,511 bytes became 1,683,361, and the decompressed bytes are
    byte-identical to the file on disk.

    ⚠ TEXT ONLY, AND ONLY WHEN THE CLIENT ASKS. Re-compressing an image or a
    font wastes CPU for nothing, and a client that does not advertise gzip must
    still get plain bytes -- a server that compresses unconditionally breaks
    those clients silently.
    """
    src = open(os.path.join(REPO, "scripts/live_server.py"),
               encoding="utf-8").read()
    ok = True
    for need, why in (
            ("Content-Encoding", "no compression header is sent"),
            ("Vary", "a cache could serve gzipped bytes to a client that "
                     "cannot read them"),
            ("Accept-Encoding", "it must only compress when asked"),
            ("_GZIP_TYPES", "it must compress text only")):
        if need not in src:
            print("  FAIL %s -- %s" % (need, why))
            ok = False
    # a client that does not ask must fall through to the base handler
    if "if not accepts or not ctype.startswith" not in src:
        print("  FAIL it does not fall back for a client that cannot gunzip")
        ok = False
    print("  %-64s %s" % ("the page is served compressed, text only, on request",
                          "ok" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.exit(main())
