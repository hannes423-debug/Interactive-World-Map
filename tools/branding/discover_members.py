#!/usr/bin/env python3
"""Find each competition's 2026-27 participants (dev-time tool).

For every league in leagues.json:
  1. read the season article (or the league article when no season article exists),
  2. take the first link of the first cells of every row in the team tables,
  3. keep links whose article carries an ice-hockey club/team infobox.

Writes tools/branding/out/members-candidates.json for review. The reviewed
result is data/hockey/memberships-2026-27.json (see curate_members.py).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import wiki  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD = re.compile(r"team|club|participa|joukkue|участ|команд|mannschaft|teilnehm|\blag\b|týmy|tímy|kluby|klubb|clubs|vereine|composition|состав", re.I)
NOT_LINK = re.compile(r"^(file|image|tiedosto|файл|datei|soubor|súbor|bild|fil|kategori|category|категория|wp|wikipedia|:)\s*:?", re.I)
NOT_TEAM_TITLE = re.compile(r"division|conference|конференц|дивизион|divisioona|konferenz|liga\b|league\b|season|kausi|сезон|saison|säsong|sezóna|arena|areena|halle|hall\b|стадион|арена|дворец|stadion", re.I)
TEAM_INFOBOX = re.compile(r"\{\{\s*(infobox[ _][^|}\n]*(?:team|club|klub|joukkue|seura|verein)|infobox[ _]ice[ _]hockey[ _](?:team|club)|infobox[ _]hockey[ _]team|jääkiekkoseura|jääkiekkojoukkue|"
                          r"хоккейный[ _]клуб|карточка[ _]хоккейного[ _]клуба|infobox[ _]eishockeyclub|infobox[ _]eishockeyverein|"
                          r"faktamall[ _]ishockeyklubb|infobox[ _]-[ _]hokejový[ _]klub|infobox[ _]hokejový[ _]klub|infobox[ _]klub|"
                          r"lagfakta|pro[ _]hockey[ _]team|infobox[ _]sports[ _]team|infobox[ _]club|ishockeyklubb|eishockeyverein|hokejový[ _]klub)", re.I)


def row_links(text, grid=False):
    secs = re.split(r"\n(==+)\s*([^=\n]+?)\s*\1[ \t]*(?=\n)", "\n" + text)
    chunks = [secs[i + 2] for i in range(1, len(secs) - 2, 3) if HEAD.search(secs[i + 1])]
    if not chunks or not any("{|" in c for c in chunks):
        chunks = [text]
    out = []
    for ch in chunks:
        for tb in re.findall(r"\{\|.*?\n\|\}", ch, re.S):
            for row in re.split(r"\n\|-[^\n]*", tb)[1:]:
                cells = [c for c in re.split(r"\n[|!]|\|\||!!", "\n" + row.strip()) if c.strip()]
                for c in cells[:4]:
                    # a cell may start with attributes: style=... | content
                    if "|" in c and "[[" not in c.split("|")[0] and "=" in c.split("|")[0]:
                        c = c.split("|", 1)[1]
                    links = [l for l in re.findall(r"\[\[([^\]|#]+)(?:\|([^\]]*))?\]\]", c)
                             if not NOT_LINK.match(l[0].strip()) and not NOT_TEAM_TITLE.search(l[0])]
                    if links:
                        t = links[0][0].strip()
                        if t not in [o["link"] for o in out]:
                            out.append({"link": t, "label": (links[0][1] or t).strip()})
                        if not grid:
                            break   # one club per row: the first linked cell
    return out


def main():
    cfg = json.load(open(os.path.join(HERE, "leagues.json")))
    only = sys.argv[1:]
    path = os.path.join(HERE, "out", "members-candidates.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    res = json.load(open(path)) if os.path.exists(path) else {}
    for lg in cfg["leagues"]:
        if only and lg["id"] not in only:
            continue
        w, t = lg["season"]
        title, text = wiki.raw(t, w)
        if not text:
            print(f"{lg['id']:18s} no article {w}:{t}", flush=True)
            continue
        teams, rejected = [], []
        for cand in row_links(text, lg.get("layout") == "grid"):
            at, atext = wiki.raw(cand["link"], w)
            generic = atext and re.search(r"\{\{\s*infobox\s*[\n|]|class=\"infobox", atext[:1500], re.I) and re.search(r"hokej|hockey|liga", atext[:3000], re.I)
            if atext and (TEAM_INFOBOX.search(atext) or generic):
                if at not in [x["title"] for x in teams]:
                    teams.append({"title": at, "label": cand["label"], "link": cand["link"]})
            else:
                rejected.append(cand["link"])
        res[lg["id"]] = {"source": wiki.page_url(title, w), "wiki": w, "teams": teams, "rejected": rejected}
        print(f"{lg['id']:18s} {len(teams):3d}  " + ", ".join(x['title'] for x in teams)[:700], flush=True)
        if rejected:
            print("   rejected: " + ", ".join(rejected)[:300], flush=True)
        json.dump(res, open(path, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
