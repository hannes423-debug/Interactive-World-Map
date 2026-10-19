#!/usr/bin/env python3
"""Turn discovered participants into data/hockey/memberships-2026-27.json (dev-time tool).

* stable club ids (slugs) shared by every file that mentions the club,
* display names (English article title; Finnish titles as-is; Russian titles
  transliterated - correct them by hand in the output file if needed),
* country from the flag shown in the club's table row, else the league country,
* affiliations ONLY when the season table has a partner/affiliate column
  naming the partner (VHL/MHL "Партнёрская команда", AHL/ECHL "affiliate").

overrides.json (optional, next to this script) can rename clubs, force ids,
drop or add clubs: {"<league>": {"drop": [...], "add": [...], "names": {"<title>": "Name"}}}
Existing ids in the output are kept, so re-running does not renumber clubs.
"""
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import wiki  # noqa: E402
from fetch import slug  # noqa: E402  (shared slug rules)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "data", "hockey", "memberships-2026-27.json")

RU = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
              ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
               "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))
RU_FLAGS = {"россии": "RUS", "казахстана": "KAZ", "белоруссии": "BLR", "беларуси": "BLR", "китая": "CHN", "китайской": "CHN"}
FLAGICON = re.compile(r"\{\{\s*(?:flagicon|flag|flagcountry|fb|ice hockey)\s*\|\s*([A-Z]{3})", re.I)
RU_FLAG = re.compile(r"\{\{\s*Флаг\s+([А-Яа-яё]+)", re.I)
IOC = {"GER": "DEU", "SUI": "CHE", "DEN": "DNK", "LAT": "LVA", "SLO": "SVN", "CRO": "HRV", "NED": "NLD"}


def translit(s):
    out = []
    for ch in s:
        lo = ch.lower()
        if lo in RU:
            t = RU[lo]
            out.append(t.capitalize() if ch != lo and t else t)
        else:
            out.append(ch)
    return "".join(out)


def clean_title(t):
    return re.sub(r"\s*\((?:[^()]*hockey[^()]*|[^()]*хоккейн[^()]*|jääkiekko|ice hockey|men's ice hockey|Liiga)\)", "", t).strip()


def table_rows(text):
    """Yield (headers, cells) for every row of every table."""
    for tb in re.findall(r"\{\|.*?\n\|\}", text, re.S):
        parts = re.split(r"\n\|-[^\n]*", tb)
        hsrc = parts[0] if "\n!" in parts[0] else (parts[1] if len(parts) > 1 else "")
        hsrc = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", hsrc)   # links -> labels
        hsrc = re.sub(r"\{\{[^{}]*\}\}", "", hsrc)                       # templates
        head = re.findall(r"\n!\s*(?:[^|\n]*=[^|\n]*\|)?([^\n]*)", hsrc)
        headers = [re.sub(r"<[^>]+>|'''?", "", h).strip().lower() for h in head]
        for row in parts[1:]:
            cells = [c for c in re.split(r"\n\||\|\|", "\n" + row.strip()) if c.strip() and not c.strip().startswith("!")]
            yield headers, cells


def link_of(cell):
    m = re.search(r"\[\[([^\]|#]+)(?:\|([^\]]*))?\]\]", cell)
    return (m.group(1).strip(), (m.group(2) or m.group(1)).strip()) if m else (None, None)


def match_existing(name, by_name):
    """Club id of an already listed club with (nearly) the same name, else None."""
    from fetch import fold
    want = set(re.split(r"[^a-z0-9]+", fold(name))) - {"", "hc", "hk", "ec", "ehc", "sc", "if", "ik", "bk", "hockey", "club", "de", "ice"}
    best, score = None, 0.0
    for cid, n in by_name.items():
        have = set(re.split(r"[^a-z0-9]+", fold(n))) - {"", "hc", "hk", "ec", "ehc", "sc", "if", "ik", "bk", "hockey", "club", "de", "ice"}
        if not want or not have:
            continue
        j = len(want & have) / len(want | have)
        if j > score:
            best, score = cid, j
    return best if score >= 0.5 else None


