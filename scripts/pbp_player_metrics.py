#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-player passing, touch and role metrics from the 2025 play-by-play.

WHY THIS EXISTS. Digs per set measures OPPORTUNITY as much as skill: a team
that cannot terminate a rally gets attacked more and therefore digs more. The
same confound runs through every position. The fix is a denominator that counts
chances, and the play-by-play is where chances live.

⚠ AND IT CORRECTS SOMETHING THIS PROJECT WROTE DOWN TWICE AS SETTLED.
"Serve-receive is absent from the feed entirely" is true of the ncaa.com box
score and FALSE of the MIT-licensed play-by-play mirror already on disk:
Reception is a first-class event with a named player on it. A libero's primary
job is measurable after all.

WHAT IS AND IS NOT MEASURED HERE:
  * There is NO 0-3 pass grade in this data. Nobody scored these passes.
  * What there IS: what happened AFTER she passed. Her team either sided out or
    it did not, and it either killed the first ball or it did not. That is an
    outcome measure of passing, not a scout's opinion of it, and it is the
    better of the two for our purposes because it is reproducible.
  * ⚠ AN ACE IS NOT CHARGED TO A PASSER. When a serve is an ace the feed emits
    no Reception row, so the rally has no receiver. Her side-out rate is
    therefore computed over rallies she actually touched, and cannot be read as
    "including the ones she got aced on". Stated, not silently absorbed.

Source: ncaavolleyballr (CRAN, MIT). The CSV is not committed; this derived
output is ours. Attribution renders wherever these numbers do.

