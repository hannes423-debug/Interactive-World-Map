#!/usr/bin/env python3
"""Acquire branding masters and write assets/branding/manifest.json (dev-time tool).

Entities come from:
  tools/branding/leagues.json + entities.json     leagues, countries (flags), national teams,
                                                  federations, IIHF and other tournaments
  data/hockey/memberships-2026-27.json            clubs taking part in 2026-27

For each entity:
  1. Current identity = the file in the logo/badge field of the entity's
     Wikipedia infobox (the logo the article shows today). For flags, the
     image_flag field of the country article.
  2. Rights are read from the file page. Commons files tagged public domain
     (e.g. PD-textlogo) or with a free licence may be published. Files hosted
     only on a local Wikipedia (non-free / fair-use logos, or "public domain
     in the US only") are not published.
  3. When the current file cannot be published, freely licensed files from
     Commons (tools/branding/out/commons-pool.json, built by commons_pool.py)
     whose names match the entity are compared visually with the current
     logo. A match above MATCH_SCORE becomes the published master; the
     identity record says it was matched visually and with what score.
  4. Otherwise the entity keeps its current (restricted) identity with no
     public master; the UI shows a fallback. --include-restricted stores such
     files under assets/branding/local/ (git-ignored) for local use only.

Usage
  python3 tools/branding/fetch.py [--include-restricted] [--only key-or-league,...] [--pending]

--pending retries only entities whose downloads were deferred because the file host throttled us.
"""
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import similarity  # noqa: E402
import wiki  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BRAND = os.path.join(ROOT, "assets", "branding")
MEMBERS = os.path.join(ROOT, "data", "hockey", "memberships-2026-27.json")
POOL = os.path.join(HERE, "out", "commons-pool.json")
SEASON = "2026–27"
TODAY = date.today().isoformat()
MATCH_SCORE = 0.80

FILE_FIELDS = r"(?:logo|badge|emblem|crest|logo_image|image_logo|logo_file|логотип|эмблема|tunnus|logotyp|znak|vereinslogo)"
PD = re.compile(r"\{\{\s*(PD-(?!ineligible-USonly)[A-Za-z0-9 _\-]+|CC0|Cc-zero)", re.I)
CC = re.compile(r"\{\{\s*(?:self\|)?(cc-by(?:-sa)?-[0-9.]+(?:-[a-z]+)?|GFDL[^}|]*|FAL)", re.I)
NONFREE = re.compile(r"\{\{\s*(non-free|logo\s*\||logo\s*\}|несвободн|обоснование|fair use)|\{\{\s*PD-ineligible-USonly|\{\{\s*PD-USonly", re.I)
STOP = {"hc", "hk", "ice", "hockey", "club", "team", "logo", "logos", "the", "of", "fc", "ec", "ehc", "sc", "ev", "ik", "if",
        "hf", "bk", "aik", "khl", "jr", "junior", "de", "la", "les", "svg", "png", "jpg", "new", "old", "primary", "secondary",
        "alternate", "national", "men", "mens", "ice-hockey", "hockey-club", "khk", "kh", "pro", "and", "est"}


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def slug(s):
    s = fold(s).replace("ø", "o").replace("æ", "ae").replace("ß", "ss").replace("ł", "l")
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def tokens(*names):
    out = set()
    for n in names:
        if not n:
            continue
        for t in re.split(r"[^a-z0-9]+", fold(n)):
            if len(t) >= 4 and t not in STOP:
                out.add(t)
    return out


