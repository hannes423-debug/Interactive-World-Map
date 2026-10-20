#!/usr/bin/env python3
"""Fetch official 2026-27 regular-season schedules (dev-time tool).

Writes data/hockey/fixtures/2026-27/<league>.json for every league with a
working adapter below, plus index.json listing what is official and where it
came from. Only published fixtures are written: dates and start times are the
league's own. Leagues without an adapter (or whose source fails) get no file,
and the calendar falls back to a generated schedule that it labels as
simulated.

Every source club must resolve to a team in games/nhl13/teams.json (by name,
city or tools/fixtures/aliases.json); a league with an unresolved club is not
written, so a wrong team can never end up in a fixture.

Usage
  python3 tools/fixtures/fetch_fixtures.py [--only nhl,ahl,...] [--teams games/nhl13/teams.json]
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from html import unescape
import http.cookiejar
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'data', 'hockey', 'fixtures', '2026-27')
ALIASES = os.path.join(os.path.dirname(__file__), 'aliases.json')
UA = 'Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0 (Interactive-World-Map fixtures)'
SEASON = '2026-27'


# KHL-family sites redirect once to set a cookie before serving the page
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def get_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/json', 'Accept-Language': 'en,ru;q=0.8'})
    with OPENER.open(req, timeout=60) as r:
        return r.read().decode('utf-8', 'replace')


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode('utf-8')
    text = text.strip()
    if text.startswith('(') and text.endswith(')'):  # HockeyTech wraps some feeds in ( )
        text = text[1:-1]
    return json.loads(text)


def utc_iso(dt):
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def local_parts(dt_utc, tz):
    loc = dt_utc.astimezone(ZoneInfo(tz))
    return loc.strftime('%Y-%m-%d'), loc.strftime('%H:%M')


# ------------------------------------------------------------ adapters
# Each yields dicts: id, date (venue-local), time (venue-local HH:MM or None),
# start (UTC ISO or None), home, away (source club names, list of candidates).

NHL_CLUBS = ['ANA', 'BOS', 'BUF', 'CAR', 'CBJ', 'CGY', 'CHI', 'COL', 'DAL', 'DET', 'EDM', 'FLA', 'LAK', 'MIN', 'MTL', 'NJD',
             'NSH', 'NYI', 'NYR', 'OTT', 'PHI', 'PIT', 'SEA', 'SJS', 'STL', 'TBL', 'TOR', 'UTA', 'VAN', 'VGK', 'WPG', 'WSH']


def nhl():
    seen = {}
    for club in NHL_CLUBS:
        url = f'https://api-web.nhle.com/v1/club-schedule-season/{club}/20262027'
        for g in get_json(url)['games']:
            if g['gameType'] != 2 or g['id'] in seen:
                continue
            start = datetime.fromisoformat(g['startTimeUTC'].replace('Z', '+00:00'))
            d, t = local_parts(start, g.get('venueTimezone') or 'America/New_York')
            name = lambda s: [f"{s['placeName']['default']} {s['commonName']['default']}", s['commonName']['default'], s['abbrev']]
            seen[g['id']] = dict(id=str(g['id']), date=d, time=t, start=utc_iso(start), home=name(g['homeTeam']), away=name(g['awayTeam']))
    return list(seen.values()), {'name': 'NHL schedule (api-web.nhle.com)', 'url': 'https://www.nhl.com/schedule'}


HOCKEYTECH = {
    # league: (client_code, key, season_id, public schedule page)
    'ahl': ('ahl', '50c2cd9b5e18e390', 94, 'https://theahl.com/stats/schedule'),
    'echl': ('echl', '2c2b89ea7345cae8', 78, 'https://echl.com/stats/schedule'),
    'ohl': ('ohl', 'f1aa699db3d81487', 88, 'https://ontariohockeyleague.com/schedule'),
    'whl': ('whl', 'f1aa699db3d81487', 295, 'https://whl.ca/schedule'),
    'qmjhl': ('lhjmq', 'f1aa699db3d81487', 214, 'https://chl.ca/lhjmq/schedule'),
    'ushl': ('ushl', 'e828f89b243dc43f', 91, 'https://ushl.com/view#/schedule'),
}


def hockeytech(league):
    code, key, season, page = HOCKEYTECH[league]
    url = (f'https://lscluster.hockeytech.com/feed/index.php?feed=modulekit&view=schedule&season_id={season}'
           f'&key={key}&client_code={code}&fmt=json')
    games = []
    for g in get_json(url)['SiteKit']['Schedule']:
        tbd = g.get('time_tbd') == '1' or g.get('date_tbd') == '1'
        start = None if tbd else datetime.fromisoformat(g['GameDateISO8601'])
        games.append(dict(
            id=g['game_id'], date=g['date_played'],
            time=None if tbd else start.strftime('%H:%M'),
            start=None if tbd else utc_iso(start),
            home=[g['home_team_name'], f"{g['home_team_city']} {g['home_team_nickname']}", g['home_team_city'], g['home_team_code']],
            away=[g['visiting_team_name'], f"{g['visiting_team_city']} {g['visiting_team_nickname']}", g['visiting_team_city'], g['visiting_team_code']],
        ))
    return games, {'name': f'{league.upper()} official schedule (HockeyTech feed)', 'url': page}


def nl():
    games = []
    for g in get_json('https://www.nationalleague.ch/api/games'):
        if g['isExhibition']:
            continue
        start = datetime.fromisoformat(g['date'])
        d, t = local_parts(start, 'Europe/Zurich')
        games.append(dict(id=g['gameId'], date=d, time=t, start=utc_iso(start),
                          home=[g['homeTeamName'], g['homeTeamShortName']], away=[g['awayTeamName'], g['awayTeamShortName']]))
    return games, {'name': 'National League schedule (nationalleague.ch)', 'url': 'https://www.nationalleague.ch/en/games'}


def shl():
    url = ('https://www.shl.se/api/sports-v2/game-schedule?seasonUuid=ndcf81nlb3&seriesUuid=qQ9-bb0bzEWUk'
           '&gameTypeUuid=qQ9-af37Ti40B&gamePlace=all&played=all')
    games = []
    for g in get_json(url)['gameInfo']:
        start = datetime.fromisoformat(g['rawStartDateTime'].replace('Z', '+00:00'))
        d, t = local_parts(start, 'Europe/Stockholm')
        name = lambda s: [s['names'].get('long'), s['names'].get('full'), s['names'].get('short'), s['names'].get('code')]
        games.append(dict(id=g['uuid'], date=d, time=t, start=utc_iso(start), home=name(g['homeTeamInfo']), away=name(g['awayTeamInfo'])))
    return games, {'name': 'SHL game schedule (shl.se)', 'url': 'https://www.shl.se/game-schedule'}


def liiga():
    games = []
    for g in get_json('https://liiga.fi/api/v2/games?tournament=runkosarja&season=2027'):
        start = datetime.fromisoformat(g['start'].replace('Z', '+00:00'))
        d, t = local_parts(start, 'Europe/Helsinki')
        name = lambda s: [s['teamName'], s['teamId'].split(':')[-1]]
        games.append(dict(id=str(g['id']), date=d, time=t, start=utc_iso(start), home=name(g['homeTeam']), away=name(g['awayTeam'])))
    return games, {'name': 'Liiga regular-season schedule (liiga.fi)', 'url': 'https://liiga.fi/fi/ohjelma'}


RU_MONTHS = {m: i + 1 for i, m in enumerate(['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
                                               'сентября', 'октября', 'ноября', 'декабря'])}
MSK = 'Europe/Moscow'


def season_date(day, month):
    """Day + month of the 2026-27 season -> ISO date (Jul-Dec 2026, Jan-Jun 2027)."""
    return f'{2026 if month >= 7 else 2027}-{month:02d}-{day:02d}'


def vhl():
    # The VHL calendar page lists the whole regular season. Upcoming games carry a Moscow start
    # time; games already played show the score instead, so their time is not published there.
    page = 'https://www.vhlru.ru/calendar/'
    html = get_text(page)
    games = []
    for day in re.split(r'<div class="calendar-page__day"', html)[1:]:
        d, mon = re.search(r'calendar-page__day-date">\s*(\d+)\s+(\S+?)\s*<', day).groups()
        date = season_date(int(d), RU_MONTHS[mon.lower()])
        for m in re.split(r'<div class="calendar-page__match[ "]', day)[1:]:
            gid = re.search(r'online/(\d+)\.html', m).group(1)
            names = re.findall(r'calendar-page__match-team-name">\s*([^<]+?)\s*<', m)
            city = re.search(r'calendar-page__match-city">\s*([^<]+?)\s*<', m).group(1)
            t = re.search(r'calendar-page__match-date-time">\s*(\d\d:\d\d)', m)
            start = datetime.fromisoformat(f'{date}T{t.group(1)}').replace(tzinfo=ZoneInfo(MSK)) if t else None
            games.append(dict(id=gid, date=date, time=t and t.group(1), start=start and utc_iso(start),
                              home=[names[0], f'{names[0]} {city}'], away=[names[1]]))
    return games, {'name': 'VHL calendar (vhlru.ru)', 'url': page, 'timeZone': 'MSK',
                   'timeNote': 'Start times are Moscow time (MSK) as published; played games show no start time on the calendar.'}


def del2():
    page = 'https://www.del-2.org/spielplan/'
    html = get_text(page)
    games = []
    for day in re.split(r'<time datetime="', html)[1:]:
        date = day[:10]
        if not re.fullmatch(r'\d{4}-\d\d-\d\d', date):
            continue
        for row in re.split(r'<div class="games-row ', day)[1:]:
            gid = re.search(r'href="/spiel/[^"]*_(\d+)"', row)
            home = re.search(r'games-team-home[^"]*" title="([^"]+)"', row)
            away = re.search(r'games-team-away[^"]*" title="([^"]+)"', row)
            if not (gid and home and away):
                continue
            t = re.search(r'games-meta-time">\s*(\d\d:\d\d)', row)
            start = datetime.fromisoformat(f'{date}T{t.group(1)}').replace(tzinfo=ZoneInfo('Europe/Berlin')) if t else None
            games.append(dict(id=gid.group(1), date=date, time=t and t.group(1), start=start and utc_iso(start),
                              home=[unescape(home.group(1))], away=[unescape(away.group(1))]))
    return games, {'name': 'DEL2 Spielplan (del-2.org)', 'url': page}


def penny_del():
    base = 'https://www.penny-del.org/spiele/monat/'
    games = {}
    for month in ('september', 'oktober', 'november', 'dezember', 'januar', 'februar', 'maerz', 'april'):
        try:
            html = get_text(base + month)
        except urllib.error.HTTPError:
            continue
        for row in re.split(r'<td class="team-schedule__date">', html)[1:]:
            d = re.match(r'[^,<]*,\s*(\d\d)\.(\d\d)\.(\d{4})', row)
            names = re.findall(r'team-meta__name[^"]*">\s*<a[^>]*>\s*([^<]+?)\s*</a>', row)
            slugs = re.findall(r'href="/teams/([^/"]+)/', row)
            if not (d and len(names) >= 2):
                continue
            date = f'{d.group(3)}-{d.group(2)}-{d.group(1)}'
            # upcoming games have no match page yet: key them by date and clubs
            gid = re.search(r'/statistik/spieldetails/[^"]*_(\d+)"', row)
            gid = gid.group(1) if gid else f'{date}-{slugs[0]}-{slugs[1]}'
            t = re.search(r'team-schedule__time">\s*(\d\d:\d\d)', row)
            start = datetime.fromisoformat(f'{date}T{t.group(1)}').replace(tzinfo=ZoneInfo('Europe/Berlin')) if t else None
            games[gid] = dict(id=gid, date=date, time=t and t.group(1), start=start and utc_iso(start),
                                       home=[unescape(names[0])], away=[unescape(names[1])])
    return list(games.values()), {'name': 'PENNY DEL Spielplan (penny-del.org)', 'url': 'https://www.penny-del.org/spiele'}


def czech():
    # All 52 rounds on one page. Upcoming games show date and time; played games only the date.
    page = 'https://www.hokej.cz/tipsport-extraliga/zapasy?do=matchList-view-all'
    html = get_text(page)
    games = []
    for row in re.split(r'<tr data-href="/zapas/', html)[1:]:
        gid = re.match(r'(\d+)', row).group(1)
        names = re.findall(r'preview__name--long">\s*([^<]+?)\s*<', row)
        played = re.search(r'match-start-time">[^<\d]*(\d\d)\.\s*(\d\d)\.', row)
        upcoming = re.search(r'<div class="col-1_3">(\d\d)\.\s*(\d\d)\.</div>\s*<div class="col-1_3">([^<]*)</div>', row)
        dm = played or upcoming
        if len(names) < 2 or not dm:
            continue
        date = season_date(int(dm.group(1)), int(dm.group(2)))
        t = re.fullmatch(r'\s*(\d\d:\d\d)\s*', upcoming.group(3)) if upcoming else None
        start = datetime.fromisoformat(f'{date}T{t.group(1)}').replace(tzinfo=ZoneInfo('Europe/Prague')) if t else None
        games.append(dict(id=gid, date=date, time=t and t.group(1), start=start and utc_iso(start),
                          home=[unescape(names[0])], away=[unescape(names[1])]))
    return games, {'name': 'Tipsport extraliga zápasy (hokej.cz)', 'url': 'https://www.hokej.cz/tipsport-extraliga/zapasy',
                   'timeNote': 'Times are venue-local (CET) as published; played games show no start time on the schedule.'}


def mestis():
    page = 'https://mestis.fi/fi/ottelut/2026-2027/runkosarja/'
    html = get_text(page)
    games = []
    for row in re.split(r'<tr data-time="', html)[1:]:
        ymd = row[:8]
        m = re.search(r'runkosarja/(\d+)/">\s*(.+?)\s+-\s+(.+?)\s*</a>', row)
        if not (m and ymd.isdigit()):
            continue
        date = f'{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}'
        t = re.search(r'<td class="h-l">\s*(\d\d:\d\d)\s*</td>', row)
        start = datetime.fromisoformat(f'{date}T{t.group(1)}').replace(tzinfo=ZoneInfo('Europe/Helsinki')) if t else None
        games.append(dict(id=m.group(1), date=date, time=t and t.group(1), start=start and utc_iso(start),
                          home=[unescape(m.group(2))], away=[unescape(m.group(3))]))
    return games, {'name': 'Mestis runkosarja (mestis.fi)', 'url': page}


def icehl():
    # Feed behind the schedule widget on ice.hockey; league 1 = regular season. All venues are on CET.
    url = 'https://s3-eu-west-1.amazonaws.com/icehl.hokejovyzapis.cz/league-matches/2026/1.json'
    games = []
    for g in get_json(url)['matches']:
        start = datetime.fromisoformat(g['start_date']).replace(tzinfo=ZoneInfo('Europe/Vienna'))
        games.append(dict(id=str(g['id']), date=start.strftime('%Y-%m-%d'), time=start.strftime('%H:%M'), start=utc_iso(start),
                          home=[g['home']['name']], away=[g['guest']['name']]))
    return games, {'name': 'win2day ICE Hockey League schedule (ice.hockey)', 'url': 'https://www.ice.hockey/en/season/schedule'}


def khl():
    # www.khl.ru builds its calendar from /rest/calendar/list/, which returns the whole regular
    # season for the page's session. Times are Moscow time (the response labels them "мск").
    page = 'https://www.khl.ru/calendar/'
    sessid = re.search(r'"bitrix_sessid":"(\w+)"', get_text(page)).group(1)
    req = urllib.request.Request('https://www.khl.ru/rest/calendar/list/', data=f'sessid={sessid}'.encode(),
                                 headers={'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest',
                                          'Content-Type': 'application/x-www-form-urlencoded'})
    with OPENER.open(req, timeout=60) as r:
        data = json.loads(r.read().decode('utf-8'))['data']
    names = {k: v['NAME'] for k, v in data['TEAMS'].items()}
    games = []
    for day in data['GAMES']:
        for date, lst in (day.items() if isinstance(day, dict) else []):
            for g in lst or []:
                t = g.get('time_format') or None
                start = datetime.fromisoformat(f"{g['date']}T{t}").replace(tzinfo=ZoneInfo(MSK)) if t else None
                games.append(dict(id=str(g['id']), date=g['date'], time=t, start=start and utc_iso(start),
                                  home=[names[str(g['teama'])]], away=[names[str(g['teamb'])]]))
    return games, {'name': 'KHL calendar (khl.ru)', 'url': page, 'timeZone': 'MSK',
                   'timeNote': 'Start times are Moscow time (MSK) as published.'}


def next_payload(html):
    """Concatenated React Server Components payload of a Next.js page (self.__next_f.push chunks)."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    return ''.join(json.loads(f'"{c}"') for c in chunks)