def main():
    cfg = {l["id"]: l for l in json.load(open(os.path.join(HERE, "leagues.json")))["leagues"]}
    cands = json.load(open(os.path.join(HERE, "out", "members-candidates.json")))
    ov_path = os.path.join(HERE, "overrides.json")
    overrides = json.load(open(ov_path)) if os.path.exists(ov_path) else {}
    old = json.load(open(OUT)) if os.path.exists(OUT) else {"leagues": {}}
    known_ids = {}
    for lg in old["leagues"].values():
        for c in lg["clubs"]:
            known_ids[(c["wiki"], c["title"])] = c["id"]
    used = set(known_ids.values())
    result = {"season": "2026–27", "generated": date.today().isoformat(),
              "description": "Clubs taking part in each competition in 2026-27, from the cited season articles. "
                             "Affiliations are recorded only where the source table names a partner club.",
              "leagues": {}}
    title_to_id = {}
    pending_aff = []
    by_name = {}
    # competitions whose participants are clubs of other leagues are processed last
    order = sorted(cands, key=lambda l: cfg.get(l, {}).get("participantsFromLeagues", False))
    for lid in order:
        data = cands[lid]
        lg = cfg.get(lid, {})
        ov = overrides.get(lid, {})
        w = data["wiki"]
        _, text = wiki.raw(cfg[lid]["season"][1], w) if lid in cfg else (None, None)
        rows = list(table_rows(text or ""))
        clubs = []
        for t in data["teams"]:
            if t["title"] in ov.get("drop", []):
                continue
            row, headers, cell = None, [], ""
            for hdr, cells in rows:
                for c in cells[:4]:
                    l, _ = link_of(c)
                    if l and (l == t["link"] or l == t["title"]):
                        row, headers, cell = cells, hdr, c
                        break
                if row:
                    break
            country = lg.get("country")
            if row:
                # grid tables hold one club per cell (flag in that cell); others one club per row
                rtext = cell if (FLAGICON.search(cell) or RU_FLAG.search(cell)) else " ".join(row[:3])
                m = FLAGICON.search(rtext)
                if m:
                    country = IOC.get(m.group(1).upper(), m.group(1).upper())
                m = RU_FLAG.search(rtext)
                if m and m.group(1).lower() in RU_FLAGS:
                    country = RU_FLAGS[m.group(1).lower()]
            if w == "ru":
                # "Динамо (хоккейный клуб, Санкт-Петербург)" -> "Dinamo Sankt-Peterburg"
                short = re.sub(r"^ХК\s+", "", clean_title(t["title"]))
                city = re.search(r"\([^,()]*хоккейный клуб[^,()]*,\s*([^()]+)\)", t["title"])
                cname = city.group(1).strip() if city else ""
                name = translit(short + (" " + cname if cname and cname not in short else ""))
            else:
                name = clean_title(t["title"])
            name = ov.get("names", {}).get(t["title"], name)
            cid = known_ids.get((w, t["title"]))
            if not cid and lg.get("participantsFromLeagues"):
                cid = match_existing(name, by_name)
            if not cid:
                base = slug(name) or slug(translit(t["title"]))
                cid = base
                if cid in used:
                    cid = f"{base}-{lid}"
                n = 2
                while cid in used:
                    cid = f"{base}-{n}"; n += 1
            used.add(cid)
            by_name.setdefault(cid, name)
            title_to_id[(w, t["title"])] = cid
            title_to_id[(w, t["link"])] = cid
            club = {"id": cid, "name": name, "wiki": w, "title": t["title"], "country": country,
                    "article": wiki.page_url(t["title"], w)}
            if row and headers:
                for hi, h in enumerate(headers):
                    if re.search(r"партн|affiliat", h):
                        # data rows may have fewer cells when the first column uses rowspan
                        offset = len(headers) - len(row)
                        ci = hi - offset
                        if 0 <= ci < len(row):
                            pl, plabel = link_of(row[ci])
                            if pl:
                                pending_aff.append((club, w, pl, plabel, h))
            clubs.append(club)
        for extra in ov.get("add", []):
            clubs.append(extra)
        result["leagues"][lid] = {"source": data["source"], "sourceKind": "wikipedia-season-article",
                                  "note": lg.get("seasonNote"), "count": len(clubs), "clubs": clubs}
    # resolve affiliations to club ids where the partner is a known club
    aliases = {}
    for lid_, ov_ in overrides.items():
        if not isinstance(ov_, dict):
            continue
        for k, v in ov_.get("aliases", {}).items():
            aliases[k] = v
    for club, w, pl, plabel, h in pending_aff:
        target = title_to_id.get((w, pl))
        if not target:
            _, ptxt = wiki.raw(pl, w)
            tl, _ = wiki.raw(pl, w)
            target = title_to_id.get((w, tl)) or aliases.get(pl) or aliases.get(plabel)
        club.setdefault("affiliations", []).append(
            {"club": target, "name": plabel if not target else None, "relation": h, "source": "season article table"})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, "w"), indent=1, ensure_ascii=False)
    for lid, lg in result["leagues"].items():
        aff = sum(1 for c in lg["clubs"] if c.get("affiliations"))
        print(f"{lid:18s} {lg['count']:3d} clubs  {aff:3d} with affiliation")


if __name__ == "__main__":
    main()