def infobox_file(text, fields=FILE_FIELDS):
    found = _infobox_file(text, fields)
    if not found and fields == FILE_FIELDS:
        # generic infoboxes (e.g. Slovak "{{Infobox ... |obrázok=") have no logo field
        head = text[:4000]
        found = _infobox_file(head, r"(?:obrázok|obrazok|obrázek|image|kuva|bild)")
        # a generic image field often holds a photo: accept only files named as a logo/emblem
        if found and not re.search(r"logo|znak|emblem|erb|crest|badge|wappen|tunnus", found, re.I):
            found = None
        if not found:
            # hand-made infobox tables embed the logo as a plain file link
            m = re.search(r"\[\[(?:Súbor|Soubor|File|Image|Obrázok|Tiedosto|Файл):([^|\]]*(?:logo|znak|emblem|erb|crest)[^|\]]*\.(?:svg|png))", head, re.I)
            found = m.group(1).strip().replace("_", " ") if m else None
    return found


def _infobox_file(text, fields):
    for m in re.finditer(r"\|\s*" + fields + r"\s*=\s*([^\n|]*)", text, re.I):
        v = m.group(1).strip()
        v = re.sub(r"^\[\[(?:File|Image|Файл|Изображение|Tiedosto|Datei|Bild|Soubor|Fil):", "", v, flags=re.I).split("|")[0].strip("[] ")
        v = re.sub(r"^(?:File|Image|Файл|Изображение|Tiedosto|Datei|Bild|Soubor|Fil):", "", v, flags=re.I)
        if re.search(r"\.(svg|png|jpe?g|gif|webp)$", v, re.I):
            return v.replace("_", " ")
    return None


def file_rights(name, local_wikis):
    """(host, rights) for a file; host 'commons', a local wiki code, or None."""
    _, txt = wiki.raw("File:" + name, "commons")
    if txt:
        pd, cc = PD.findall(txt), CC.findall(txt)
        tm = bool(re.search(r"\{\{\s*trademark", txt, re.I))
        author = re.search(r"\|\s*author\s*=\s*([^\n]*)", txt, re.I)
        if pd:
            status, basis = "public_domain", "Wikimedia Commons tag {{%s}}" % pd[0].strip()
        elif cc:
            status, basis = "licensed", "Wikimedia Commons licence %s (attribution required)" % cc[0]
        else:
            status, basis = "unverified", "No recognised licence tag on the Commons file page"
        return "commons", {
            "status": status, "basis": basis, "trademark": True if tm else None,
            "author": re.sub(r"\[\[[^|\]]*\|?([^\]]*)\]\]", r"\1", author.group(1)).strip()[:160] if author else None,
            "publish": status in ("public_domain", "licensed"),
            "note": "Copyright status only. Logos remain trademarks of their owners; use does not imply endorsement."}
    for w in local_wikis:
        _, ltxt = wiki.raw("File:" + name, w)
        if ltxt:
            usonly = re.search(r"PD-(?:ineligible-)?USonly", ltxt, re.I)
            nonfree = NONFREE.search(ltxt)
            if usonly:
                st, basis = "unverified", f"{w}.wikipedia: public domain in the United States only; not cleared elsewhere"
            elif nonfree:
                st, basis = "restricted", f"Non-free (fair-use) file on {w}.wikipedia"
            else:
                st, basis = "unverified", f"Hosted only on {w}.wikipedia without a recognised licence"
            return w, {"status": st, "basis": basis, "publish": False,
                       "note": "Not redistributed: permission from the rights holder is required for a public release."}
    return None, None


def file_url(name, host):
    if host == "commons":
        return wiki.commons_file_url(name)
    import hashlib
    n = name.replace(" ", "_")
    n = n[0].upper() + n[1:]
    h = hashlib.md5(n.encode()).hexdigest()
    return f"https://upload.wikimedia.org/wikipedia/{host}/{h[0]}/{h[:2]}/{urllib.parse.quote(n)}"


_pool = None


