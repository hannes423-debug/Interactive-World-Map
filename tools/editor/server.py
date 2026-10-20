#!/usr/bin/env python3
"""Local server for the league editor and the live game view.

    python3 tools/editor/server.py --db /path/to/LeagueDatabase [--port 8765]

Serves the repository like any static server, with two differences:

  games/<id>/*.json   come from <db>/games/<id>/ when that folder exists, so the
                      game view always shows the database being edited
  db/...              files under <db>/ (uploaded logos live in <db>/logos/)

and a small API used by editor.html:

  GET  api/info                     database path, games, repo path
  GET  api/events                   server-sent events: reload, focus
  POST api/save    {game, files}    write leagues/teams/badges/... (old copies go to <db>/backups/)
  POST api/logo?game=&kind=&id=&ext=   raw image body -> <db>/logos/<game>/<kind>/<id>.<ext>
  POST api/focus   {hash}           tell game views to show a route
  POST api/new-game {id, from}      copy a game's data into a new one
  POST api/export  {game}           copy the game + its logos into the repo (for GitHub Pages)

Only listens on 127.0.0.1. Standard library only.
"""
import argparse
import datetime
import json
import mimetypes
import queue
import re
import shutil
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO = Path(__file__).resolve().parents[2]
DATA_FILES = {'game', 'territories', 'leagues', 'teams', 'badges', 'tournaments'}
LOGO_EXT = {'png', 'svg', 'webp', 'jpg', 'jpeg', 'gif'}
SAFE_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
KEEP_BACKUPS = 60

clients = []          # one queue per open game view / editor (server-sent events)
clients_lock = threading.Lock()


def broadcast(event, data=''):
    with clients_lock:
        for q in clients:
            q.put((event, data))


def seed(db):
    """First run: copy the repository's games into the database."""
    (db / 'games').mkdir(parents=True, exist_ok=True)
    (db / 'logos').mkdir(exist_ok=True)
    (db / 'backups').mkdir(exist_ok=True)
    for g in (REPO / 'games').iterdir():
        if g.is_dir() and not g.name.startswith('test-') and not (db / 'games' / g.name).exists():
            shutil.copytree(g, db / 'games' / g.name)
            print(f'seeded {g.name} from the repository')