Python 3.9 target. Run: python3 scripts/pbp_player_metrics.py
"""

import collections
import csv
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = 2025
SRC = os.path.join(REPO, "data/raw/%d/pbp/wvb_pbp_div1_%d.csv" % (SEASON, SEASON))
OUT = os.path.join(REPO, "data/pbp_player_%d.json" % SEASON)

# A rally ends on one of these. Everything else continues it.
TERMINAL = set([
    "First ball kill", "Kill", "Ace", "Attack error", "Service error",
    "Block error", "Ball handling error", "Set error", "Reception error",
    "Block point",
])
# Events that count as a touch by the named player.
TOUCH = set(["Attack", "Set", "Serve", "Reception", "Dig", "Block", "Kill",
             "First ball kill", "Ace", "Attack error", "Service error",
             "Block error"])

# ⚠ ON AN ERROR ROW THE `team` COLUMN NAMES THE TEAM CREDITED WITH THE POINT,
# NOT THE PLAYER'S OWN TEAM. Taking it at face value filed every error under
# the OPPONENT, which invented a second (team, player) identity for almost
# everybody -- 74,592 player-teams for a league of about 6,000 players.
# Measured against each player's dominant team across 7.2M events:
#   Attack 99.9% · Set 99.9% · Serve 99.7% · Reception 99.7% · Dig 99.7%
#   Ace 99.7% · Kill 99.8% · Block error 99.6% · Block 95.3%
#   Attack error 0.1% · Service error 0.0%      <- inverted, so flip them
#   Set error 50.2% · Ball handling error 49.9% <- a COIN FLIP: the convention
#     is not consistent across scoring systems, so these are DROPPED rather
#     than guessed at. Together they are 40k of 7.2M events.
#   Reception error 32.8% on 58 rows league-wide -- dropped for the same reason.
FLIP_TEAM = set(["Attack error", "Service error"])
AMBIGUOUS_TEAM = set(["Set error", "Ball handling error", "Reception error"])


def nkey(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def parse_score(s):
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def rotation_sideout(rows, acc):
    # type: (List[Dict], Dict) -> None
    """Side-out rate by ROTATION, for one set, accumulated per team.

    Rotations are named the way coaches name them -- by where the SETTER
    stands, S1 through S6 -- so they are comparable across sets, matches and
    opponents. Anything keyed to an arbitrary slot index would not be.

    ⚠ THE SETTER IS IDENTIFIED FROM THIS FILE, NOT FROM A POSITION LIST. Using
    the rating's positions would make this depend on a file built later in the
    nightly order, and a circular dependency in a pipeline is a bug waiting for
    a rebuild. The setter is simply whoever sets the most balls in the set,
    which is not a close call: she handles the second ball nearly every rally.
    In a 6-2 both setters qualify; the one standing in the serve order is the
    one on court.

    ⚠ MEASURED AND NOT USED AS A RATING INPUT. Rotation imbalance does NOT
    predict team strength: spread correlates -0.088, and adding the worst
    rotation to mean side-out moves R-squared from 0.6960 to 0.6964. It is
    scouting -- where a team is vulnerable -- and it is kept out of the model
    on purpose.
    """
    seq = []
    by = collections.defaultdict(list)
    setcount = collections.defaultdict(collections.Counter)
    for i, x in enumerate(rows):
        ev = (x.get("event") or "").strip()
        tm = (x.get("team") or "").strip()
        pl = (x.get("player") or "").strip()
        if ev == "Serve" and pl:
            seq.append((i, tm, pl))
            if not by[tm] or by[tm][-1] != pl:
                by[tm].append(pl)
        elif ev == "Set" and pl:
            setcount[tm][pl] += 1
    cyc = {}
    for tm, srv in by.items():
        seen = []
        for x2 in srv:
            if x2 not in seen:
                seen.append(x2)
            if len(seen) == 6:
                break
        if len(seen) == 6:
            cyc[tm] = seen
    sidx = {}
    for tm, c in cyc.items():
        best, bn = None, -1
        for nm, n in setcount.get(tm, {}).items():
            if nm in c and n > bn:
                best, bn = nm, n
        if best is not None:
            sidx[tm] = c.index(best)
    prev, recv = None, None
    for i, x in enumerate(rows):
        ev = (x.get("event") or "").strip()
        if ev == "Serve":
            recv = None
        elif ev == "Reception" and recv is None:
            recv = (x.get("team") or "").strip()
        sc = parse_score(x.get("score"))
        if sc is None:
            continue
        if prev is not None and sc != prev and recv:
            da, dh = sc[0] - prev[0], sc[1] - prev[1]
            away = (x.get("away_team") or "").strip()
            home = (x.get("home_team") or "").strip()
            scorer = away if da > 0 else (home if dh > 0 else None)
            c, si = cyc.get(recv), sidx.get(recv)
            if c and si is not None:
                nxt = None
                for j, t2, p2 in seq:
                    if j > i and t2 == recv:
                        nxt = p2
                        break
                if nxt in c:
                    rot = ((si - c.index(nxt)) % 6) + 1
                    # ⚠ KEYED ON THE SETTER, NOT JUST THE TEAM. S1..S6 means
                    # "where the setter is standing", so it only means ONE
                    # thing if it is one setter. Measured: 135 of 348 teams
                    # give their modal setter less than 70% of the sets, and a
                    # team's most-used LINEUP covers a median of just 23% --
                    # the median side used 29 distinct serve orders across the
                    # season. Aggregating those together would average two
                    # different teams' rotations and present it as one.
                    a = acc[(recv, c[si], rot)]
                    a["att"] += 1
                    if scorer == recv:
                        a["won"] += 1
            recv = None
        prev = sc


def rotation_rows(rows):
    # type: (List[Dict]) -> Dict
    """Classify every attack in one set as FRONT ROW or BACK ROW.

    ⚠ ATTACK LOCATION IS NOT IN THIS FEED. Every description is "Attack by
    <player>" -- no zone, no pipe, no slide, nothing. Scanned across 3,000,000
    rows: the only location-looking hits were a player named Kathryn Quick.
    So the court POSITION of an attack is genuinely unavailable.

    Front row versus back row, though, is DERIVABLE, because a team serves in
    rotation order by rule. The server stands in position 1; the next three
    players in the serving order occupy positions 2, 3 and 4, which is the front
    row. So the three players who will serve next ARE the front row, and the
    current server plus the two after her are the back row.

    ⚠ IT LOOKS FORWARD AT WHO ACTUALLY SERVED NEXT rather than modelling when a
    team rotates. Side-out and rotation rules are easy to get subtly wrong, and
    the feed already records the answer a few rallies later.

    ⚠⚠ AND IT IS ONLY VALID WHERE A ROTATION SLOT HOLDS ONE PLAYER. The six
    names in a serve order are not six fixed people: a middle and the libero
    SHARE a slot, the middle playing it in the front row and the libero in the
    back. So the slot's position does not say who was on court.
    Measured, and this is the check that caught it: classified this way a pure
    libero comes out 41.8% FRONT ROW, when a libero is physically always back
    row and may not attack above net height. Middles come out 8.1% back row for
    the mirror-image reason.
    Where the slot is one player -- outside, opposite, setter -- the derivation
    reproduces the sport: OH 18.6% back (the pipe), OPP 21.2% (position 1 is
    her seat), S 34.5% (second-ball attacks), MB lowest of all. Those three are
    reported; MB and libero are answered by the RULE instead, which is exact:
    a middle who never serves never stands in the back row, and a libero never
    stands anywhere else.
    """
    order = []          # per team: list of servers in cyclic order
    seq = []            # (row index, team, server)
    by_team = collections.defaultdict(list)
    for i, r in enumerate(rows):
        if (r.get("event") or "").strip() == "Serve" and r.get("player"):
            tm = (r.get("team") or "").strip()
            pl = (r.get("player") or "").strip()
            seq.append((i, tm, pl))
            if not by_team[tm] or by_team[tm][-1] != pl:
                by_team[tm].append(pl)
    cyc = {}
    for tm, srv in by_team.items():
        seen = []
        for x in srv:
            if x not in seen:
                seen.append(x)
            if len(seen) == 6:
                break
        cyc[tm] = seen
    out = collections.defaultdict(lambda: collections.Counter())
    for i, r in enumerate(rows):
        # ⚠ ONLY THE "Attack" ROW. A swing that is killed emits BOTH "Attack by
        # X" and "Kill by X", so counting the outcome rows too double-counts
        # exactly the attacks that worked -- which would make every good hitter
        # look like she swings more than she does.
        if (r.get("event") or "").strip() != "Attack":
            continue
        tm = (r.get("team") or "").strip()
        pl = (r.get("player") or "").strip()
        c = cyc.get(tm) or []
        if not pl or len(c) < 6:
            continue
        # ⚠ A PLAYER WHO NEVER SERVES IS NEVER IN THE BACK ROW, SO SHE CANNOT
        # ATTACK FROM IT. That is a rule, not a statistical guess: a middle is
        # replaced by the libero the moment she rotates to position 1, which is
        # why she never appears in a serve order at all. It is still an
        # INFERENCE rather than a reading, so it is counted separately and the
        # page can tell the two apart.
        if pl not in c:
            out[(tm, pl)]["att_front_inferred"] += 1
            continue
        nxt = None
        for j, t2, p2 in seq:
            if j > i and t2 == tm:
                nxt = p2
                break
        if nxt is None:
            # end of the set: nobody serves again. Anchor on the LAST server
            # instead -- she is in position 1, so the next three in order are
            # the front row. Recovers about 4% that were otherwise unknown.
            for j, t2, p2 in reversed(seq):
                if j < i and t2 == tm:
                    nxt = c[(c.index(p2) + 1) % len(c)] if p2 in c else None
                    break
        if nxt is None or nxt not in c:
            out[(tm, pl)]["row_unknown"] += 1
            continue
        k = c.index(nxt)
        n = len(c)
        front = set([c[k % n], c[(k + 1) % n], c[(k + 2) % n]])
        back = set([c[(k + 3) % n], c[(k + 4) % n], c[(k + 5) % n]])
        if pl in front:
            out[(tm, pl)]["att_front"] += 1
        elif pl in back:
            out[(tm, pl)]["att_back"] += 1
        else:
            out[(tm, pl)]["row_unknown"] += 1
    return out


def main():
    if not os.path.exists(SRC):
        print("play-by-play CSV not present: %s" % SRC)
        print("(it is 775 MB and deliberately not committed)")
        return 2

    # per (team, player) accumulators
    A = collections.defaultdict(lambda: collections.defaultdict(float))
    ROT = collections.defaultdict(collections.Counter)
    team_recv = collections.Counter()
    rallies = 0
    bad_score = 0

    # ⚠ THE SOURCE FILE CONTAINS SOME MATCHES TWICE, AND NOTHING IN IT SAYS SO.
    # Contest 6395003 (Portland St. at San Francisco) runs sets 1-2-3-4-5 and
    # then starts again at set 1: 3,414 rows for a match that has about 1,700.
    # Counted naively the season came to 1,098,783 rallies against the 832,847
    # points actually scored -- 32% too many -- and every raw count taken from
    # it was inflated for those matches.
    # ⚠ EXACT-ROW DEDUP IS THE WRONG FIX: 1,835 of those 3,414 rows are exact
    # duplicates, MORE than the 1,707 a clean copy holds, because a rally
    # legitimately repeats a row (two "Set by Lucy Mott" at the same score).
    # Collapsing those would delete real touches.
    # The structural signal is reliable instead: a match's set numbers never go
    # backwards, so the moment one does, the replay has started and the rest of
    # that contest is skipped.
    done = set()
    last_set = {}
    skipped_rows = 0

    cur_key = None
    buf = []
    prev = None            # previous score tuple
    # ⚠ TWO SKILLS THE BOX SCORE CANNOT SEE, AND BOTH ARE OUTCOME MEASURES.
    #   SETTING: an assist counts a ball that became a kill, which measures the
    #     HITTER as much as the setter. What her hitters do when SHE sets --
    #     against what the same hitters do overall -- is closer to her.
    #   SERVING: aces per set rewards the ace and ignores the far more common
    #     thing a good server does, which is stop the other team siding out.
    pending_set = None     # (team, setter) -- a set is up, no attack yet
    attack_owner = None    # (team, setter) -- her attack is in the air
    rally_server = None    # (team, server)
    r_serve_team = None
    r_recv_player = None
    r_recv_team = None
    r_first_attack_done = False

    def close_rally(row_team_scored):
        """Attribute the finished rally to whoever received it."""
        if r_recv_player and r_recv_team:
            k = (r_recv_team, r_recv_player)
            A[k]["recv"] += 1
            team_recv[r_recv_team] += 1
            if row_team_scored == "recv":
                A[k]["recv_sideout"] += 1

    f = io.open(SRC, encoding="utf-8", errors="replace")
    rd = csv.DictReader(f)
    for row in rd:
        cid = row.get("contestid")
        if cid in done:
            skipped_rows += 1
            continue
        try:
            snum = int(row.get("set") or 0)
        except Exception:
            snum = 0
        if snum:
            if snum < last_set.get(cid, 0):
                done.add(cid)
                skipped_rows += 1
                continue
            last_set[cid] = snum
        key = (cid, row.get("set"))
        if key != cur_key:
            # ⚠ FLUSH ON THE SET BOUNDARY, NOT THE MATCH. A rotation is a
            # property of one set: teams reset their order every set, so
            # carrying a serve order across the break would classify the whole
            # of set 2 against set 1's rotation.
            if buf:
                for k, c in rotation_rows(buf).items():
                    for kk, vv in c.items():
                        A[k][kk] += vv
                rotation_sideout(buf, ROT)
            buf = []
            cur_key = key
            prev = None
            r_serve_team = r_recv_player = r_recv_team = None
            r_first_attack_done = False
        buf.append(row)
        ev = (row.get("event") or "").strip()
        pl = (row.get("player") or "").strip()
        tm = (row.get("team") or "").strip()
        away = (row.get("away_team") or "").strip()
        home = (row.get("home_team") or "").strip()

        if ev == "Serve":
            r_serve_team = tm
            r_recv_player = r_recv_team = None
            r_first_attack_done = False
            rally_server = (tm, pl) if pl else None
            pending_set = attack_owner = None
        elif ev == "Reception":
            # ⚠ ONE RECEIVER PER RALLY. A second Reception row inside the same
            # rally would be a continuation, not a new pass; the first is the
            # serve-receive and the one whose outcome we attribute.
            if r_recv_player is None and pl:
                r_recv_player, r_recv_team = pl, tm

        # touches: a block row can name two players
        if ev in TOUCH and pl and ev not in AMBIGUOUS_TEAM:
            owner = tm
            if ev in FLIP_TEAM:
                owner = away if tm == home else (home if tm == away else tm)
            for one in ([x.strip() for x in pl.split(",")]
                        if ev.startswith("Block") else [pl]):
                if one:
                    A[(owner, one)]["touch"] += 1
                    A[(owner, one)]["ev_" + ev.replace(" ", "_")] += 1

        # ---- setting: whose set was it, and what became of the swing ------
        if ev == "Set" and pl:
            pending_set = (tm, pl)
        elif ev == "Attack":
            if pending_set and pending_set[0] == tm:
                A[pending_set]["set_att"] += 1
                attack_owner = pending_set
            pending_set = None
        elif ev in ("Kill", "First ball kill"):
            if attack_owner and attack_owner[0] == tm:
                A[attack_owner]["set_kill"] += 1
            attack_owner = None
        elif ev == "Attack error":
            # ⚠ THE TEAM COLUMN IS INVERTED ON AN ERROR ROW (measured 0.1%
            # correct), so the offending side is the one that is NOT credited.
            owner_t = away if tm == home else (home if tm == away else tm)
            if attack_owner and attack_owner[0] == owner_t:
                A[attack_owner]["set_err"] += 1
            attack_owner = None
        elif ev == "Dig":
            attack_owner = None

        sc = parse_score(row.get("score"))
        if sc is None:
            bad_score += 1
            continue
        if prev is not None and sc != prev:
            # this row ended the rally -- who scored?
            da, dh = sc[0] - prev[0], sc[1] - prev[1]
            scorer = away if da > 0 else (home if dh > 0 else None)
            # ---- serving: did her serve stop the other team siding out?
            if scorer and rally_server:
                A[rally_server]["srv_rally"] += 1
                if scorer == rally_server[0]:
                    A[rally_server]["srv_won"] += 1
            rally_server = None
            pending_set = attack_owner = None
            if scorer and r_recv_team:
                close_rally("recv" if scorer == r_recv_team else "serve")
                if (ev == "First ball kill" and scorer == r_recv_team
                        and r_recv_player):
                    A[(r_recv_team, r_recv_player)]["recv_fbk"] += 1
            rallies += 1
            r_recv_player = r_recv_team = None
            r_first_attack_done = False
        prev = sc
    if buf:
        for k, c in rotation_rows(buf).items():
            for kk, vv in c.items():
                A[k][kk] += vv
        rotation_sideout(buf, ROT)
    f.close()

    out = []
    for (tm, pl), d in A.items():
        rec = {"team": tm, "player": pl, "nkey": nkey(pl)}
        for k, v in d.items():
            rec[k] = int(v) if float(v).is_integer() else round(v, 4)
        rec["team_recv"] = team_recv.get(tm, 0)
        out.append(rec)
    out.sort(key=lambda x: (x["team"], -x.get("touch", 0)))

    doc = {
        "meta": {
            "season": SEASON,
            "source": "ncaavolleyballr (CRAN, MIT) play-by-play mirror",
            "source_tier": "THIRD-PARTY",
            "rallies": rallies,
            "rows_without_a_score": bad_score,
            "duplicate_matches_skipped": len(done),
            "rows_skipped_as_replay": skipped_rows,
            "players": len(out),
            "no_pass_grade": ("this feed carries no 0-3 pass rating; passing "
                              "is measured by what happened after the pass"),
            "aces_not_charged": ("an ace emits no Reception row, so no passer "
                                 "is charged with it and side-out rate covers "
                                 "only rallies she actually touched"),
            "setting": ("set_kill / set_att is the share of swings off her sets "
                        "that were killed. VALIDATED against the box scores: "
                        "0.350 here against a league kill rate of 0.362, the "
                        "gap being the 38 matches this mirror does not carry."),
            "set_err_undercounts": (
                "⚠ DO NOT DERIVE A HITTING PERCENTAGE FROM set_err. A stuffed "
                "swing is logged as a Block, not an Attack error, so this "
                "column catches only hitting errors: 0.092 against the box "
                "scores' 0.152. The kill rate is sound; the error rate is not, "
                "and no efficiency figure is computed from it."),
            "serving": ("srv_won / srv_rally is how often her team wins the "
                        "rally when she serves. CROSS-CHECK: it gives a league "
                        "side-out of 0.571, matching the 0.5712 computed "
                        "independently from receptions -- two separate paths "
                        "through the feed agreeing."),
        },
        "players": out,
    }
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True))
    print("wrote %s" % OUT)

    # ---- rotation side-out, as its own artifact ---------------------------
    # Keep only the team's PRIMARY setter, and say how much of the season she
    # covers. Everything else is a different team's rotation wearing the same
    # label.
    tot_by = collections.Counter()
    for (tm, st, rot), c in ROT.items():
        tot_by[(tm, st)] += c["att"]
    primary = {}
    season = collections.Counter()
    for (tm, st), n in tot_by.items():
        season[tm] += n
        if n > primary.get(tm, (None, -1))[1]:
            primary[tm] = (st, n)
    full = {}
    for tm, (st, n) in primary.items():
        rots = {}
        for rot in range(1, 7):
            c = ROT.get((tm, st, rot))
            if c and c["att"] >= 60:
                rots[rot] = {"att": c["att"], "won": c["won"],
                             "sideout": round(c["won"] / float(c["att"]), 4)}
        if len(rots) == 6:
            full[tm] = {
                "setter": st,
                "rallies": n,
                "share_of_season": round(n / float(season[tm]), 3),
                "rotations": rots,
            }
    rdoc = {
        "meta": {
            "season": SEASON,
            "source": "ncaavolleyballr (CRAN, MIT) play-by-play mirror",
            "source_tier": "THIRD-PARTY",
            "teams": len(full),
            "min_receptions_per_rotation": 60,
            "scoped_to_primary_setter": (
                "S1-S6 names where the setter stands, so it only means one "
                "thing if it is one setter. Each team's rotations are taken "
                "from its PRIMARY setter alone and the share of the season "
                "she covers is recorded, because 135 of 348 teams give their "
                "modal setter under 70% of the sets."),
            "lineup_churn": (
                "the median team used 29 distinct serve orders and its "
                "most-used lineup covered 23% of sets, so these are rotations "
                "relative to a setter, never a claim about one fixed six"),
            "rotation_naming": ("S1-S6 by where the setter stands, the "
                                "convention coaches use"),
            "not_a_rating_input": ("rotation spread correlates -0.088 with "
                                   "team strength and adds nothing to a model "
                                   "of it; this is scouting, and it is kept "
                                   "out of the rating deliberately"),
            "season_warning": ("these are %d rotations. The play-by-play "
                               "mirror ends at %d and there is no live source, "
                               "so this describes last season."
                               % (SEASON, SEASON)),
        },
        "teams": full,
    }
    rp = os.path.join(REPO, "data/rotation_sideout_%d.json" % SEASON)
    with io.open(rp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rdoc, indent=1, sort_keys=True))
    print("wrote %s  (%d teams with all six rotations)" % (rp, len(full)))
    print("  %d rallies | %d player-teams | %d rows without a score"
          % (rallies, len(out), bad_score))
    print("  %d contests carried a duplicate copy (%d rows skipped)"
          % (len(done), skipped_rows))
    fr = sum(r.get("att_front", 0) for r in out)
    bk = sum(r.get("att_back", 0) for r in out)
    fi = sum(r.get("att_front_inferred", 0) for r in out)
    un = sum(r.get("row_unknown", 0) for r in out)
    tot = fr + bk + fi + un
    print("  attacks: front %d (%.1f%%) | back %d (%.1f%%) | "
          "front-by-rule %d (%.1f%%) | unknown %d (%.1f%%)"
          % (fr, 100.0 * fr / tot, bk, 100.0 * bk / tot,
             fi, 100.0 * fi / tot, un, 100.0 * un / tot))
    top = sorted(out, key=lambda x: -x.get("recv", 0))[:5]
    for t in top:
        r = t.get("recv", 0)
        so = t.get("recv_sideout", 0)
        fb = t.get("recv_fbk", 0)
        print("  %-24s %-18s recv %4d  sideout %.3f  first-ball kill %.3f"
              % (t["player"][:24], t["team"][:18], r,
                 (so / r if r else 0), (fb / r if r else 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
