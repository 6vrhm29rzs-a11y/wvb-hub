#!/usr/bin/env python3
"""Build the local, frozen Nov 1 ballot dashboard. No crawl or rating writes."""
import collections
import datetime
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from gamelog import load_games_jsonl
from reconcile_2025 import norm

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'output' / 'opponent_adjusted_2026-11-01'
DEST = ROOT / 'Cody' / 'ballot-review-2026-11-01.html'

# Editorial judgments reproduce the ballot delivered to Cody. Numerical fields
# below are always read from computed research artifacts, never transcribed.
EDITORIAL = [
 ('Nebraska', 'The most complete case', 'Elite wins and sustained dominance. The narrow performance range backs up the unbeaten record; competitive four-set wins do not change the No. 1 case.', 'Clear No. 1', '', '', ''),
 ('Pittsburgh', 'Tested and close to full strength', 'BYU, Kentucky and Tennessee wins support second. The lone SMU loss is meaningful, but Babcock returned after her brief illness absence.', 'Returned', 'Olivia Babcock returned November 1 after illness. No ongoing absence deduction.', 'Pittsburgh Post-Gazette', 'https://www.post-gazette.com/sports/pitt/2026/11/01/olivia-babcock-pitt-nc-state/stories/202609170067'),
 ('Florida', 'Physicality backed by production', 'Cody’s physicality, serving and competitiveness assessment supports the statistical case. Wins over Kentucky, Tennessee and Minnesota give Florida the edge over Louisville; the Vanderbilt loss limits the rise.', 'Scouting input', 'Cody’s observation: physical, tough serving and difficult to beat in December. This is scouting context, not a quantified model adjustment.', '', ''),
 ('Louisville', 'Dominant, with a test still ahead', 'Excellent adjusted scoring and attacking, with a repeatable performance level. Wisconsin and Kentucky losses leave a gap in the elite-win case. Pitt and SMU remain the important tests.', 'Watch the next tests', 'Cody’s observation: cruising. Strong execution counts; the upper ACC matchups will say more about the ceiling.', '', ''),
 ('Kentucky', 'A promising lineup response', 'Louisville, Wisconsin and Penn State wins keep Kentucky high. The Texas A&M sweep loss and Tennessee loss are real concerns. Gaerte’s 19-kill Missouri match supports the new lineup without proving every issue solved.', 'Lineup change', 'Cody identified Gaerte moving outside with Watson at opposite. Reporting confirms a lineup reshuffle and Kentucky hitting .327 against Missouri’s .168. One match is encouraging evidence.', 'On3 / KSR', 'https://www.on3.com/sites/kentucky-wildcats/news/no-7-kentucky-vb-course-corrects-with-sweep-over-missouri/'),
 ('Wisconsin', 'Elite wins outweigh the model position', 'The hub’s toughest schedule and wins over Louisville and Florida justify a major upward editorial move. The USC win and verified UCLA sweep help, while the broad performance range explains the restraint.', 'Snapshot gap', 'Record includes the November 1 UCLA sweep. The adjusted model statistics do not include that match. No medical explanation is inferred from a player’s absence.', 'Big Ten results', 'https://bigten.org/schedule.aspx?schedule=17645'),
 ('SMU', 'Keep credit for the marquee wins', 'Pitt, Kentucky and Texas wins deserve more credit than model No. 11. Five consecutive victories show the replacement lineup is competing; Newsome’s injury limits confidence in moving SMU higher.', 'Availability watch', 'Natalia Newsome’s injury complicates comparison with the lineup that beat Pitt. No verified return date is assumed.', 'Independent injury reporting', 'https://sports.yahoo.com/articles/smu-volleyball-shows-fight-cant-210603314.html'),
 ('BYU', 'Good wins, still short of the top tier', 'Arizona State and Kansas are meaningful wins. There is still no win over this ballot’s top seven, and the saved SOS is No. 48. Eighth respects the season without treating the lighter schedule as championship proof.', 'Résumé restraint', 'Cody’s concern: the schedule and elite-win evidence do not yet support a top-five ballot. No automatic altitude or prior-year conference penalty is applied.', '', ''),
 ('Arizona St.', 'A high ceiling with costly outliers', 'Minnesota, Texas and Kansas wins support the top ten. UC Davis and West Virginia losses are the counterweight. BYU stays ahead on the head-to-head result and stronger consistency.', 'Volatility watch', '', '', ''),
 ('Penn St.', 'The recent wins earn the climb', 'Oregon, Washington and Purdue wins make a strong current case. The Oregon head-to-head and sustained improvement put Penn State ahead of the Ducks; Michigan State and UCLA losses still count.', 'Availability context', 'Jones’s earlier injury is context for the season. This ballot gives credit for results actually earned, with no assumed-return bonus.', '', ''),
 ('Vanderbilt', 'The Florida win carries weight', 'The Florida win and 16–3 record justify more credit than model No. 14. Missouri and Tennessee losses plus a wide performance range keep Vanderbilt outside the top ten.', 'High-value win', '', '', ''),
 ('Oregon', 'Reward the record; inspect the margins', 'Minnesota, Michigan State and Purdue wins are substantial. Adjusted attacking and scoring lag several teams with worse records, and losses to Wisconsin and Penn State matter. Recent sweeps help without erasing those differences.', 'Margin check', '', '', ''),
 ('Texas', 'The improvement has substance', 'A difficult schedule and wins over Wisconsin and Tennessee keep Texas high despite seven losses. Three consecutive sweeps support the upward trend; the Oklahoma sweep loss prevents a top-ten placement.', 'Long-term absence', 'Abby Vander Wal’s season-ending absence is already part of the lineup and results being evaluated. It is not another new deduction this week.', 'Availability reporting', 'https://sports.yahoo.com/articles/texas-volleyball-loses-key-offensive-001617346.html'),
 ('Kansas', 'Repeatable performance, fewer elite wins', 'TCU and Baylor wins plus a tight middle performance range make a strong case. The Florida State and Stanford losses, and limited elite-win evidence, hold Kansas below the model’s No. 10.', 'Snapshot gap', 'Corrected record includes the October 1 sweep of Utah, which is missing from the model. That match is shown below as verified context, with no invented adjusted performance.', 'KU Sports', 'https://www2.kusports.com/sports/college/volleyball/2026/oct/01/kansas-volleyball-sweeps-no-23-utah-for-9th-straight-win-remains-undefeated-in-conference-play/'),
 ('Minnesota', 'Strong attacking, uneven delivery', 'The attacking differential is excellent and Washington/UCLA wins help. A lower performance median and a broad range show that the strong average is not reproduced consistently. Illinois and Purdue losses constrain the rank.', 'Consistency watch', '', '', ''),
 ('Tennessee', 'Current availability changes the call', 'Kentucky, Penn State and Vanderbilt wins support a much higher season-long ceiling. A two-loss road weekend without Sutton changes the current-lineup assessment; the earlier wins still count.', 'Unavailable last weekend', 'Chelsea Sutton missed Texas A&M and Missouri after an injury against Vanderbilt. No return timetable is assumed. Missouri outblocked Tennessee 14–7.', 'On SI reporting', 'https://www.si.com/college/tennessee/volleyball/tennessee-volleyball-drops-five-set-match-to-mizzou-01m6cm1vjw87'),
 ('Purdue', 'Judge the lineup that is competing', 'SMU and Minnesota wins sustain the ranking. Creighton and TCU losses plus the latest Penn State loss limit it. The newly public explanation for Wollard’s season-long absence does not trigger a second deduction.', 'Season-long absence', 'Wollard’s medical update explains an absence already reflected in the season’s results. No return is assumed.', 'WLFI reporting', 'https://www.wlfi.com/2026/10/30/kenna-wollard-provides-health-update/'),
 ('TCU', 'The wins earn an editorial lift', 'SMU and Purdue wins are stronger résumé evidence than the model position suggests. Beating Baylor in five helps; earlier Baylor and Kansas sweep losses and weaker adjusted differentials keep TCU outside the top fifteen.', 'Résumé lift', '', '', ''),
 ('Washington', 'Dangerous, but the floor is lower', 'Wisconsin and Purdue wins establish the ceiling. Sweep losses to Indiana, Illinois and Minnesota make it difficult to rank the 17–4 record more aggressively.', 'Sweep-loss concern', '', '', ''),
 ('Texas A&M', 'Can beat the best; needs repeatability', 'Sweeping Kentucky and beating Tennessee are substantial. Nine losses, Arkansas and Oklahoma setbacks, and the latest Texas sweep loss cap the placement. The difficult schedule still deserves allowance.', 'Snapshot gap', 'Verified current record is 14–9. One win is missing from the statistical model; adjusted stats are left as computed rather than patched with an invented match.', 'KBTX', 'https://www.kbtx.com/2026/11/01/aggie-volleyball-swept-lone-star-showdown/'),
 ('Illinois', 'More quality wins than the record suggests', 'Minnesota, Michigan State and Washington wins make the case. The relatively compact middle range helps; Cincinnati and Michigan losses and the five-set Northwestern escape restrain the placement.', 'Quality wins', '', '', ''),
 ('Baylor', 'Competitive, without enough separation', 'The TCU sweep is the clearest win. A tight middle range points to a repeatable level, but the Houston, Kansas and TCU five-set stretch shows how little separation Baylor is creating.', 'Close-match watch', '', '', ''),
 ('North Carolina', 'Attacking warrants attention', 'Colorado State, Stanford and Georgia Tech wins count, but all took five sets. Kentucky and Vanderbilt losses restrain the rank. The strong adjusted hitting differential makes UNC a credible top-25 team.', 'Opponent context', 'Stanford lost setter Logan Parks during its UNC match. The win counts with that context attached; assists alone do not establish setting quality.', '', ''),
 ('Colorado St.', 'Dominance earns the place', 'The Colorado sweep and recent handling of league opponents earn a ballot spot. Saved SOS No. 78 limits how far the dominance carries. Stronger opponents away from home remain the important test.', 'Schedule context', 'No invented altitude deduction. Opponent quality is adjusted statistically; a causal altitude effect has not been established.', '', ''),
 ('Michigan St.', 'The least secure selection', 'Penn State and UCLA wins narrowly preserve a spot over Indiana. The reverse sweep, Waye’s injury, broad performance range and saved SOS No. 64 make this a substantial downward override from model No. 17.', 'Availability watch', 'Carmen Waye left the Indiana match injured and could not return to that match. A current return date is unverified.', 'The State News', 'https://statenews.com/article/2026/10/no-25-spartans-victim-of-reverse-sweep-in-consequential-loss?ct=content_open&cv=cbox_latest'),
]