def pool_candidates(entity, limit=4):
    global _pool
    if _pool is None:
        _pool = json.load(open(POOL)) if os.path.exists(POOL) else {}
    toks = tokens(entity.get("name"), entity.get("title"), *(entity.get("aliases") or []))
    if not toks:
        return []
    scored = []
    for f, cats in _pool.items():
        if not re.search(r"\.(svg|png)$", f, re.I):
            continue
        ft = fold(f + " " + " ".join(cats))
        if re.search(r"naisten|women|damen|dam|u20|u18|junior|nuoret", fold(f)) and not re.search(r"women|naisten|junior|u20|u18", fold(entity.get("name") or "")):
            continue
        hits = sum(1 for t in toks if t in ft)
        if hits and hits / len(toks) >= 0.66:
            scored.append((hits / len(toks), f.lower().endswith(".svg"), f))
    scored.sort(reverse=True)
    picked = [f for s, _, f in scored][:limit]
    # the entity's own Commons category often holds its logos
    from commons_pool import category
    for cat in [entity.get("title"), entity.get("name")]:
        if not cat or entity.get("wiki") not in ("en", None):
            continue
        for c in (cat, cat + " logos"):
            files, _ = category(c)
            for f in files:
                if re.search(r"logo|crest|emblem|badge|wappen", f, re.I) and re.search(r"\.(svg|png)$", f, re.I) and f not in picked:
                    picked.append(f)
    return picked[:limit + 2]


PENDING = object()   # download deferred because the file host is throttling us


THUMB_NOTE = {}   # file name -> width of the cached thumbnail used instead of the original


def fetch_bytes(name, host, allow_thumb=True):
    try:
        st, data = wiki.download(file_url(name, host))
    except wiki.Blocked:
        data = PENDING
    if data is PENDING and allow_thumb and host == "commons":
        w, tdata = wiki.cached_thumbnail(name)
        if tdata:
            THUMB_NOTE[name] = w
            return tdata
    return data


def fetch_thumb(name, host):
    """250 px PNG preview for visual comparison (falls back to the original for small files)."""
    try:
        st, data = wiki.download(wiki.thumb_url(name, host))
        if data is None:
            st, data = wiki.download(file_url(name, host))
    except wiki.Blocked:
        w, data = wiki.cached_thumbnail(name, host, sizes=(250, 330, 500, 120))
        return data if data else PENDING
    return data


def save_master(aid_tail, typ, name, data, local):
    if name in THUMB_NOTE:
        name = os.path.splitext(name)[0] + ".png"   # cached thumbnails are PNG renders
    folder = os.path.join(BRAND, "local" if local else "", "masters", typ + "s")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, aid_tail + os.path.splitext(name)[1].lower())
    open(path, "wb").write(data)
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def asset_record(aid, entity, name, host, rights, how, identity, master, local_master, alt=False):
    return {
        "id": aid, "name": entity["name"] + (" (alternate)" if alt else ""), "type": entity["type"],
        "entity": entity["key"], "related": entity.get("related", {}),
        "season": None if alt else entity.get("season", SEASON),
        "renderClass": entity["renderClass"],
        "master": master, "localMaster": local_master, "outputs": {},
        "source": {"kind": "wikimedia-commons" if host == "commons" else f"{host}.wikipedia", "file": name,
                   "page": wiki.page_url("File:" + name, "commons" if host == "commons" else host),
                   "url": file_url(name, host), "via": how},
        "acquired": TODAY if (master or local_master) else None,
        "identity": identity, "rights": rights, "technical": {"status": "unverified"},
        "notes": (f"Master is Wikimedia's {THUMB_NOTE[name]} px PNG rendering of the original file, taken from the "
                  "edge cache because original downloads were throttled. Replace with the original "
                  "(re-run fetch.py) for full resolution.") if name in THUMB_NOTE else None,
        **({"masterIsThumbnail": THUMB_NOTE[name]} if name in THUMB_NOTE else {}),
    }


