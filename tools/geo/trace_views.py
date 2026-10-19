#!/usr/bin/env python3
"""Trace territory outlines that follow each background image's own artwork.

Dev-time tool only. Run after calibrate.py.

For every view in data/maps.json:
  * Natural Earth countries (and subdivisions for the countries listed in the
    view's "subdivide") are placed on the image with the view's calibration.
  * Each unit's interior becomes a watershed marker; the image's painted border
    lines and coastline act as ridges, so the traced outline snaps to what is
    drawn in the artwork. Where the artwork has no line, the calibrated Natural
    Earth border is used as a weaker ridge.
  * The result is written to data/geo/views/<view>.json as SVG path strings in
    image pixel coordinates.

These files are plain data: a wrong outline can be fixed by editing the path
for that id (see README "Correcting territory boundaries") or by adjusting
the calibration / control points and re-running this tool.

Usage
  python3 tools/geo/trace_views.py            # all views
  python3 tools/geo/trace_views.py europe     # one view

Requires numpy, scipy, opencv-python-headless, scikit-image, Pillow.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.segmentation import watershed

sys.path.insert(0, os.path.dirname(__file__))
from calibrate import apply_affine, image_lines, projected, warp_points  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAPS = os.path.join(ROOT, "data", "maps.json")
GEO = os.path.join(ROOT, "data", "geo")
OUT = os.path.join(ROOT, "tools", "geo", "out")
MAX_ERODE = 14        # how far (px) a traced border may move from the calibrated one
                      # (per view override: "traceMaxErode" in data/maps.json)
MIN_AREA_PX = 40      # units smaller than this on a view are not exported
SIMPLIFY_PX = 0.8
ISLAND_SNAP_PX = 30  # unassigned islands this close join the nearest unit


def load_units(spec):
    countries = json.load(open(os.path.join(GEO, "countries.json")))["features"]
    subs = json.load(open(os.path.join(GEO, "subdivisions.json")))["features"]
    split = set(spec.get("subdivide", []))
    units = {}
    for code, f in countries.items():
        if code in split:
            continue
        units[code] = {"name": f["name"], "kind": "country", "country": code, "rings": f["rings"]}
    for code, f in subs.items():
        if f["country"] in split:
            units[code] = {"name": f["name"], "kind": "subdivision", "country": f["country"], "rings": f["rings"]}
    return units


def place(cal, rings, W, H):
    out = []
    for r in rings:
        ll = np.array(r, float)
        xy = apply_affine(cal["affine"], projected(cal["projection"], ll))
        if not np.isfinite(xy).all() or np.abs(np.diff(xy[:, 0])).max(initial=0) > W * 0.3:
            continue
        if xy[:, 0].max() < 0 or xy[:, 0].min() > W or xy[:, 1].max() < 0 or xy[:, 1].min() > H:
            continue
        out.append(warp_points(xy, cal.get("warp"), W, H))
    return out


def ring_path(c):
    pts = c.reshape(-1, 2)
    return "M" + "L".join(f"{x},{y}" for x, y in pts) + "Z"


def trace(vid, spec):
    W, H = spec["width"], spec["height"]
    cal = spec["calibration"]
    img, land, coast, lines = image_lines(os.path.join(ROOT, spec["image"]))
    land = land.astype(bool)

    units = load_units(spec)
    ids = []
    prior = np.zeros((H, W), np.uint8)       # calibrated borders
    labels_ne = np.zeros((H, W), np.int32)
    for uid, u in units.items():
        polys = place(cal, u["rings"], W, H)
        if not polys:
            continue
        m = np.zeros((H, W), np.uint8)
        cv2.fillPoly(m, [np.round(p * 8).astype(np.int32) for p in polys], 1, shift=3)
        if m.sum() < MIN_AREA_PX:
            continue
        ids.append(uid)
        labels_ne[m > 0] = len(ids)
        cv2.polylines(prior, [np.round(p * 8).astype(np.int32) for p in polys], True, 1, 1, shift=3)

    # markers: each unit's calibrated interior, eroded so the border can move
    markers = np.zeros((H, W), np.int32)
    for k in range(1, len(ids) + 1):
        m = (labels_ne == k) & land
        if not m.any():
            continue
        dt = ndimage.distance_transform_edt(m)
        depth = min(spec.get("traceMaxErode", MAX_ERODE), max(1.0, dt.max() * 0.5))
        markers[(dt >= depth) & m] = k

    # ridges: painted lines (strong) and calibrated borders (weak)
    g = img.astype(np.float32).mean(2)
    tophat = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, np.ones((5, 5), np.uint8))
    painted = cv2.GaussianBlur(np.clip(tophat / 60.0, 0, 1), (0, 0), 1.0)
    weak = cv2.GaussianBlur(prior.astype(np.float32), (0, 0), 4.0)
    weak = weak / max(weak.max(), 1e-6) * 0.35
    elevation = np.maximum(painted, weak)

    lab = watershed(elevation, markers, mask=land)
    # islands that received no marker join the nearest unit if it is close
    orphan = land & (lab == 0)
    if orphan.any() and (lab > 0).any():
        d, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
        near = orphan & (d <= ISLAND_SNAP_PX)
        lab[near] = lab[iy[near], ix[near]]

    def outline(m):
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        cs, _ = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        parts = []
        for c in cs:
            if cv2.contourArea(c) < 6:
                continue
            c = cv2.approxPolyDP(c, SIMPLIFY_PX, True)
            if len(c) >= 3:
                parts.append(ring_path(c))
        return "".join(parts)

    feats = {}
    for k, uid in enumerate(ids, start=1):
        m = (lab == k).astype(np.uint8)
        if m.sum() < MIN_AREA_PX:
            continue
        d = outline(m)
        if not d:
            continue
        x, y, w, h = cv2.boundingRect(cv2.findNonZero(m))
        u = units[uid]
        feats[uid] = {"name": u["name"], "kind": u["kind"], "country": u["country"],
                      "bbox": [int(x), int(y), int(w), int(h)], "d": d}

    # dissolved outline for each subdivided country, so hovering the country
    # does not stroke every internal border
    countries = json.load(open(os.path.join(GEO, "countries.json")))["features"]
    for code in spec.get("subdivide", []):
        ks = [k for k, uid in enumerate(ids, start=1) if units[uid]["country"] == code]
        if not ks:
            continue
        m = np.isin(lab, ks).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        d = outline(m)
        if d:
            x, y, w, h = cv2.boundingRect(cv2.findNonZero(m))
            feats[code] = {"name": countries.get(code, {}).get("name", code), "kind": "country",
                           "country": code, "subdivided": True,
                           "bbox": [int(x), int(y), int(w), int(h)], "d": d}

    os.makedirs(os.path.join(GEO, "views"), exist_ok=True)
    path = os.path.join(GEO, "views", f"{vid}.json")
    with open(path, "w") as fh:
        json.dump({"view": vid, "width": W, "height": H,
                   "source": "Natural Earth 1:50m (public domain), calibrated and traced against "
                             f"{spec['image']} by tools/geo/trace_views.py",
                   "features": feats}, fh, separators=(",", ":"))
    print(f"  {vid:14s} {len(feats)} units -> {os.path.relpath(path, ROOT)} ({os.path.getsize(path) // 1024} KB)")

    # preview: random fills + outlines over the image
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(1)
    pal = rng.integers(60, 255, (len(ids) + 1, 3)).astype(np.uint8)
    pal[0] = 0
    over = img.copy()
    sel = lab > 0
    over[sel] = (0.55 * img[sel] + 0.45 * pal[lab[sel]]).astype(np.uint8)
    edges = cv2.morphologyEx(lab.astype(np.float32), cv2.MORPH_GRADIENT, np.ones((3, 3))) > 0
    over[edges & sel] = (255, 220, 60)
    Image.fromarray(over).save(os.path.join(OUT, f"{vid}-traced.png"))


def main():
    args = sys.argv[1:]
    maps = json.load(open(MAPS))
    for vid, spec in maps["views"].items():
        if args and vid not in args:
            continue
        trace(vid, spec)


if __name__ == "__main__":
    main()
