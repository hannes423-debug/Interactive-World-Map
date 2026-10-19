"""Small, polite Wikimedia client used by the branding tools (dev-time only).

* Raw wikitext via index.php?action=raw (the action API is often rate limited
  from shared IPs, raw page reads are not).
* Wikidata via the public SPARQL endpoint.
* Commons originals via upload.wikimedia.org (path derived from the MD5 of
  the file name, the documented Commons storage layout).

Every response is cached in tools/branding/.cache/ so re-runs are cheap and
the sources are not hammered. Requests are spaced at least DELAY seconds.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE = os.path.join(ROOT, "tools", "branding", ".cache")
UA = ("CareerMapBranding/0.2 (https://github.com/hannes423-debug/Interactive-World-Map; "
      "asset provenance research)")
DELAY = 0.8
UPLOAD_DELAY = 8.0   # originals: be gentle, Wikimedia asks bulk users to prefer thumbnails
_last = [0.0]
_blocked_until = {}


class Blocked(Exception):
    """The host asked us to stop for a long time; callers record the item as pending."""


def _get(url, binary=False, accept=None):
    key = hashlib.sha1(url.encode()).hexdigest()
    path = os.path.join(CACHE, key[:2], key)
    meta = path + ".status"
    if os.path.exists(meta):
        status = int(open(meta).read())
        if status != 200:
            return status, None
        data = open(path, "rb").read()
        return 200, data if binary else data.decode("utf-8", "replace")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    host = urllib.parse.urlsplit(url).netloc
    if _blocked_until.get(host, 0) > time.time():
        raise Blocked(host)
    delay = UPLOAD_DELAY if host == "upload.wikimedia.org" else DELAY
    for attempt in range(5):
        wait = delay - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Accept": accept} if accept else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                status = r.status
            break
        except urllib.error.HTTPError as e:
            status, data = e.code, None
            ra = e.headers.get("Retry-After")
            if e.code == 429 and ra and ra.isdigit() and int(ra) > 60:
                import sys
                print(f"  [429] {host} asks for a {ra}s pause - marking downloads pending", file=sys.stderr, flush=True)
                _blocked_until[host] = time.time() + int(ra)
                raise Blocked(host)
            if e.code in (429, 503) and attempt < 4:
                import sys
                print(f"  [{e.code}] retry-after={ra} {url[:90]}", file=sys.stderr, flush=True)
                time.sleep(min(120, int(ra)) if ra and ra.isdigit() else 15 * (attempt + 1))
                continue
            break
        except (urllib.error.URLError, TimeoutError):
            if attempt < 4:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    if status in (200, 404):   # cache definitive answers only
        open(meta, "w").write(str(status))
        if data is not None:
            open(path, "wb").write(data)
    if status != 200:
        return status, None
    return status, data if binary else data.decode("utf-8", "replace")


def raw(title, wiki="en"):
    """Wikitext of a page, following #REDIRECT once. Returns (final_title, text) or (title, None)."""
    host = "commons.wikimedia.org" if wiki == "commons" else f"{wiki}.wikipedia.org"
    for _ in range(3):
        url = f"https://{host}/w/index.php?" + urllib.parse.urlencode({"title": title, "action": "raw"})
        status, text = _get(url)
        if text is None:
            return title, None
        low = text.lstrip()
        if low.startswith("#") and len(low) < 600 and "[[" in low.split("\n")[0]:
            import re
            m = re.search(r"\[\[([^\]|#]+)", low)
            if not m:
                return title, text
            title = m.group(1).strip()
            continue
        return title, text
    return title, None


def page_url(title, wiki="en"):
    host = "commons.wikimedia.org" if wiki == "commons" else f"{wiki}.wikipedia.org"
    return f"https://{host}/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def commons_file_url(name):
    name = name.replace(" ", "_")
    if name.lower().startswith("file:"):
        name = name[5:]
    name = name[0].upper() + name[1:]
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    return f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{urllib.parse.quote(name)}"


def download(url):
    return _get(url, binary=True)


def thumb_url(name, wiki_code="commons", width=250):
    """Standard-size thumbnail (PNG) of a file - for previews and comparisons."""
    import hashlib
    n = name.replace(" ", "_")
    if n.lower().startswith("file:"):
        n = n[5:]
    n = n[0].upper() + n[1:]
    h = hashlib.md5(n.encode("utf-8")).hexdigest()
    base = "commons" if wiki_code == "commons" else wiki_code
    suffix = ".png" if n.lower().endswith(".svg") else ""
    q = urllib.parse.quote(n)
    return f"https://upload.wikimedia.org/wikipedia/{base}/thumb/{h[0]}/{h[:2]}/{q}/{width}px-{q}{suffix}"


def sparql(query):
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": query, "format": "json"})
    status, text = _get(url, accept="application/sparql-results+json")
    if text is None:
        raise RuntimeError(f"SPARQL failed: HTTP {status}")
    return json.loads(text)["results"]["bindings"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def qid(title, lang):
    """Wikidata id of a Wikipedia article (via Special:ItemByTitle, not the query service)."""
    url = f"https://www.wikidata.org/wiki/Special:ItemByTitle/{lang}wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    key = hashlib.sha1(("qid:" + url).encode()).hexdigest()
    path = os.path.join(CACHE, key[:2], key + ".qid")
    if os.path.exists(path):
        return open(path).read() or None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    opener = urllib.request.build_opener(_NoRedirect)
    q = ""
    try:
        opener.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        import re
        m = re.search(r"/(Q\d+)$", loc)
        q = m.group(1) if m else ""
        if e.code == 429:
            raise RuntimeError("Rate limited by wikidata.org")
    open(path, "w").write(q)
    return q or None


def entity(q):
    status, text = _get(f"https://www.wikidata.org/wiki/Special:EntityData/{q}.json")
    if not text:
        return None
    return json.loads(text)["entities"].get(q) or next(iter(json.loads(text)["entities"].values()))


def claim_values(ent, prop):
    out = []
    for c in (ent or {}).get("claims", {}).get(prop, []):
        if c.get("rank") == "deprecated":
            continue
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            v = v["id"]
        out.append((v, c.get("rank"), c.get("qualifiers", {})))
    return out