class Handler(SimpleHTTPRequestHandler):
    db: Path = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(REPO), **kw)

    def log_message(self, fmt, *args):  # quiet: only API calls
        if '/api/' in self.path and 'events' not in self.path:
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    # ------------------------------------------------------------ files
    def translate_path(self, path):
        rel = unquote(urlparse(path).path).lstrip('/')
        parts = [p for p in rel.split('/') if p not in ('', '.', '..')]
        if parts[:1] == ['db']:
            return str(self.db.joinpath(*parts[1:]))
        if parts[:1] == ['games'] and len(parts) >= 3 and (self.db / 'games' / parts[1]).is_dir():
            return str(self.db.joinpath(*parts))
        return super().translate_path(path)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.endswith('/api/events'):
            return self.events()
        if url.path.endswith('/api/info'):
            games = sorted(p.name for p in (self.db / 'games').iterdir() if p.is_dir())
            titles = {}
            for g in games:
                try:
                    titles[g] = json.loads((self.db / 'games' / g / 'game.json').read_text('utf-8')).get('title', g)
                except (OSError, ValueError):
                    titles[g] = g
            return self.json({'db': str(self.db), 'repo': str(REPO), 'games': games, 'titles': titles})
        return super().do_GET()

    def events(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        q = queue.Queue()
        with clients_lock:
            clients.append(q)
        try:
            self.wfile.write(b': hello\n\n')
            self.wfile.flush()
            while True:
                try:
                    event, data = q.get(timeout=20)
                    self.wfile.write(f'event: {event}\ndata: {data}\n\n'.encode())
                except queue.Empty:
                    self.wfile.write(b': ping\n\n')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with clients_lock:
                clients.remove(q)

    # -------------------------------------------------------------- API
    def do_POST(self):
        url = urlparse(self.path)
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n)
        try:
            name = url.path.rsplit('/api/', 1)[-1]
            if name == 'save':
                return self.json(self.save(json.loads(body)))
            if name == 'logo':
                return self.json(self.logo(parse_qs(url.query), body))
            if name == 'focus':
                broadcast('focus', json.loads(body).get('hash', ''))
                return self.json({'ok': True})
            if name == 'new-game':
                return self.json(self.new_game(json.loads(body)))
            if name == 'export':
                return self.json(self.export(json.loads(body)))
            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as e:
            self.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)

    def game_dir(self, game):
        if not SAFE_ID.match(game or ''):
            raise ValueError(f'bad game id {game!r}')
        d = self.db / 'games' / game
        if not d.is_dir():
            raise ValueError(f'no game {game!r} in the database')
        return d

    def save(self, req):
        d = self.game_dir(req.get('game'))
        stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup = self.db / 'backups' / d.name / stamp
        written = []
        for fname, data in (req.get('files') or {}).items():
            if fname not in DATA_FILES:
                raise ValueError(f'not a data file: {fname}')
            target = d / f'{fname}.json'
            text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
            if target.exists():
                if target.read_text('utf-8') == text:
                    continue
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup / target.name)
            tmp = target.with_suffix('.json.tmp')
            tmp.write_text(text, 'utf-8')
            tmp.replace(target)
            written.append(fname)
        # keep the newest backups only
        old = sorted((self.db / 'backups' / d.name).glob('*')) if (self.db / 'backups' / d.name).exists() else []
        for p in old[:-KEEP_BACKUPS]:
            shutil.rmtree(p, ignore_errors=True)
        if written:
            broadcast('reload', d.name)
        return {'ok': True, 'written': written, 'backup': str(backup) if written else None}

    def logo(self, qs, body):
        game, kind, ident = (qs.get(k, [''])[0] for k in ('game', 'kind', 'id'))
        ext = qs.get('ext', ['png'])[0].lower()
        self.game_dir(game)
        if kind not in ('leagues', 'teams') or not SAFE_ID.match(ident) or ext not in LOGO_EXT:
            raise ValueError('bad logo request')
        if not body or len(body) > 8 * 1024 * 1024:
            raise ValueError('logo must be between 1 byte and 8 MB')
        folder = self.db / 'logos' / game / kind
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob(f'{ident}.*'):
            old.unlink()
        (folder / f'{ident}.{ext}').write_bytes(body)
        stamp = int(datetime.datetime.now().timestamp())
        # ?v= makes browsers fetch a replaced logo instead of a cached one
        return {'ok': True, 'path': f'db/logos/{game}/{kind}/{ident}.{ext}?v={stamp}'}

    def new_game(self, req):
        src = self.game_dir(req.get('from'))
        new = req.get('id', '')
        if not SAFE_ID.match(new) or (self.db / 'games' / new).exists():
            raise ValueError(f'game id {new!r} is taken or not valid (lowercase letters, digits, - and _)')
        shutil.copytree(src, self.db / 'games' / new)
        g = json.loads((self.db / 'games' / new / 'game.json').read_text('utf-8'))
        g['id'] = new
        g['title'] = req.get('title') or new
        (self.db / 'games' / new / 'game.json').write_text(json.dumps(g, ensure_ascii=False, indent=2) + '\n', 'utf-8')
        logos = self.db / 'logos' / src.name
        if logos.exists():
            shutil.copytree(logos, self.db / 'logos' / new, dirs_exist_ok=True)
            for f in (self.db / 'games' / new).glob('*.json'):
                f.write_text(f.read_text('utf-8').replace(f'db/logos/{src.name}/', f'db/logos/{new}/'), 'utf-8')
        return {'ok': True}

    def export(self, req):
        d = self.game_dir(req.get('game'))
        shutil.copytree(d, REPO / 'games' / d.name, dirs_exist_ok=True)
        logos = self.db / 'logos' / d.name
        if logos.exists():
            shutil.copytree(logos, REPO / 'db' / 'logos' / d.name, dirs_exist_ok=True)
        return {'ok': True, 'to': str(REPO / 'games' / d.name)}

    def json(self, obj, status=HTTPStatus.OK):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True, help='league database folder')
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    db = Path(a.db).expanduser().resolve()
    seed(db)
    Handler.db = db
    mimetypes.add_type('image/svg+xml', '.svg')
    mimetypes.add_type('text/javascript', '.js')
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    srv.daemon_threads = True
    print(f'League editor: http://127.0.0.1:{a.port}/editor.html   database: {db}')
    srv.serve_forever()


if __name__ == '__main__':
    main()