def acquire(entity, include_restricted, assets, entities_map, log):
    etype, key = entity["type"], entity["key"]
    tail = entity["id"]
    wikis = [entity.get("wiki") or "en"] + (["en"] if entity.get("wiki") not in (None, "en") else [])
    # 1. current identity
    if etype == "flag":
        title, text = wiki.raw(entity["countryArticle"], "en")
        cur = infobox_file(text or "", r"image_flag")
    else:
        title, text = wiki.raw(entity["title"], entity["wiki"]) if entity.get("title") else (None, None)
        cur = infobox_file(text) if text else None
        art_wiki = entity.get("wiki", "en")
        if not cur and entity.get("title") and entity.get("wiki") not in (None, "en"):
            # home-language infobox has no logo: try the same article title on other Wikipedias
            for w in ("en", "de"):
                if w == entity["wiki"]:
                    continue
                t2, x2 = wiki.raw(re.sub(r"\s*\([^)]*\)$", "", entity["title"]), w)
                f2 = infobox_file(x2) if x2 and re.search(r"hockey|eishockey|hokej", x2[:4000], re.I) else None
                if f2 and not re.search(r"logo|crest|emblem|wappen|znak|badge", f2, re.I):
                    f2 = None
                if f2:
                    title, text, cur, art_wiki = t2, x2, f2, w
                    wikis = [w] + wikis
                    break
    article = wiki.page_url(title, "en" if etype == "flag" else (art_wiki if etype != "flag" else "en")) if text else None
    ids, active, status, pending = [], None, "missing", []
    ref_sig, ref_src = None, None
    if etype == "flag":
        active, status = flag_asset(entity, cur, article, assets, log)
        cur = None
    if cur:
        host, rights = file_rights(cur, wikis)
        if host:
            ident = {"status": "verified_secondary", "season": entity.get("season", SEASON),
                     "basis": f"File shown in the infobox of {article} on {TODAY}"}
            data = fetch_bytes(cur, host) if (rights["publish"] or include_restricted) else None
            ref_src = (cur, host)
            if data is PENDING:
                pending.append(cur)
                data = None
            aid = f"{etype}.{tail}"
            if rights["publish"] and data:
                assets[aid] = asset_record(aid, entity, cur, host, rights, "infobox", ident, save_master(tail, etype, cur, data, False), None)
                active, status = aid, "public"
                log.append(f"PUBLIC   {key}: {cur} [{rights['status']}]")
            elif rights["publish"]:
                assets[aid] = asset_record(aid, entity, cur, host, rights, "infobox", ident, None, None)
                assets[aid]["pendingDownload"] = True
                active, status = aid, "pending"
                log.append(f"PENDING  {key}: {cur} [{rights['status']}] download deferred")
            else:
                lm = save_master(tail, etype, cur, data, True) if (include_restricted and data) else None
                aid = f"{etype}.{tail}--current"
                assets[aid] = asset_record(aid, entity, cur, host, rights, "infobox", ident, None, lm)
                ids.append(aid)
                status = "restricted"
                log.append(f"RESTRICT {key}: {cur} [{rights['status']}]")
        else:
            log.append(f"NOFILE   {key}: infobox names {cur} but the file was not found")
    # 2. free alternative when the current file cannot be published
    if status not in ("public", "pending") and etype != "flag":
        best = None
        cands = pool_candidates(entity)
        if cands and ref_src:
            prev = fetch_thumb(*ref_src)
            if prev is PENDING:
                pending.append("reference preview")
                cands = []
            else:
                pimg = similarity.load(prev, "x.png") if prev else None
                ref_sig = similarity.signature(pimg) if pimg else None
        for f in cands:
            host, rights = file_rights(f, [])
            if host != "commons" or not rights["publish"]:
                continue
            prev = fetch_thumb(f, host)
            if prev is PENDING:
                pending.append(f)
                best = None
                break
            img = similarity.load(prev, "x.png") if prev else None
            if img is None:
                continue
            sc = similarity.score(ref_sig, similarity.signature(img)) if ref_sig else None
            cand = (sc if sc is not None else -1, f, None, rights)
            if best is None or cand[0] > best[0]:
                best = cand
        if best:
            sc, f, data, rights = best
            data = fetch_bytes(f, "commons")
            if data is PENDING or not data:
                log.append(f"{'PENDING ' if data is PENDING else 'DLFAIL  '} {key}: {f}")
                if data is PENDING:
                    pending.append(f)
                best = None
        if best:
            aid = f"{etype}.{tail}"
            if ref_sig is not None and sc >= MATCH_SCORE:
                ident = {"status": "verified_visual", "season": entity.get("season", SEASON), "score": sc,
                         "basis": f"Free Commons file visually matches the current infobox logo ({cur}), score {sc}"}
                assets[aid] = asset_record(aid, entity, f, "commons", rights, "commons-match", ident, save_master(tail, etype, f, data, False), None)
                active, status = aid, "public"
                log.append(f"MATCHED  {key}: {f} score {sc}")
            elif ref_sig is None and ref_src:
                # the current logo exists but could not be compared: do not guess by name
                pending.append("reference preview")
                log.append(f"PENDING  {key}: cannot compare {f} with the current logo yet")
            elif ref_sig is None:
                ident = {"status": "unverified", "season": None,
                         "basis": "No current logo found in the article; Commons file chosen by name only - check it"}
                assets[aid] = asset_record(aid, entity, f, "commons", rights, "commons-name", ident, save_master(tail, etype, f, data, False), None)
                active, status = aid, "public-unverified"
                log.append(f"NAMEONLY {key}: {f}")
            else:
                aid = f"{etype}.{tail}--older"
                ident = {"status": "not_current", "season": None, "score": sc,
                         "basis": f"Free Commons file differs from the current infobox logo ({cur}); probably an earlier identity"}
                assets[aid] = asset_record(aid, entity, f, "commons", rights, "commons-name", ident, save_master(tail, etype, f, data, False), None, alt=True)
                ids.append(aid)
                log.append(f"OLDER    {key}: {f} score {sc}")
    if active is None and ids and status == "restricted":
        active = ids[0]
    entities_map[key] = {"type": etype, "id": entity["id"], "name": entity["name"], "status": status,
                         "active": active, "alternates": [i for i in ids if i != active],
                         "article": article, "related": entity.get("related", {}),
                         "pending": pending or None}
    if status == "missing":
        log.append(f"MISSING  {key}")