def build():
    model = json.loads((RESEARCH/'results.json').read_text())
    games = json.loads((RESEARCH/'all_team_game_adjustments.json').read_text())
    power = json.loads((ROOT/'data'/'rating_2026.json').read_text())
    meta = {norm(t['team']):t for t in power['teams']}
    logos = json.loads((ROOT/'data'/'vb_logos.json').read_text())['teams']
    colors = json.loads((ROOT/'data'/'team_colors_2026.json').read_text())['teams']
    logos = {norm(k):v for k,v in logos.items()}
    colors = {norm(k):v for k,v in colors.items()}
    conferences = {norm(k):v for k,v in json.loads((ROOT/'data'/'raw'/'2026'/'conferences_2026.json').read_text())['teams'].items()}
    editorial = {norm(t[0]):dict(zip(['team','headline','reason','tag','context','source_title','source_url'],t)) for t in EDITORIAL}
    order = [norm(t[0]) for t in EDITORIAL]
    finalrank = {k:i+1 for i,k in enumerate(order)}
    epochs = {str(g['game_id']):g.get('start_time_epoch') for g in load_games_jsonl(str(ROOT/'data'/'raw'/'2026'/'games.jsonl'))}
    grouped = collections.defaultdict(list)
    for g in games:
        epoch = epochs.get(g['game_id'])
        date = datetime.datetime.fromtimestamp(int(epoch),ZoneInfo('America/Los_Angeles')).date().isoformat() if epoch else g['date']
        grouped[g['key']].append({
            'id':g['game_id'], 'date':date, 'opponent':g['opponent'], 'opp_key':norm(g['opponent']),
            'won':g['won'], 'score':g['match_score'], 'sets':g['set_scores'],
            'margin':g['raw_margin'], 'performance':g['adjusted_performance'],
            'points':g['stats']['points']['raw'], 'hitting':g['stats']['hitting']['raw'],
            'adj_hitting':g['stats']['hitting']['opponent_adjusted'],
            'counted':True})
    # Verified results outside the fitted snapshot are context, never fabricated ratings.
    # Wisconsin–UCLA is on the frozen site; the raw archive preserves its points.
    import season_counts as SC
    corr = SC.corrections(2026)
    raw = {str(g['game_id']):SC.apply_correction(g,corr) for g in load_games_jsonl(str(ROOT/'data'/'raw'/'2026'/'games.jsonl'))}
    if not any(g['id']=='6625961' for g in grouped[norm('Wisconsin')]):
        g = raw.get('6625961')
        if g and g.get('game_state')=='F':
            for side in g['teams']:
                k=norm(side['name_short'])
                opp=next(t for t in g['teams'] if t is not side)
                own,other=('home','visit') if side.get('is_home') else ('visit','home')
                sets=[[int(s[v]) if s.get(v) is not None else None for v in [own,other]] for s in g.get('linescores',[])]
                complete=sets and all(None not in pair for pair in sets)
                grouped[k].append({'id':'6625961','date':'2026-11-01','opponent':opp['name_short'],
                    'opp_key':norm(opp['name_short']),'won':k==norm('Wisconsin'),
                    'score':[side.get('sets_won'),opp.get('sets_won')], 'sets':sets,
                    'margin':sum(a-b for a,b in sets)/len(sets) if complete else None,
                    'performance':None,'points':None,'hitting':None,'adj_hitting':None,'counted':False})
    for k,opp,won,score,sets in [('Kansas','Utah',True,[3,0],[[32,30],[25,20],[26,24]]),('Utah','Kansas',False,[0,3],[[30,32],[20,25],[24,26]])]:
        if not any(g['date']=='2026-10-01' and g['opp_key']==norm(opp) for g in grouped[norm(k)]):
            grouped[norm(k)].append({'id':'verified-kansas-utah-20261001','date':'2026-10-01',
                'opponent':opp,'opp_key':norm(opp),'won':won,'score':score,'sets':sets,
                'margin':sum(a-b for a,b in sets)/3.,'performance':None,'points':None,
                'hitting':None,'adj_hitting':None,'counted':False})
    teams=[]
    boxlog={}
    for line in (ROOT/'data'/'raw'/'2026'/'boxscores.jsonl').open():
        b=json.loads(line); boxlog[str(b['game_id'])]=b
    swaps=SC.box_team_swaps(2026)
    avca=[]
    for line in (ROOT/'data'/'raw'/'2026'/'polls_avca.jsonl').open():
        poll=json.loads(line)
        if poll.get('season')!=2026 or poll.get('date','')>'2026-11-01':continue
        ranks={}
        for row in poll.get('rows',[]):
            school=re.sub(r'\s*\(\d+\)\s*$','',row.get('SCHOOL',''))
            school={'Penn State':'Penn St.','Arizona State':'Arizona St.','Michigan State':'Michigan St.','Colorado State':'Colorado St.'}.get(school,school)
            try:ranks[norm(school)]=int(row['RANK'])
            except (ValueError,KeyError):pass
        if not avca or avca[-1]['stamp']!=poll.get('stamp'):
            avca.append({'stamp':poll.get('stamp'),'date':poll.get('date'),'ranks':ranks})
    vt=[]
    for line in (ROOT/'Cody'/'data'/'vt_poll_2026.txt').read_text().splitlines():
        if line and line[0].isdigit():
            fields=line.split('|');vt.append((norm(fields[1]),int(fields[0])))
    vt=dict(vt)
    for t in model['ranking']:
        t=dict(t); k=t['key']; m=meta.get(k,{})
        t.update({'final_rank':finalrank.get(k),'conference':conferences.get(k) or m.get('conference') or '—',
                  'sos':m.get('sos_rank'),'editorial':editorial.get(k),
                  'color':colors.get(k,{}).get('primary','#386684'),
                  'logo':logos.get(k,{}).get('bgl'),
                  'games':sorted(grouped[k],key=lambda g:(g['date'],g['id']))})
        fixed={'Wisconsin':(16,6),'Kansas':(16,5),'Texas A&M':(14,9),'Utah':(12,9),'UCLA':(15,8)}
        if t['team'] in fixed:
            t['wins'],t['losses']=fixed[t['team']]
        t['stats_matches']=sum(g['counted'] for g in t['games'])
        for game in t['games']:
            rs=raw.get(game['id']); ownbox=oppbox=None
            if rs:
                ids={str(s['team_id']):norm(s['name_short']) for s in rs['teams']}
                for bt in boxlog.get(game['id'],{}).get('teams',[]):
                    tid=str(bt.get('team_id')); tid=swaps.get(game['id'],{}).get(tid,tid)
                    if ids.get(tid)==k:ownbox=bt.get('team_stats',{})
                    elif ids.get(tid)==game['opp_key']:oppbox=bt.get('team_stats',{})
            def counts(b):
                try:return [float(b[x]) for x in ['kills','attackErrors','attackAttempts']]
                except (KeyError,TypeError,ValueError):return None
            game['attack_counts']=counts(ownbox);game['opp_attack_counts']=counts(oppbox)
            sets=game['sets']; expected=sum(int(v) for v in game['score']) if all(v is not None for v in game['score']) else None
            complete=bool(sets) and len(sets)==expected and all(all(v is not None for v in pair) for pair in sets)
            if complete:
                complete=all(max(int(v) for v in pair)>=(15 if i==4 else 25) and abs(int(pair[0])-int(pair[1]))>=2 for i,pair in enumerate(sets))
                complete=complete and sum(int(p[0])>int(p[1]) for p in sets)==int(game['score'][0])
            game['rally_counts']=[sum(int(pair[i]) for pair in sets) for i in [0,1]]+[len(sets)] if complete else None
            game['margin']=(game['rally_counts'][0]-game['rally_counts'][1])/game['rally_counts'][2] if complete else None
            game['scores_complete']=bool(complete)
            if game['attack_counts'] and game['attack_counts'][2]:game['hitting']=(game['attack_counts'][0]-game['attack_counts'][1])/game['attack_counts'][2]
            game['opp_hitting']=(game['opp_attack_counts'][0]-game['opp_attack_counts'][1])/game['opp_attack_counts'][2] if game['opp_attack_counts'] and game['opp_attack_counts'][2] else None
        def aggregate(gs):
            rally=[g['rally_counts'] for g in gs if g['rally_counts']]; own=[g['attack_counts'] for g in gs if g['attack_counts']]; opp=[g['opp_attack_counts'] for g in gs if g['opp_attack_counts']]
            sums=lambda rows:[sum(r[i] for r in rows) for i in range(3)]
            pts=sums(rally);att=sums(own);oa=sums(opp)
            return {'pps_for':pts[0]/pts[2] if pts[2] else None,'pps_against':pts[1]/pts[2] if pts[2] else None,
                    'margin':(pts[0]-pts[1])/pts[2] if pts[2] else None,'hitting':(att[0]-att[1])/att[2] if att[2] else None,
                    'opp_hitting':(oa[0]-oa[1])/oa[2] if oa[2] else None,'scored_matches':len(rally),'box_matches':len(own),
                    'matches':len(gs),'sets':pts[2],'wins':sum(g['won'] for g in gs),'losses':sum(not g['won'] for g in gs)}
        t['actual']=aggregate(t['games']);t['recent_actual']=aggregate([g for g in t['games'] if g['date']>='2026-10-12'])
        t['avca_history']=[{'date':p['date'],'stamp':p['stamp'],'rank':p['ranks'].get(k)} for p in avca]
        t['vt_preseason']=vt.get(k)
        teams.append(t)
    doc={'season':2026,'through':'2026-11-01','order':order,'teams':teams,
         'first_out':[norm(n) for n in ['Indiana','Stanford','UCLA','Missouri','Utah']],
         'tests':model['tests'],'weights':model['weights'],
         'design':{'palette':{'court_blue':'#1356b8','ink':'#183349','floor':'#f1f6fa','teal':'#0d7d80','error':'#b64450','white':'#ffffff'},
                   'type':'Avenir Next for reading; condensed display for rank and team identity',
                   'layout':'Selectable ballot rail beside a team scouting sheet; comparison and league-wide plot on separate tabs',
                   'review':'Use court blue and school identities; avoid generic hero metrics, gradients, and decorative card grids'}}
    frozen=ROOT/'output'/'final_ballot_dashboard_2026-11-01.json'
    frozen.write_text(json.dumps(doc,separators=(',',':')))
    template=(ROOT/'scripts'/'ballot_review_template.html').read_text()
    encoded=json.dumps(doc,separators=(',',':')).replace('</','<\\/')
    DEST.write_text(template.replace('__BALLOT_DATA__',encoded))
    print('Built %s (%s bytes); %d teams, %d ballot entries.'%(DEST,DEST.stat().st_size,len(teams),len(order)))


if __name__=='__main__':
    build()