def allsvenskan():
    # The match page embeds the whole season's game list in its server-rendered payload.
    page = 'https://hockeyallsvenskan.se/pages/matcher'
    text = next_payload(get_text(page))
    dec = json.JSONDecoder()
    found = {}
    for m in re.finditer(r'"games":\[', text):
        arr, _ = dec.raw_decode(text, m.end() - 1)
        for g in arr:
            if isinstance(g, dict) and g.get('gameType') == 'HA' and g.get('scheduledDateTime') and g.get('homeTeam'):
                found[g['id']] = g
    games = []
    for g in found.values():
        start = datetime.fromisoformat(g['scheduledDateTime'].replace('Z', '+00:00'))
        d, t = local_parts(start, 'Europe/Stockholm')
        games.append(dict(id=str(g['id']), date=d, time=t, start=utc_iso(start),
                          home=[g['homeTeam']['name'], g['homeTeam'].get('shortName')], away=[g['awayTeam']['name'], g['awayTeam'].get('shortName')]))
    return games, {'name': 'HockeyAllsvenskan matcher (hockeyallsvenskan.se)', 'url': page}


def slovakia():
    # Tipsport liga (Slovak top flight) on the federation's stats site: whole regular season on one page.
    page = 'https://www.hockeyslovakia.sk/sk/stats/results/1197/tipsport-liga'
    html = get_text(page)
    games = []
    for row in re.split(r'<tr class="fn-tap-row', html)[1:]:
        gid = re.search(r'tipsport-liga/match/(\d+)', row)
        names = re.findall(r'class="image-competitor-icon[^"]*"', row) and re.findall(r'title="([^"]+)" class="image-competitor-icon', row)
        d = re.search(r'match-date[^>]*>.*?(\d\d)\.(\d\d)\.(\d{4})', row, re.S)
        if not (gid and d and len(names) >= 2):
            continue
        date = f'{d.group(3)}-{d.group(2)}-{d.group(1)}'
        t = re.search(r'hover-hide[^"]*">\s*(\d\d:\d\d)\s*<', row)
        start = datetime.fromisoformat(f'{date}T{t.group(1)}').replace(tzinfo=ZoneInfo('Europe/Bratislava')) if t else None
        games.append(dict(id=gid.group(1), date=date, time=t and t.group(1), start=start and utc_iso(start),
                          home=[unescape(names[0])], away=[unescape(names[1])]))
    return games, {'name': 'Tipsport liga results & schedule (hockeyslovakia.sk)', 'url': page}