NPM_FLAGS = os.path.join(HERE, ".cache", "npm", "svg-country-flags-1.2.10", "package")
ISO2 = {"FIN": "fi", "RUS": "ru", "USA": "us", "CAN": "ca", "SWE": "se", "CHE": "ch", "DEU": "de", "AUT": "at", "CZE": "cz",
        "SVK": "sk", "BLR": "by", "KAZ": "kz", "CHN": "cn", "LVA": "lv", "NOR": "no", "DNK": "dk", "FRA": "fr", "GBR": "gb",
        "ITA": "it", "SVN": "si", "HUN": "hu", "POL": "pl", "JPN": "jp", "KOR": "kr"}


def flag_asset(entity, infobox_name, article, assets, log):
    """Flags: public-domain SVGs from the npm package svg-country-flags 1.2.10 (taken from Wikipedia),
    cross-checked against the flag file named in the country article's infobox."""
    iso2 = ISO2.get(entity["related"]["country"])
    path = os.path.join(NPM_FLAGS, "svg", f"{iso2}.svg") if iso2 else None
    if not path or not os.path.exists(path):
        log.append(f"MISSING  {entity['key']}: no flag file")
        return None, "missing"
    data = open(path, "rb").read()
    aid = f"flag.{entity['id']}"
    rights = {"status": "public_domain", "publish": True, "trademark": None, "author": None,
              "basis": "National flag; SVG published as public domain (licence 'PD') in the npm package "
                       "svg-country-flags 1.2.10, whose files were taken from Wikipedia",
              "note": "Use of national flags can be restricted by national law (e.g. commercial use)."}
    ident = {"status": "verified_secondary", "season": None,
             "basis": f"Country article infobox ({article}) shows {infobox_name}; package file {iso2}.svg (2021 release)"
                      if infobox_name else "Country flag from the package; infobox flag not found"}
    master = save_master(entity["id"], "flag", f"{iso2}.svg", data, False)
    rec = asset_record(aid, entity, f"{iso2}.svg", "npm", rights, "npm:svg-country-flags", ident, master, None)
    rec["source"] = {"kind": "npm-package", "file": f"svg/{iso2}.svg", "package": "svg-country-flags@1.2.10",
                     "page": "https://www.npmjs.com/package/svg-country-flags",
                     "url": "https://registry.npmjs.org/svg-country-flags/-/svg-country-flags-1.2.10.tgz",
                     "upstream": "https://github.com/hjnilsson/country-flags", "via": "npm"}
    assets[aid] = rec
    log.append(f"PUBLIC   {entity['key']}: {iso2}.svg [public_domain] (npm svg-country-flags)")
    return aid, "public"


