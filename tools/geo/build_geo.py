#!/usr/bin/env python3
"""Build the territory boundary files in data/geo/ from Natural Earth.

Dev-time tool only; the website reads the generated JSON directly.

Source: Natural Earth 1:50m (public domain), pinned to v5.1.2
  admin 0 countries          -> data/geo/countries.json      (id = ADM0_A3, e.g. "SWE")
  admin 1 states/provinces   -> data/geo/subdivisions.json   (id = ISO 3166-2, e.g. "CA-ON")
                                for the countries in SUBDIVISION_COUNTRIES only

Output format (compact, not GeoJSON, to keep the page light):
  { "source": ..., "features": { "<id>": { "name": "...", "rings": [[[lon,lat],...], ...] } } }
Every ring is an outer ring; holes are dropped (they do not matter for hover).

Usage
  python3 tools/geo/build_geo.py
"""
import json
import os
import urllib.request

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE = os.path.join(ROOT, "tools", "geo", ".cache")
OUTDIR = os.path.join(ROOT, "data", "geo")
NE = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/geojson/"
SOURCES = {
    "admin0_50m.geojson": NE + "ne_50m_admin_0_countries.geojson",
    "admin1_50m.geojson": NE + "ne_50m_admin_1_states_provinces.geojson",
    "lakes_50m.geojson": NE + "ne_50m_lakes.geojson",
}
SUBDIVISION_COUNTRIES = {"CAN", "USA", "RUS"}
TOLERANCE = 0.035   # degrees, Douglas-Peucker
MIN_AREA = 0.03     # square degrees; smaller islands are dropped
DECIMALS = 3


def fetch():
    os.makedirs(CACHE, exist_ok=True)
    for name, url in SOURCES.items():
        path = os.path.join(CACHE, name)
        if not os.path.exists(path):
            print("downloading", url)
            urllib.request.urlretrieve(url, path)


def simplify(ring):
    a = np.array(ring, dtype=np.float64)
    if len(a) < 4:
        return None
    # unwrap rings that cross the antimeridian so the area test works
    area = 0.5 * abs(np.dot(a[:-1, 0], a[1:, 1]) - np.dot(a[1:, 0], a[:-1, 1]))
    if area < MIN_AREA:
        return None
    s = cv2.approxPolyDP(a.astype(np.float32).reshape(-1, 1, 2), TOLERANCE, True).reshape(-1, 2)
    if len(s) < 3:
        return None
    return [[round(float(x), DECIMALS), round(float(y), DECIMALS)] for x, y in s]


def rings_of(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    out = []
    for p in polys:
        r = simplify(p[0])
        if r:
            out.append(r)
    return out


def main():
    fetch()
    os.makedirs(OUTDIR, exist_ok=True)
    src = "Natural Earth 1:50m v5.1.2 (public domain), simplified by tools/geo/build_geo.py"

    countries = {}
    for f in json.load(open(os.path.join(CACHE, "admin0_50m.geojson")))["features"]:
        p = f["properties"]
        code = p["ADM0_A3"]
        if code == "ATA":
            continue
        rings = rings_of(f["geometry"])
        if rings:
            countries[code] = {"name": p["NAME"], "rings": rings}
    write("countries.json", {"source": src, "idField": "ADM0_A3", "features": countries})

    subs = {}
    for f in json.load(open(os.path.join(CACHE, "admin1_50m.geojson")))["features"]:
        p = f["properties"]
        if p["adm0_a3"] not in SUBDIVISION_COUNTRIES:
            continue
        rings = rings_of(f["geometry"])
        if rings:
            subs[p["iso_3166_2"]] = {"name": p["name"], "country": p["adm0_a3"], "rings": rings}
    write("subdivisions.json", {"source": src, "idField": "iso_3166_2", "features": subs})


def write(name, obj):
    path = os.path.join(OUTDIR, name)
    with open(path, "w") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    print(f"{path}: {len(obj['features'])} features, {os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    main()
