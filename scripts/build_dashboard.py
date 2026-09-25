#!/usr/bin/env python3
"""Center Court: Cody's one-screen dashboard, rebuilt every local refresh.

Asked 2026-09-23 ("a visual data dashboard with photos and logos ... I can
follow"). Local-only and PRIVATE: writes Cody/CENTER-COURT.html (gitignored),
served by live_server at /CENTER-COURT.html. Every number comes from the
same counted finals and artifacts the hub uses -- season_counts.countable,
digby_top25, predictions, season_sim, conference_lab -- so the two pages
cannot disagree. Photos and crests are HOTLINKED URLs, never downloaded
(the headshot rule). Live scores come from live_server's /api/live, polled
by the page every 60s. Run by local_refresh.py after build_hub.

Python 3.9 target.
"""
import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
OUT = os.path.join(REPO, "Cody", "CENTER-COURT.html")
TEMPLATE = os.path.join(REPO, "scripts", "dashboard_template.html")


def collect():
    os.chdir(REPO)
    import season_counts as SC
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
    d = json.load(open('data/data_2026.json'))
    games = SC.countable(d['games'], 2026)
    bl = json.load(open('data/digby_top25_2026.json'))
    B = {t['team']: t for t in bl['all']}
    hist = [json.loads(l) for l in open('data/rankings_history_2026.jsonl') if l.strip()]
    prev = hist[-1]
    prevrank = {}
    for k, v in prev.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and 'rank' in v[0]:
            prevrank = {r['team']: r['rank'] for r in v}
    pre_rank = {t['team']: i + 1 for i, t in enumerate(sorted(bl['all'], key=lambda t: -(t.get('preseason_z') or -9)))}
    sim = {t['team']: t for t in json.load(open('data/season_sim_2026.json'))['teams']}
    top = []
    for t in bl['all'][:25]:
        s = sim.get(t['team'], {})
        top.append(dict(r=t['rank'], t=t['team'], rec=s.get('record_so_far'), sc=round(t['score'], 3),
                        pz=t['preseason_z'], sz=t['season_z'], w=t['weight_on_season'],
                        prev=prevrank.get(t['team']), conf=s.get('conference'),
                        pre=pre_rank.get(t['team']), m=t.get('matches'), pw=s.get('proj_wins_p50'), ct=s.get('conf_title_pct'), tp=s.get('tournament_pct')))
    now = datetime.datetime.now(PT)
    res = []
    for g in games:
        if g.get('state') != 'F':
            continue
        ep = g.get('start_time_epoch') or 0
        dt = datetime.datetime.fromtimestamp(ep, PT)
        if (now - dt).days > 4:
            continue
        wi = SC.winner_index(g)
        if wi is None:
            continue
        ts = g['teams']; W = ts[wi]; L = ts[1 - wi]
        ls = [(p.get('home'), p.get('visit')) for p in g.get('linescores') or []]
        sets = [(h, v) if W['is_home'] else (v, h) for h, v in ls]
        res.append(dict(d=dt.strftime('%a %b %-d'), ep=ep, w=W['name_short'], l=L['name_short'],
                        ws=W['sets_won'], lsw=L['sets_won'], sets=sets,
                        rw=B.get(W['name_short'], {}).get('rank'), rl=B.get(L['name_short'], {}).get('rank')))
    res.sort(key=lambda x: -x['ep'])
    pl = json.load(open('data/raw/2026/players_2026.json'))['players']
    tn = {t['team_id']: t['name_short'] for t in d['teams']}
    maxs = max(p['sets'] for p in pl); mins = max(3, maxs // 2)
    def row(p, v):
        return dict(n=p['first'] + ' ' + p['last'], t=tn.get(p['team_id'], '?'), pos=p.get('pos'), v=v, s=p['sets'])
    def lead(fn, nd=2, n=5):
        q = sorted([p for p in pl if p['sets'] >= mins], key=fn, reverse=True)[:n]
        return [row(p, round(fn(p), nd)) for p in q]
    leaders = [
        ('Points / set', lead(lambda p: (p['kills'] + p['aces'] + p['block_solos'] + 0.5 * p['block_assists']) / p['sets'])),
        ('Kills / set', lead(lambda p: p['kills'] / p['sets'])),
        ('Assists / set', lead(lambda p: p['assists'] / p['sets'])),
        ('Digs / set', lead(lambda p: p['digs'] / p['sets'])),
        ('Blocks / set', lead(lambda p: (p['block_solos'] + 0.5 * p['block_assists']) / p['sets'])),
        ('Aces / set', lead(lambda p: p['aces'] / p['sets'])),
    ]
    amin = max(100, maxs * 4)
    hq = sorted([p for p in pl if p['atts'] >= amin], key=lambda p: (p['kills'] - p['errors']) / p['atts'], reverse=True)[:5]
    leaders.append(('Hitting pct', [row(p, round((p['kills'] - p['errors']) / p['atts'], 3)) for p in hq]))
    pr = json.load(open('data/predictions_2026.json'))['games']
    lim = (now + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    up = []
    for r in pr:
        ra = B.get(r['away'], {}).get('rank', 999); rh = B.get(r['home'], {}).get('rank', 999)
        if ra <= 25 and rh <= 25 and r['date'] <= lim:
            up.append(dict(date=r['date'], time=r['time'], a=r['away'], h=r['home'], ra=ra, rh=rh,
                           hw=r['home_win'], neutral=r['neutral'], ev=r.get('event')))
    # per-team detail for the top 25
    T25 = [t['t'] for t in top]
    allres = []
    for g in games:
        if g.get('state') != 'F':
            continue
        wi = SC.winner_index(g)
        if wi is None:
            continue
        ep = g.get('start_time_epoch') or 0
        allres.append((ep, g, wi))
    allres.sort(key=lambda x: x[0])
    teams = {}
    for name in T25:
        rr = []
        for ep, g, wi in allres:
            ts = g['teams']
            me = [i for i, t in enumerate(ts) if t['name_short'] == name]
            if not me:
                continue
            i = me[0]; o = ts[1 - i]
            sets = [(p.get('home'), p.get('visit')) if ts[i]['is_home'] else (p.get('visit'), p.get('home')) for p in g.get('linescores') or []]
            rr.append(dict(d=datetime.datetime.fromtimestamp(ep, PT).strftime('%b %-d'), o=o['name_short'], ha='vs' if ts[i]['is_home'] else 'at',
                           wl='W' if i == wi else 'L', sc='%s-%s' % (ts[i]['sets_won'], o['sets_won']), sets=sets,
                           orank=B.get(o['name_short'], {}).get('rank')))
        tid = [t['team_id'] for t in d['teams'] if t['name_short'] == name]
        ps = [p for p in pl if tid and p['team_id'] == tid[0] and p['sets'] >= 5]
        def pps(p): return (p['kills'] + p['aces'] + p['block_solos'] + 0.5 * p['block_assists']) / p['sets']
        ps = sorted(ps, key=pps, reverse=True)[:7]
        players = [dict(n=p['first'] + ' ' + p['last'], pos=p.get('pos'), s=p['sets'], pps=round(pps(p), 2),
                        k=round(p['kills'] / p['sets'], 2), hit=(round((p['kills'] - p['errors']) / p['atts'], 3) if p['atts'] >= 20 else None),
                        dg=round(p['digs'] / p['sets'], 2), a=round(p['assists'] / p['sets'], 2),
                        b=round((p['block_solos'] + 0.5 * p['block_assists']) / p['sets'], 2)) for p in ps]
        nxt = []
        for r in pr:
            if name in (r['away'], r['home']) and r['date'] >= now.strftime('%Y-%m-%d'):
                home = r['home'] == name
                o = r['away'] if home else r['home']
                nxt.append(dict(date=r['date'], time=r['time'], o=o, ha='vs' if home or r['neutral'] else 'at',
                                p=round(100 * (r['home_win'] if home else r['away_win'])), orank=B.get(o, {}).get('rank')))
        teams[name] = dict(res=rr, players=players, next=nxt[:4])
    sc_pts = [dict(n=p['first'] + ' ' + p['last'], t=tn.get(p['team_id'], '?'), k=round(p['kills'] / p['sets'], 2),
                   h=round((p['kills'] - p['errors']) / p['atts'], 3)) for p in pl if p['atts'] >= amin]
    cl = json.load(open('data/conference_lab_2026.json'))['confs']
    confs = sorted([dict(c=c['conf'], w=c['w'], l=c['l'], med=c['med_power'], v25=c['vs25'], t5=c['top5_power'])
                    for c in cl if c['w'] + c['l'] > 0], key=lambda c: c['med'])[:12]
    fin = [g for g in games if g.get('state') == 'F']
    five = sum(1 for g in fin if len(g.get('linescores') or []) == 5)
    base = (dict(stamp=now.strftime('%a %b %-d, %-I:%M %p PT'), top=top, res=res[:60], leaders=leaders,
                          up=up, confs=confs, nf=len(fin), five=five, mins=mins, amin=amin,
                          k=bl['meta']['k_matches'], teams=teams, scat=sc_pts, prevweek=prev.get('week') or prev.get('iso_week')))

    d = json.load(open('data/data_2026.json'))
    games = [g for g in SC.countable(d['games'], 2026) if g.get('state') == 'F' and SC.winner_index(g) is not None]
    games.sort(key=lambda g: g.get('start_time_epoch') or 0)
    gid_ok = {g['game_id'] for g in games}
    bl = json.load(open('data/digby_top25_2026.json'))
    B = {t['team']: t for t in bl['all']}
    top25 = [t['t'] for t in base['top']]
    tid2name = {t['team_id']: t['name_short'] for t in d['teams']}
    name2tid = {v: k for k, v in tid2name.items()}

    # ---- rating trend (daily snapshots + today) ----
    rh = json.load(open('data/rating_history_2026.json'))
    days = [p['day'] for p in rh['points']]
    today = datetime.datetime.now(PT).strftime('%Y-%m-%d')
    trend = {}
    for t in top25:
        s = [(p['day'], (p['teams'].get(t) or {}).get('rank')) for p in rh['points']]
        s.append((today, B[t]['rank']))
        trend[t] = s
    trend_days = days + [today]
    missing = rh['meta'].get('missing_days', [])

    # ---- box-score team totals per game ----
    box = {}
    for line in open('data/raw/2026/boxscores.jsonl'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        gid = str(r.get('game_id'))
        if gid not in gid_ok:
            continue
        per = {}
        for t in r.get('teams') or []:
            k = e = ta = 0
            for st in (t.get('team_stats') or {}).get('sets') or []:
                try:
                    k += int(st.get('kills') or 0); e += int(st.get('attackErrors') or 0); ta += int(st.get('attackAttempts') or 0)
                except ValueError:
                    pass
            if ta:
                per[str(t.get('team_id'))] = (k, e, ta)
        box[gid] = per   # last wins

    # ---- per-team match series ----
    series = {}
    for name in top25:
        tid = name2tid.get(name)
        rows = []
        w = l = 0
        for g in games:
            ts = g['teams']
            idx = [i for i, t in enumerate(ts) if t['name_short'] == name]
            if not idx:
                continue
            i = idx[0]; o = ts[1 - i]; wi = SC.winner_index(g)
            win = i == wi
            w += win; l += (not win)
            ls = g.get('linescores') or []
            mine = [(p.get('home') if ts[i]['is_home'] else p.get('visit')) for p in ls]
            theirs = [(p.get('visit') if ts[i]['is_home'] else p.get('home')) for p in ls]
            margin = round(sum(a - b for a, b in zip(mine, theirs)) / len(ls), 2) if ls else None
            b = box.get(g['game_id'], {})
            me = b.get(str(ts[i]['team_id'])); op = b.get(str(o['team_id']))
            rows.append(dict(
                d=datetime.datetime.fromtimestamp(g['start_time_epoch'], PT).strftime('%b %-d'),
                o=o['name_short'], wl='W' if win else 'L', sc='%s-%s' % (ts[i]['sets_won'], o['sets_won']),
                m=margin, rec='%d-%d' % (w, l),
                hit=round((me[0] - me[1]) / me[2], 3) if me else None,
                ohit=round((op[0] - op[1]) / op[2], 3) if op else None,
                orank=(B.get(o['name_short']) or {}).get('rank')))
        series[name] = rows

    # ---- featured players (league leaders + each top-25 team's top scorer) ----
    pl = json.load(open('data/raw/2026/players_2026.json'))['players']
    mins = base['mins']
    def pps(p): return (p['kills'] + p['aces'] + p['block_solos'] + 0.5 * p['block_assists']) / p['sets']
    elig = [p for p in pl if p['sets'] >= mins]
    feat = sorted(elig, key=pps, reverse=True)[:12]
    for name in top25:
        tid = name2tid.get(name)
        tp = sorted([p for p in elig if p['team_id'] == tid], key=pps, reverse=True)[:1]
        for p in tp:
            if p not in feat:
                feat.append(p)
    # game logs for featured players
    fkeys = {(p['team_id'], p['first'].lower(), p['last'].lower()) for p in feat}
    glog = {}
    ep = {g['game_id']: g['start_time_epoch'] for g in games}
    for line in open('data/raw/2026/playerbox.jsonl'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        gid = str(r.get('game_id'))
        if gid not in ep:
            continue
        for row in r.get('rows') or []:
            k = (str(row.get('team_id')), (row.get('first') or '').lower(), (row.get('last') or '').lower())
            if k in fkeys:
                try:
                    sets = int(row.get('gp') or 0)
                    pts = int(row.get('kills') or 0) + int(row.get('aces') or 0) + int(row.get('bs') or 0) + 0.5 * int(row.get('ba') or 0)
                except ValueError:
                    continue
                if sets:
                    glog.setdefault(k, {})[gid] = (ep[gid], round(pts / sets, 2), int(row.get('kills') or 0))
    # photos
    ph = json.load(open('data/raw/2026/roster_photos_2026.json'))['teams']
    rs = json.load(open('data/raw/2026/rosters_2026.json'))['teams']
    def photo_url(team, first, last):
        want = (first + ' ' + last).lower()
        for src in ((ph.get(team) or {}).get('photos') or {}).items():
            if src[0].lower() == want:
                return src[1]
        for p in (rs.get(team) or {}).get('players') or []:
            if (p.get('name_raw') or '').lower() == want and p.get('photo'):
                return p['photo']
        return None

    players = []
    for p in feat:
        team = tid2name.get(p['team_id'], '?')
        k = (p['team_id'], p['first'].lower(), p['last'].lower())
        log = sorted((glog.get(k) or {}).values())
        u = photo_url(team, p['first'], p['last'])
        players.append(dict(n=p['first'] + ' ' + p['last'], t=team, pos=p.get('pos'), s=p['sets'], m=p['matches'],
                            pps=round(pps(p), 2), kps=round(p['kills'] / p['sets'], 2),
                            hit=round((p['kills'] - p['errors']) / p['atts'], 3) if p['atts'] else None,
                            dps=round(p['digs'] / p['sets'], 2), aps=round(p['assists'] / p['sets'], 2),
                            bps=round((p['block_solos'] + 0.5 * p['block_assists']) / p['sets'], 2),
                            spark=[x[1] for x in log], img=(u.replace('http://', 'https://', 1) if u else None),
                            lead=p in feat[:12]))

    # ---- logos (SVG crests from ncaa.com, the feed we already use) ----
    d25 = json.load(open('data/data_2025.json'))
    seo = {t['name_short']: t.get('seoname') for t in d25['teams']}
    seo.update({t['name_short']: t.get('seoname') for t in d['teams'] if t.get('seoname')})
    # ---- team metrics: every D-I team, from the same counted finals ----
    # Box totals per game (kills/errors/attempts/aces/blocks/digs), both sides.
    tbox = {}
    for line in open('data/raw/2026/boxscores.jsonl'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        gid = str(r.get('game_id'))
        if gid not in gid_ok:
            continue
        per = {}
        for t in r.get('teams') or []:
            k = e = ta = 0
            for st in (t.get('team_stats') or {}).get('sets') or []:
                try:
                    k += int(st.get('kills') or 0); e += int(st.get('attackErrors') or 0)
                    ta += int(st.get('attackAttempts') or 0)
                except ValueError:
                    pass
            per[str(t.get('team_id'))] = [k, e, ta, 0, 0.0, 0]
        tbox[gid] = per
    # aces / blocks / digs come from the player lines (team block has no digs)
    for line in open('data/raw/2026/playerbox.jsonl'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        gid = str(r.get('game_id'))
        if gid not in tbox:
            continue
        agg = {}
        for row in r.get('rows') or []:
            a = agg.setdefault(str(row.get('team_id')), [0, 0.0, 0])
            try:
                a[0] += int(row.get('aces') or 0)
                a[1] += int(row.get('bs') or 0) + 0.5 * int(row.get('ba') or 0)
                a[2] += int(row.get('digs') or 0)
            except ValueError:
                pass
        for tid, a in agg.items():
            if tid in tbox[gid]:
                tbox[gid][tid][3:6] = a
    # D-I = the 348 the rankings carry, never the feed's division flag (the
    # feed serves West Florida as div 1 on an all-D-II schedule)
    di = {name2tid[t] for t in B if t in name2tid}
    tm = {}
    for g in games:
        ts = g['teams']; wi = SC.winner_index(g)
        ls = g.get('linescores') or []
        for i in (0, 1):
            me, op = ts[i], ts[1 - i]
            if str(me['team_id']) not in di:
                continue
            x = tm.setdefault(me['name_short'], dict(res=[], sets=0, five=[0, 0], comeback=0, close=[0, 0],
                                                    sweeps=0, k=0, e=0, ta=0, ok=0, oe=0, ota=0, aces=0, blk=0.0,
                                                    dig=0, bsets=0, marg=[]))
            win = i == wi
            x['res'].append('W' if win else 'L')
            mine = [(q.get('home') if me['is_home'] else q.get('visit')) for q in ls]
            thr = [(q.get('visit') if me['is_home'] else q.get('home')) for q in ls]
            if ls:
                x['sets'] += len(ls)
                x['marg'].append(sum(a - b for a, b in zip(mine, thr)) / len(ls))
                if len(ls) == 5:
                    x['five'][0 if win else 1] += 1
                if win and mine[0] < thr[0]:
                    x['comeback'] += 1
                if win and len(ls) == 3:
                    x['sweeps'] += 1
                for a, b in zip(mine, thr):
                    if abs(a - b) <= 2:
                        x['close'][0 if a > b else 1] += 1
            bx = tbox.get(g['game_id'], {})
            mb, ob = bx.get(str(me['team_id'])), bx.get(str(op['team_id']))
            if mb and ob and mb[2] and ob[2] and ls:
                x['k'] += mb[0]; x['e'] += mb[1]; x['ta'] += mb[2]
                x['ok'] += ob[0]; x['oe'] += ob[1]; x['ota'] += ob[2]
                x['aces'] += mb[3]; x['blk'] += mb[4]; x['dig'] += mb[5]; x['bsets'] += len(ls)
    teamstats = []
    for name, x in tm.items():
        n = len(x['res'])
        if n < 6:
            continue
        streak = 1
        for r_ in reversed(x['res'][:-1]):
            if r_ != x['res'][-1]:
                break
            streak += 1
        season = sum(x['marg']) / len(x['marg']) if x['marg'] else None
        last5 = sum(x['marg'][-5:]) / len(x['marg'][-5:]) if len(x['marg']) >= 5 else None
        bs = x['bsets']
        teamstats.append(dict(
            t=name, n=n, w=x['res'].count('W'), l=x['res'].count('L'),
            streak=('%s%d' % (x['res'][-1], streak)), sk=streak if x['res'][-1] == 'W' else -streak,
            five=x['five'], comeback=x['comeback'], close=x['close'],
            sweep=round(x['sweeps'] / n, 3), marg=round(season, 2) if season is not None else None,
            last5=round(last5, 2) if last5 is not None else None,
            form=round(last5 - season, 2) if last5 is not None and season is not None else None,
            hit=round((x['k'] - x['e']) / x['ta'], 3) if x['ta'] else None,
            ohit=round((x['ok'] - x['oe']) / x['ota'], 3) if x['ota'] else None,
            aps=round(x['aces'] / bs, 2) if bs else None, bps=round(x['blk'] / bs, 2) if bs else None,
            dps=round(x['dig'] / bs, 2) if bs else None, rank=(B.get(name) or {}).get('rank')))
    def tboard(key, rev=True, n=5, flt=lambda r: True):
        rows = [r for r in teamstats if r.get(key) is not None and flt(r)]
        return sorted(rows, key=lambda r: r[key], reverse=rev)[:n]
    tboards = [
        ('Hitting %', 'hit', tboard('hit')),
        ('Opp. hitting % (lowest)', 'ohit', tboard('ohit', rev=False)),
        ('Point margin / set', 'marg', tboard('marg')),
        ('Blocks / set', 'bps', tboard('bps')),
        ('Aces / set', 'aps', tboard('aps')),
        ('Digs / set', 'dps', tboard('dps')),
    ]
    streaks = sorted([r for r in teamstats if r['sk'] >= 3], key=lambda r: -r['sk'])[:8]
    top50 = lambda r: (r['rank'] or 999) <= 50
    hot = tboard('form', flt=top50, n=6)
    cold = tboard('form', rev=False, flt=top50, n=6)
    clutch = sorted([r for r in teamstats if sum(r['five']) >= 2], key=lambda r: (-(r['five'][0] - r['five'][1]), -r['five'][0]))[:6]
    comebacks = sorted([r for r in teamstats if r['comeback']], key=lambda r: -r['comeback'])[:6]
    closest = sorted([r for r in teamstats if sum(r['close']) >= 4], key=lambda r: -(r['close'][0] / float(sum(r['close']))))[:6]
    tm_payload = dict(boards=tboards, streaks=streaks, hot=hot, cold=cold, clutch=clutch, comebacks=comebacks,
                      closest=closest, n=len(teamstats))
    tm_names = set()
    for _, _, rows in tboards:
        tm_names |= {r['t'] for r in rows}
    for grp in (streaks, hot, cold, clutch, comebacks, closest):
        tm_names |= {r['t'] for r in grp}
    need = set(top25) | {p['t'] for p in players} | tm_names
    for r in base['res']:
        if (r['rw'] or 99) <= 25 or (r['rl'] or 99) <= 25:
            need |= {r['w'], r['l']}
    for u in base['up']:
        need |= {u['a'], u['h']}
    logos = {t: 'https://www.ncaa.com/sites/default/files/images/logos/schools/bgl/%s.svg' % seo[t]
             for t in sorted(need) if seo.get(t)}
    colors = {k: v.get('primary') for k, v in json.load(open('data/team_colors_2026.json'))['teams'].items() if k in need}

    base.update(tm=tm_payload, trend=trend, trend_days=trend_days, missing=missing, series=series, players=players, logos=logos, colors=colors)
    return base


def main():
    data = collect()
    html = open(TEMPLATE, encoding="utf-8").read()
    # "</" inside a JSON string could close the script element early
    blob = json.dumps(data).replace("</", "<\\/")
    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            + html.replace("__DATA__", blob) + "</html>")
    if not os.path.isdir(os.path.dirname(OUT)):
        print("no Cody/ directory (CI checkout) -- dashboard is local-only; skipping")
        return 0
    tmp = OUT + ".tmp"
    open(tmp, "w", encoding="utf-8").write(page)
    os.replace(tmp, OUT)
    print("wrote %s (%d KB, %d finals, through %s)"
          % (OUT, len(page) // 1024, data["nf"], data["stamp"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
