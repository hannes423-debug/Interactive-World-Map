#!/usr/bin/env python3
"""Measure how well territory outlines follow the painted lines in each map image.

For every territory a game shows on a map, its outline (data/geo/views/<map>.json)
is rasterised and each outline pixel is checked against the image's own lines
(coastline + painted borders, as found by calibrate.image_lines). Reports the
share of outline pixels within 2 px and 4 px of a painted line, and writes an
overlay to tools/geo/out/<map>-territories.png.

Low numbers point at a territory whose boundary needs correcting.

Usage: python3 tools/geo/check_alignment.py [game]   (default nhl13)
"""
import json
import os
import re
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, os.path.dirname(__file__))
from calibrate import image_lines  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "tools", "geo", "out")


def path_rings(d):
    for ring in re.findall(r"M([^Z]+)Z", d):
        pts = [tuple(map(float, p.split(","))) for p in ring.split("L")]
        yield np.array(pts)


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "nhl13"
    g = json.load(open(os.path.join(ROOT, "games", game, "game.json")))
    terrs = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "games", game, "territories.json")))["territories"]}
    maps = json.load(open(os.path.join(ROOT, "data", "maps.json")))["views"]
    os.makedirs(OUT, exist_ok=True)
    for vid, v in g["views"].items():
        spec = maps.get(v["map"])
        if not spec:
            continue
        geo = json.load(open(os.path.join(ROOT, "data", "geo", "views", f"{v['map']}.json")))["features"]
        img, land, coast, lines = image_lines(os.path.join(ROOT, spec["image"]))
        dist = ndimage.distance_transform_edt(~lines)
        over = img.copy()
        items = v.get("territories") or v.get("regions") or []
        print(f"{vid} ({spec['image']})")
        for tid in items:
            if v["level"] == "world":
                units, name = g["views"][tid].get("worldUnits", []), g["views"][tid]["title"]
            else:
                t = terrs.get(tid, {})
                units, name = t.get("geo", []), t.get("name", tid)
            m = np.zeros(dist.shape, np.uint8)
            for u in units:
                if u in geo:
                    for r in path_rings(geo[u]["d"]):
                        cv2.fillPoly(m, [np.round(r).astype(np.int32)], 1)
            if not m.any():
                print(f"  {name:28s} no outline on this map")
                continue
            edge = cv2.morphologyEx(m, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
            edge[:2, :] = edge[-2:, :] = False
            edge[:, :2] = edge[:, -2:] = False
            d = dist[edge]
            print(f"  {name:28s} {(d <= 2).mean() * 100:5.1f}% within 2px   {(d <= 4).mean() * 100:5.1f}% within 4px")
            over[edge] = (255, 210, 60)
        Image.fromarray(over).save(os.path.join(OUT, f"{v['map']}-territories.png"))


if __name__ == "__main__":
    main()