def ensure_npm_flags():
    if os.path.exists(NPM_FLAGS):
        return
    import io
    import tarfile
    import urllib.request
    data = urllib.request.urlopen("https://registry.npmjs.org/svg-country-flags/-/svg-country-flags-1.2.10.tgz", timeout=60).read()
    os.makedirs(os.path.dirname(NPM_FLAGS), exist_ok=True)
    tarfile.open(fileobj=io.BytesIO(data), mode="r:gz").extractall(os.path.dirname(NPM_FLAGS), filter="data")


def build_entities(only):
    cfg = json.load(open(os.path.join(HERE, "leagues.json")))
    ent = json.load(open(os.path.join(HERE, "entities.json")))
    out = []
    for lg in cfg["leagues"] + ent["extraLeagues"]:
        w, t = lg["article"]
        out.append({"key": f"league:{lg['id']}", "type": "league", "id": lg["id"], "name": lg.get("name", t), "wiki": w,
                    "title": t, "renderClass": "symbol", "related": {"country": lg.get("country")}})
    if os.path.exists(MEMBERS):
        for lid, lg in json.load(open(MEMBERS))["leagues"].items():
            for c in lg["clubs"]:
                out.append({"key": f"club:{c['id']}", "type": "club", "id": c["id"], "name": c["name"],
                            "wiki": c["wiki"], "title": c["title"], "renderClass": "crest",
                            "aliases": c.get("aliases"), "related": {"league": lid, "country": c.get("country")}})
    for c in ent["countries"]:
        out.append({"key": f"flag:{c['id']}", "type": "flag", "id": c["id"], "name": f"Flag of {c['name']}",
                    "countryArticle": c["article"], "renderClass": "flag", "season": None, "related": {"country": c["iso3"]}})
        w, t = c["nationalTeam"]
        out.append({"key": f"national-team:{c['id']}", "type": "national-team", "id": c["id"], "name": t, "wiki": w,
                    "title": t, "renderClass": "national-team", "related": {"country": c["iso3"]}})
        out.append({"key": f"federation:{c['id']}", "type": "federation", "id": c["id"], "name": None, "wiki": "en",
                    "title": None, "fromNationalTeam": t, "renderClass": "federation", "related": {"country": c["iso3"]}})
    for t in ent["international"]:
        w, a = t["article"]
        out.append({"key": f"{t['type']}:{t['id']}", "type": t["type"], "id": t["id"], "name": t["name"], "wiki": w,
                    "title": a, "season": t.get("season"), "renderClass": t["type"], "related": {}})
    seen, uniq = set(), []
    for e in out:   # a club in two competitions (e.g. SHL and CHL) is one entity
        if e["key"] not in seen:
            seen.add(e["key"]); uniq.append(e)
    out = uniq
    if only:
        out = [e for e in out if any(o == e["key"] or o == e.get("related", {}).get("league") or o == e["key"].split(":")[0] for o in only)]
    return out


