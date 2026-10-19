#!/usr/bin/env python3
"""Collect freely licensed hockey logo files from Wikimedia Commons categories.

Crawls "Ice hockey logos of <country>" (and their sub-categories, two levels)
through the normal category pages (not the rate-limited API) and writes
tools/branding/out/commons-pool.json: {file name: [categories]}.
"""
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
import wiki  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
COUNTRIES = ["Finland", "Russia", "the United States", "Canada", "Sweden", "Switzerland", "Germany", "Austria",
             "the Czech Republic", "Czechia", "Slovakia", "Belarus", "Kazakhstan", "China", "Latvia", "Norway", "Denmark",
             "France", "the United Kingdom", "Italy", "Slovenia", "Hungary", "Poland", "Japan", "South Korea"]
EXTRA = ["National Hockey League logos", "American Hockey League logos", "ECHL logos", "Kontinental Hockey League logos",
         "Logos of the Kontinental Hockey League", "Ice hockey logos", "Ice hockey team logos", "IIHF logos",
         "Logos of ice hockey leagues", "Logos of national ice hockey teams", "Ice hockey federations logos"]


def category(name):
    """Files and sub-categories of a Commons category, following 'next page' links."""
    files, subs = [], []
    url = "https://commons.wikimedia.org/wiki/Category:" + urllib.parse.quote(name.replace(" ", "_"))
    for _ in range(20):
        st, html = wiki._get(url)
        if not html:
            break
        files += [urllib.parse.unquote(f).replace("_", " ") for f in re.findall(r'class="galleryfilename[^"]*" href="/wiki/File:([^"?#]+)"', html)]
        if not files:
            files += [urllib.parse.unquote(f).replace("_", " ") for f in re.findall(r'href="/wiki/File:([^"?#]+)"', html)]
        block = html.split('id="mw-subcategories"', 1)
        if len(block) > 1:
            subs += [urllib.parse.unquote(s).replace("_", " ") for s in re.findall(r'href="/wiki/Category:([^"?#]+)"', block[1].split('id="mw-category-media"')[0])]
        nxt = re.search(r'href="([^"]*filefrom=[^"]*)"[^>]*>next page', html)
        if not nxt:
            break
        url = "https://commons.wikimedia.org" + nxt.group(1).replace("&amp;", "&")
    return sorted(set(files)), sorted(set(subs))


def main():
    pool = {}
    seen = set()
    queue = [(f"Ice hockey logos of {c}", 0) for c in COUNTRIES] + [(e, 0) for e in EXTRA]
    while queue:
        cat, depth = queue.pop(0)
        if cat in seen:
            continue
        seen.add(cat)
        files, subs = category(cat)
        for f in files:
            pool.setdefault(f, []).append(cat)
        if depth < 2:
            queue += [(s, depth + 1) for s in subs if re.search(r"logo|ice hockey|hockey", s, re.I)]
        print(f"{len(pool):6d} files  {cat}  (+{len(files)}, {len(subs)} subcats)", flush=True)
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    json.dump(pool, open(os.path.join(HERE, "out", "commons-pool.json"), "w"), indent=0, ensure_ascii=False)


if __name__ == "__main__":
    main()
