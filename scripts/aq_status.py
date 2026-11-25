#!/usr/bin/env python3
"""What the conference tournaments have already decided (Cody, 2026-11-22).

One answer for every bid-picking surface: a league's real champion holds its automatic bid, and a team that has
lost in its conference tournament can no longer win it. Champions come from NCAA.com's AQ tracker (the latest
stored capture), eliminations from the single-elimination check in conf_tournament_observed_2026.json.
Everything is keyed by reconcile_2025.norm(). Missing files mean nothing is decided; nothing is guessed.
"""
import json, os

from ingest_conf_tournaments import OUT, RAW, SNAP, same_team
from reconcile_2025 import norm


def load():
    """{"champions": {norm(team): conference}, "eliminated": set(norm(team))}"""
    champions, eliminated = {}, set()
    if os.path.exists(SNAP):
        rows = [json.loads(l) for l in open(SNAP, encoding="utf-8") if l.strip()]
        polls = os.path.join(RAW, "polls_rpi.jsonl")
        if rows and os.path.exists(polls):
            lines = open(polls, encoding="utf-8").read().splitlines()
            alias = {"Metro": "MAAC"}
            by_conf = {}
            for r in json.loads(lines[-1])["rows"]:
                by_conf.setdefault(alias.get(r.get("Conf"), r.get("Conf")), []).append(r["School"])
            for conf, tr in rows[-1]["leagues"].items():
                if not tr.get("winner"):
                    continue
                hit = [s for s in by_conf.get(conf, []) if same_team(s, tr["winner"])]
                if len(hit) == 1:
                    champions[norm(hit[0])] = conf
    if os.path.exists(OUT):
        for lg in (json.load(open(OUT, encoding="utf-8")).get("leagues") or {}).values():
            for m in lg.get("matches") or []:
                if m.get("winner"):
                    eliminated.add(norm(m["b"] if m["winner"] == m["a"] else m["a"]))
    return {"champions": champions, "eliminated": eliminated - set(champions)}
