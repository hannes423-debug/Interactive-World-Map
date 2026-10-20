#!/usr/bin/env python3
"""Download logos for teams and leagues into the league database (private use).

    python3 tools/editor/fetch_logos.py [--territories swe,fin,nor,dnk] [--leagues shl,liiga,...]
                                        [--game nhl13] [--server http://127.0.0.1:8765] [--force]

Needs the editor server running (tools/editor/launch.sh). For each team in the
given territories (and each given league) the best available logo is chosen:

  1. the logo shown on the club's article in its home-language Wikipedia
     (sv, fi, nb, da ...), then on English Wikipedia - SVG preferred, otherwise
     the largest original raster;
  2. the Wikidata logo image (P154) if neither article has one.

Files go to <db>/logos/<game>/{teams,leagues}/ through the server and the data
is saved through it, so an open editor and game view refresh by themselves.
Items that already have a logo are skipped unless --force. Standard library only.
These are full-quality originals, including non-free logos: keep them private.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data'))
from geocode_teams import UA  # noqa: E402

NATIVE = {'swe': 'sv', 'fin': 'fi', 'nor': 'nb', 'dnk': 'da', 'deu': 'de', 'che': 'de', 'aut': 'de', 'cze': 'cs',
          'svk': 'sk', 'rus': 'ru', 'blr': 'ru', 'kaz': 'ru', 'lva': 'lv', 'fra': 'fr', 'ita': 'it'}
LEAGUE_TERR = {'shl': 'swe', 'allsvenskan': 'swe', 'liiga': 'fin', 'mestis': 'fin'}
IMAGE_EXT = ('svg', 'png', 'webp', 'gif')


def get(url, data=None, ctype=None):
    headers = {'User-Agent': UA}
    if ctype:
        headers['Content-Type'] = ctype
    req = urllib.request.Request(url, data=data, headers=headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except OSError:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f'gave up on {url}')


def wiki(host, **params):
    params.update(format='json', formatversion=2)
    return json.loads(get(f'https://{host}/w/api.php?' + urllib.parse.urlencode(params)))


def page_info(host, title, lang):
    """Lead image (any licence) of an article, its Wikidata id and its title in another language."""
    d = wiki(host, action='query', titles=title, redirects=1, prop='pageimages|pageprops|langlinks',
             piprop='original|name', pilicense='any', ppprop='wikibase_item', lllang=lang)
    p = (d.get('query', {}).get('pages') or [{}])[0]
    return {
        'image': p.get('original'),
        'name': p.get('pageimage'),
        'qid': p.get('pageprops', {}).get('wikibase_item'),
        'native': (p.get('langlinks') or [{}])[0].get('title'),
    }


def usable(cand):
    """Logos only: no photos of arenas or players."""
    if not cand or not cand.get('image'):
        return False
    name = (cand.get('name') or '').lower()
    ext = name.rsplit('.', 1)[-1]
    return ext in IMAGE_EXT or (ext in ('jpg', 'jpeg') and 'logo' in name)


def best_logo(host, title, territory):
    lang = NATIVE.get(territory, 'en')
    found = []
    first = page_info(host, title, lang)
    qid = first['qid']
    home_host = host.split('.')[0]
    if lang != home_host and first['native']:
        found.append(page_info(f'{lang}.wikipedia.org', first['native'], 'en'))
    found.append(first)
    if home_host != 'en':
        en = wiki(host, action='query', titles=title, redirects=1, prop='langlinks', lllang='en', formatversion=2)
        en_title = ((en.get('query', {}).get('pages') or [{}])[0].get('langlinks') or [{}])[0].get('title')
        if en_title:
            found.append(page_info('en.wikipedia.org', en_title, 'en'))
    found = [c for c in found if usable(c)]
    svg = [c for c in found if c['name'].lower().endswith('.svg')]
    if svg:
        return svg[0]['image']['source'], 'svg'
    if found:
        c = max(found, key=lambda c: c['image'].get('width', 0))
        return c['image']['source'], c['name'].rsplit('.', 1)[-1].lower().replace('jpeg', 'jpg')
    if qid:
        ent = json.loads(get('https://www.wikidata.org/w/api.php?' + urllib.parse.urlencode(
            {'action': 'wbgetclaims', 'entity': qid, 'property': 'P154', 'format': 'json'})))
        for c in ent.get('claims', {}).get('P154', []):
            fname = c['mainsnak'].get('datavalue', {}).get('value')
            if fname:
                ext = fname.rsplit('.', 1)[-1].lower()
                return 'https://commons.wikimedia.org/wiki/Special:FilePath/' + urllib.parse.quote(fname), ext
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--territories', default='swe,fin,nor,dnk')
    ap.add_argument('--leagues', default='shl,allsvenskan,liiga,mestis')
    ap.add_argument('--game', default='nhl13')
    ap.add_argument('--server', default='http://127.0.0.1:8765')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    S = a.server.rstrip('/')
    teams_doc = json.loads(get(f'{S}/games/{a.game}/teams.json'))
    leagues_doc = json.loads(get(f'{S}/games/{a.game}/leagues.json'))
    league_src = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'branding', 'leagues.json'), encoding='utf-8'))
    league_article = {l['id']: l.get('article') for l in league_src['leagues']}

    jobs = []
    terrs = set(filter(None, a.territories.split(',')))
    for t in teams_doc['teams']:
        if t.get('territory') in terrs and t.get('article') and (a.force or not t.get('logo')):
            u = urllib.parse.urlparse(t['article'])
            title = urllib.parse.unquote(u.path.rsplit('/wiki/', 1)[1]).replace('_', ' ')
            jobs.append(('teams', t, u.netloc, title, t['territory']))
    for l in leagues_doc['leagues']:
        art = league_article.get(l['id'])
        if l['id'] in a.leagues.split(',') and art and (a.force or not l.get('logo')):
            jobs.append(('leagues', l, f'{art[0]}.wikipedia.org', art[1], LEAGUE_TERR.get(l['id'], 'en')))

    done, missing = 0, []
    for kind, item, host, title, terr in jobs:
        try:
            url, ext = best_logo(host, title, terr)
            if not url:
                missing.append(item['id'])
                continue
            data = get(url)
            q = urllib.parse.urlencode({'game': a.game, 'kind': kind, 'id': item['id'], 'ext': ext})
            r = json.loads(get(f'{S}/api/logo?{q}', data=data, ctype='application/octet-stream'))
            item['logo'] = r['path']
            done += 1
            print(f'{item["id"]:40s} {ext:4s} {len(data) // 1024:5d} KB  {urllib.parse.unquote(url.rsplit("/", 1)[-1])[:60]}')
        except Exception as e:  # keep going; report at the end
            print(f'{item["id"]}: {e}', file=sys.stderr)
            missing.append(item['id'])
        time.sleep(1.0)
    body = json.dumps({'game': a.game, 'files': {'teams': teams_doc, 'leagues': leagues_doc}}).encode()
    get(f'{S}/api/save', data=body, ctype='application/json')
    print(f'\n{done} logos saved; none found for: {", ".join(missing) or "-"}')


if __name__ == '__main__':
    main()
