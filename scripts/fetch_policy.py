#!/usr/bin/env python3
"""ONE network policy for every script that follows school or published links
(mail 054). The no-scrape hook guards shell and WebFetch; Python's urllib is
invisible to it, and urllib follows redirects silently -- so an allowed
school URL could land on a blocked host before any final-URL check (the
pilot sent 16 requests to stats.statbroadcast.com that way; all 403).

  * the blocked-host list is read from .claude/hooks/no_scrape.py itself --
    one list, no copy to drift
  * FAIL CLOSED: if the list cannot be loaded, every request is refused
  * matching uses the parsed HOSTNAME (lower-cased, port and userinfo
    stripped): exact host or a true subdomain ("x.statbroadcast.com");
    look-alikes ("notstatbroadcast.com", "statbroadcast.com.evil") do not
    match by accident either way
  * every redirect hop is checked BEFORE it is followed

urlopen() is a drop-in for urllib.request.urlopen. Blocked -> BlockedURL, a
URLError subclass, so existing `except URLError` paths handle it.
"""
import importlib.util
import os
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, ".claude", "hooks", "no_scrape.py")


class BlockedURL(urllib.error.URLError):
    pass


class PolicyUnavailable(BlockedURL):
    pass


_BLOCKED = None


def blocked_hosts(path=HOOK):
    global _BLOCKED
    if _BLOCKED is None or path != HOOK:
        try:
            spec = importlib.util.spec_from_file_location("no_scrape_policy", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            hosts = set(h.lower().strip(".") for h in mod.BLOCKED)
            if not hosts:
                raise ValueError("empty blocked list")
        except Exception as exc:                       # noqa: BLE001
            raise PolicyUnavailable("network policy could not be loaded (%s) -- refusing" % exc)
        if path != HOOK:
            return hosts
        _BLOCKED = hosts
    return _BLOCKED


def host_of(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def is_blocked(url, hosts=None):
    hosts = blocked_hosts() if hosts is None else hosts
    h = host_of(url)
    if not h:
        return True                     # unparseable -> refuse
    return any(h == b or h.endswith("." + b) for b in hosts)


def check(url):
    if is_blocked(url):
        raise BlockedURL("blocked by project network policy: %s" % host_of(url))


class PolicyRedirect(urllib.request.HTTPRedirectHandler):
    """Checks every hop before it is requested. Subclass this (not the stock
    handler) when a script needs custom redirect behaviour."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(*handlers):
    hs = list(handlers)
    if not any(isinstance(h, PolicyRedirect) or (isinstance(h, type) and issubclass(h, PolicyRedirect)) for h in hs):
        hs.append(PolicyRedirect)
    return urllib.request.build_opener(*hs)


def urlopen(req, timeout=None, *args, **kw):
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    check(url)
    opener = build_opener()
    return opener.open(req, timeout=timeout) if timeout is not None else opener.open(req)