ADAPTERS = {'vhl': vhl, 'slovak-extraliga': slovakia, 'allsvenskan': allsvenskan, 'khl': khl, 'icehl': icehl, 'mestis': mestis, 'del2': del2, 'del': penny_del, 'czech-extraliga': czech, 'nhl': nhl, 'nl': nl, 'shl': shl, 'liiga': liiga, **{k: (lambda k=k: hockeytech(k)) for k in HOCKEYTECH}}


# ------------------------------------------------------------ club matching
CYR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя', ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p',
    'r', 's', 't', 'u', 'f', 'kh', 'ts', 'ch', 'sh', 'shch', '', 'y', '', 'e', 'yu', 'ya']))


def norm(s):
    s = ''.join(CYR.get(c, c) for c in (s or '').lower())
    s = re.sub(r'\([^)]*\)', ' ', (s or '').replace('œ', 'oe').replace('Œ', 'Oe'))  # "(OHL)" tags
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


class Matcher:
    def __init__(self, teams, league, aliases):
        self.all = teams
        self.teams = [t for t in teams if t['league'] == league]
        self.aliases = {norm(k): v for k, v in aliases.get(league, {}).items()}
        self.cache = {}

    def resolve(self, names):
        key = tuple(n for n in names if n)
        if key in self.cache:
            return self.cache[key]
        hit = self._resolve(key)
        self.cache[key] = hit
        return hit

    def _resolve(self, names):
        for n in names:
            if norm(n) in self.aliases:
                return self.aliases[norm(n)]
        for pool in (self.teams, self.all):  # exact name; other leagues' clubs for inter-league games
            for n in names:
                for t in pool:
                    if norm(n) == norm(t['name']):
                        return t['id']
        # best token overlap between any source name and our name
        best, score = None, 0.0
        for n in names:
            src = set(norm(n).split())
            for t in self.teams:
                ours = set(norm(t['name']).split())
                j = len(src & ours) / len(src | ours) if src | ours else 0
                if j > score:
                    best, score = t['id'], j
        return best if score >= 0.5 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only')
    ap.add_argument('--teams', default=os.path.join(ROOT, 'games', 'nhl13', 'teams.json'))
    args = ap.parse_args()
    teams = json.load(open(args.teams, encoding='utf-8'))['teams']
    aliases = json.load(open(ALIASES, encoding='utf-8')) if os.path.exists(ALIASES) else {}
    os.makedirs(OUT, exist_ok=True)
    index_path = os.path.join(OUT, 'index.json')
    index = json.load(open(index_path, encoding='utf-8')) if os.path.exists(index_path) else {'season': SEASON, 'leagues': {}}

    wanted = args.only.split(',') if args.only else list(ADAPTERS)
    failed = False
    for league in wanted:
        try:
            raw, source = ADAPTERS[league]()
        except Exception as err:  # network or format change: keep the previous file
            print(f'{league}: source failed ({err})', file=sys.stderr)
            failed = True
            continue
        if not raw:
            print(f'{league}: NOT written, the source returned no games', file=sys.stderr)
            failed = True
            continue
        m = Matcher(teams, league, aliases)
        unresolved = sorted({g[side][0] for g in raw for side in ('home', 'away') if not m.resolve(g[side])})
        if unresolved:
            print(f'{league}: NOT written, unresolved clubs: {unresolved}', file=sys.stderr)
            failed = True
            continue
        owners = {}
        for names, tid in m.cache.items():
            owners.setdefault(tid, set()).add(names[0])
        clash = {t: sorted(n) for t, n in owners.items() if len({norm(x) for x in n}) > 1}
        if clash:
            print(f'{league}: NOT written, several source clubs map to one team: {clash}', file=sys.stderr)
            failed = True
            continue
        raw.sort(key=lambda g: (g['date'], g['time'] or '99:99', g['id']))
        rows = [[g['id'], g['date'], g['time'], g['start'], m.resolve(g['home']), m.resolve(g['away'])] for g in raw]
        clubs = sorted({r[4] for r in rows} | {r[5] for r in rows})
        missing = sorted(t['id'] for t in m.teams if t['id'] not in clubs)
        doc = {
            'league': league, 'season': SEASON, 'phase': 'regular-season', 'status': 'official',
            'source': {**source, 'fetched': date.today().isoformat()},
            'note': 'Published fixtures: dates and venue-local start times as issued by the league. Results are not stored; the simulator produces them.',
            'columns': ['id', 'date', 'time', 'start', 'home', 'away'],
            'games': rows,
        }
        with open(os.path.join(OUT, f'{league}.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
        index['leagues'][league] = {'status': 'official', 'games': len(rows), 'clubs': len(clubs), 'first': rows[0][1], 'last': rows[-1][1],
                                    'source': doc['source']}
        note = f' (teams.json clubs absent from schedule: {missing})' if missing else ''
        print(f'{league}: {len(rows)} games, {len(clubs)} clubs, {rows[0][1]} → {rows[-1][1]}{note}')

    index['leagues'] = dict(sorted(index['leagues'].items()))
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