def main():
    include_restricted = "--include-restricted" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else []
    mpath = os.path.join(BRAND, "manifest.json")
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {"assets": {}, "entities": {}}
    assets, entities_map = manifest["assets"], manifest["entities"]
    log = []
    ensure_npm_flags()
    todo = build_entities(only)
    if "--pending" in sys.argv:   # retry only entities whose downloads were deferred
        def needs(k):
            ent = entities_map.get(k, {})
            act = assets.get(ent.get("active") or "", {})
            return ent.get("pending") or ent.get("status") == "pending" or act.get("masterIsThumbnail")
        todo = [e for e in todo if needs(e["key"])]
        print(f"{len(todo)} entities with deferred downloads", flush=True)
    if "--missing" in sys.argv:   # retry entities for which no logo file was found
        todo = [e for e in todo if entities_map.get(e["key"], {}).get("status", "missing") == "missing"]
        print(f"{len(todo)} entities without a logo file", flush=True)
    touched = set()
    for e in todo:
        if e.get("fromNationalTeam"):
            _, txt = wiki.raw(e["fromNationalTeam"], "en")
            m = re.search(r"\|\s*association\s*=\s*\[\[([^\]|]+)(?:\|([^\]]*))?", txt or "", re.I)
            if not m:
                entities_map[e["key"]] = {"type": "federation", "id": e["id"], "name": None, "status": "missing",
                                          "active": None, "alternates": [], "related": e["related"]}
                log.append(f"MISSING  {e['key']}: no association in national team infobox")
                print(log[-1], flush=True)
                continue
            e["title"] = m.group(1).strip()
            e["name"] = e["title"]
        for aid in [a for a, v in assets.items() if v["entity"] == e["key"]]:
            del assets[aid]
        n = len(log)
        acquire(e, include_restricted, assets, entities_map, log)
        touched.add(e["key"])
        for line in log[n:]:
            print(line, flush=True)
        if len(touched) % 10 == 0:
            save(manifest, assets, entities_map, touched)
    save(manifest, assets, entities_map, touched)
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    open(os.path.join(HERE, "out", "fetch.log"), "a").write("\n".join(log) + "\n")


def save(manifest, assets, entities_map, touched=None):
    """Write the manifest. With `touched`, merge only those entities into the file on disk,
    so that a concurrent process.py run (outputs/technical fields) is not overwritten."""
    mpath = os.path.join(BRAND, "manifest.json")
    if touched is not None and os.path.exists(mpath):
        disk = json.load(open(mpath))
        for key in touched:
            for aid in [a for a, v in disk["assets"].items() if v["entity"] == key]:
                del disk["assets"][aid]
            for aid, v in assets.items():
                if v["entity"] == key:
                    disk["assets"][aid] = v
            if key in entities_map:
                disk["entities"][key] = entities_map[key]
        manifest, assets, entities_map = disk, disk["assets"], disk["entities"]
    manifest.update({"schema": 1, "season": SEASON, "generatedSizes": [128, 256, 512, 1024],
                     "description": "Branding manifest. 'assets' are keyed by stable asset id; 'entities' map "
                                    "league/club/flag/federation/national-team/tournament keys to the active asset for the "
                                    "season plus alternates. Assets whose rights do not allow publication have master=null; "
                                    "their local copies (if fetched with --include-restricted) are listed in "
                                    "assets/branding/local/manifest.local.json, which is git-ignored."})
    manifest["assets"] = dict(sorted(assets.items()))
    manifest["entities"] = dict(sorted(entities_map.items()))
    os.makedirs(BRAND, exist_ok=True)
    tmp = os.path.join(BRAND, "manifest.json.tmp")
    json.dump(manifest, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(BRAND, "manifest.json"))
    local = {a: {"master": v["localMaster"]} for a, v in assets.items() if v.get("localMaster")}
    if local:
        os.makedirs(os.path.join(BRAND, "local"), exist_ok=True)
        json.dump({"assets": local}, open(os.path.join(BRAND, "local", "manifest.local.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
