#!/usr/bin/env python3
"""Give every team a home city and [lon, lat] from Wikidata.

    python3 tools/data/geocode_teams.py <path/to/teams.json> [--force]

For each team with an `article` (Wikipedia URL) the Wikidata item is looked up
and its city is taken from, in order: headquarters location (P159), the home
venue's (P115) administrative location (P131), the team's own P131. The city's
coordinates become `lonlat`; when only the venue has coordinates those are used.
Teams that already have `lonlat` are skipped unless --force. Standard library only.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

UA = 'Interactive-World-Map-editor/1.0 (https://github.com/hannes423-debug/Interactive-World-Map)'


def get(url, accept='application/json'):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # network hiccup or throttling
            print('  retry', attempt + 1, e, file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(url)


def qids_for(titles, host='en.wikipedia.org'):
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        q = urllib.parse.urlencode({'action': 'query', 'titles': '|'.join(chunk), 'prop': 'pageprops',
                                    'ppprop': 'wikibase_item', 'redirects': 1, 'format': 'json'})
        d = get(f'https://{host}/w/api.php?' + q)['query']
        alias = {}
        for n in d.get('normalized', []) + d.get('redirects', []):
            alias[n['to']] = alias.get(n['from'], n['from'])
        for p in d.get('pages', {}).values():
            qid = p.get('pageprops', {}).get('wikibase_item')
            if not qid:
                continue
            t = p['title']
            out[t] = qid
            # map back through normalisation / redirects to the requested title
            while t in alias:
                t = alias[t]
                out[t] = qid
        time.sleep(0.5)
    return out


def entities(ids):
    """Claims and English labels for Wikidata items, 50 per request."""
    out = {}
    ids = sorted(set(ids) - {None})
    for i in range(0, len(ids), 50):
        q = urllib.parse.urlencode({'action': 'wbgetentities', 'ids': '|'.join(ids[i:i + 50]),
                                    'props': 'claims|labels', 'languages': 'en', 'format': 'json'})
        out.update(get('https://www.wikidata.org/w/api.php?' + q).get('entities', {}))
        time.sleep(0.5)
    return out


def claim(ent, prop):
    """First value of a property: an item id, or [lon, lat] for coordinates."""
    for c in (ent or {}).get('claims', {}).get(prop, []):
        v = c.get('mainsnak', {}).get('datavalue', {}).get('value')
        if isinstance(v, dict) and 'id' in v:
            return v['id']
        if isinstance(v, dict) and 'latitude' in v:
            return [round(v['longitude'], 4), round(v['latitude'], 4)]
    return None


def label(ent):
    return (ent or {}).get('labels', {}).get('en', {}).get('value')


ISO2 = {'RUS': 'RU', 'USA': 'US', 'CAN': 'CA', 'SWE': 'SE', 'DEU': 'DE', 'FIN': 'FI', 'CHE': 'CH', 'CZE': 'CZ',
        'AUT': 'AT', 'SVK': 'SK', 'BLR': 'BY', 'KAZ': 'KZ', 'CHN': 'CN', 'NOR': 'NO', 'FRA': 'FR', 'DNK': 'DK',
        'POL': 'PL', 'ITA': 'IT', 'SVN': 'SI', 'HUN': 'HU', 'GBR': 'GB', 'LVA': 'LV', 'JPN': 'JP', 'KOR': 'KR'}
NOISE = {'hc', 'hk', 'if', 'ik', 'sk', 'ec', 'ev', 'ehc', 'sc', 'aik', 'hockey', 'club', 'team', 'the', 'de', 'tc',
         'hockeyclub', 'lakers', 'hf', 'bk', 'is', 'ehv', 'eishockey', 'mhl', 'junior', 'jr'}


def country_of(team):
    g = str(team.get('geo') or '')
    return g[:2] if '-' in g else ISO2.get(g)


def guess_from_name(team):
    """Fallback: geocode the city field, else words of the team name, inside the team's country.

    Only places with 20 000+ inhabitants count, so a club name never lands on a hamlet."""
    cc = country_of(team)
    words = [w for w in team['name'].replace('-', ' ').replace('/', ' ').split() if w.lower().strip('.') not in NOISE]
    tries = [team['city']] if team.get('city') else []
    tries += [' '.join(words[i:i + 2]) for i in range(len(words) - 1)] + words
    for name in tries:
        if len(name) < 3:
            continue
        q = urllib.parse.urlencode({'name': name, 'count': 5, 'language': 'en', **({'countryCode': cc} if cc else {})})
        for r in get('https://geocoding-api.open-meteo.com/v1/search?' + q).get('results', []) or []:
            if (r.get('population') or 0) >= 20000 and (not cc or r.get('country_code') == cc):
                return r['name'], [round(r['longitude'], 4), round(r['latitude'], 4)]
        time.sleep(0.2)
    return None, None


def main():
    path = sys.argv[1]
    force = '--force' in sys.argv
    doc = json.load(open(path, encoding='utf-8'))
    teams = [t for t in doc['teams'] if t.get('article') and (force or not t.get('lonlat'))]
    title = lambda t: urllib.parse.unquote(t['article'].rsplit('/wiki/', 1)[1]).replace('_', ' ')
    host = lambda t: urllib.parse.urlparse(t['article']).netloc
    qmap = {}
    for h in sorted({host(t) for t in teams}):
        qmap[h] = qids_for(sorted({title(t) for t in teams if host(t) == h}), h)
    byq = {}
    for t in teams:
        q = qmap[host(t)].get(title(t))
        if q:
            byq.setdefault(q, []).append(t)
    team_ents = entities(byq)
    venues = {q: claim(e, 'P115') for q, e in team_ents.items()}
    venue_ents = entities(venues.values())
    city_of = {}
    for q, e in team_ents.items():
        # city: headquarters, else the home venue's location, else the team's own location
        city_of[q] = claim(e, 'P159') or claim(venue_ents.get(venues[q]), 'P131') or claim(e, 'P131')
    city_ents = entities(city_of.values())
    found = 0
    for q, ts in byq.items():
        city = city_ents.get(city_of.get(q))
        lonlat = claim(city, 'P625') or claim(venue_ents.get(venues.get(q)), 'P625')
        for t in ts:
            if lonlat:
                t['lonlat'] = lonlat
                found += 1
            if label(city) and not t.get('city'):
                t['city'] = label(city)
    for t in doc['teams']:
        if t.get('lonlat'):
            continue
        city, lonlat = guess_from_name(t)
        if lonlat:
            t['lonlat'] = lonlat
            t['city'] = t.get('city') or city
            t['placeNote'] = 'guessed from the team name - check'
            found += 1
    json.dump(doc, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    missing = [t['id'] for t in doc['teams'] if not t.get('lonlat')]
    print(f'{found} teams located, {len(missing)} without coordinates:', ', '.join(missing))


if __name__ == '__main__':
    main()
