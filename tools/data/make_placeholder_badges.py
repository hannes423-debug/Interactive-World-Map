#!/usr/bin/env python3
"""Generate clearly-marked placeholder league badges.

Writes assets/badges/placeholder/<league id>.svg for every league in
games/<game>/leagues.json. These are NOT league logos: each one carries the
league's short name and a "PLACEHOLDER" label. To use a real logo, set the
league's "logo" field (or the badge's "image" field) to the real file; the
placeholder is then ignored.

Usage: python3 tools/data/make_placeholder_badges.py [game]   (default nhl13)
"""
import json
import os
import sys
from xml.sax.saxutils import escape

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
game = sys.argv[1] if len(sys.argv) > 1 else "nhl13"
leagues = json.load(open(os.path.join(ROOT, "games", game, "leagues.json")))["leagues"]
out = os.path.join(ROOT, "assets", "badges", "placeholder")
os.makedirs(out, exist_ok=True)

for lg in leagues:
    short = lg["shortName"]
    size = 30 if len(short) <= 3 else 24 if len(short) <= 4 else 19
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
  <title>{escape(lg["name"])} - placeholder badge</title>
  <!-- PLACEHOLDER: not an official logo. Replace by setting "logo" in leagues.json. -->
  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#25324a"/><stop offset="1" stop-color="#121a2a"/></linearGradient></defs>
  <path d="M60 6 L108 24 V62 C108 88 86 106 60 114 C34 106 12 88 12 62 V24 Z" fill="url(#g)" stroke="#8fa3c2" stroke-width="3"/>
  <path d="M60 14 L100 29 V62 C100 84 82 99 60 106 C38 99 20 84 20 62 V29 Z" fill="none" stroke="#3b4c69" stroke-width="1.5" stroke-dasharray="4 3"/>
  <text x="60" y="68" text-anchor="middle" font-family="Inter, Segoe UI, Arial, sans-serif" font-weight="700" font-size="{size}" fill="#e9eef7" letter-spacing="1">{escape(short)}</text>
  <text x="60" y="90" text-anchor="middle" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="8.5" fill="#8fa3c2" letter-spacing="1.2">PLACEHOLDER</text>
</svg>
'''
    with open(os.path.join(out, f'{lg["id"]}.svg'), "w") as fh:
        fh.write(svg)
print(f"{len(leagues)} placeholder badges -> {os.path.relpath(out, ROOT)}")
