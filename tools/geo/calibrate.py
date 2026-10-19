#!/usr/bin/env python3
"""Align Natural Earth boundaries with each background map image.

Dev-time tool only; the website never runs Python.

The background images are artwork, not exact projections, so alignment is
done in three layers that the browser applies in the same order
(js/projection.js):

  1. projection  - a standard projection (Miller, orthographic, ...)
  2. affine      - 2x3 matrix from projected units to image pixels
  3. warp        - a coarse grid of pixel offsets, bilinearly interpolated,
                   that absorbs the artwork's local distortions

How the fit works (iterative closest point)
  * Lines are extracted from the image: the land/ocean edge (ocean is near
    black in the red channel) plus the thin bright border lines.
  * Natural Earth country outlines are projected and sampled every few px.
  * Each sample is matched to the nearest image line pixel; the affine and
    then the warp grid are solved by regularised least squares. Repeat with a
    shrinking search radius.
  * control_points.json gives rough seeds so the first iteration converges.

Usage
  python3 tools/geo/calibrate.py            # all views, writes data/maps.json
  python3 tools/geo/calibrate.py europe     # one view
  python3 tools/geo/calibrate.py --preview  # only redraw tools/geo/out/*.png

Requires numpy, scipy, opencv-python-headless, Pillow. Run build_geo.py first.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage, sparse
from scipy.sparse.linalg import spsolve

sys.path.insert(0, os.path.dirname(__file__))
from projections import project  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "tools", "geo", "out")
MAPS = os.path.join(ROOT, "data", "maps.json")
CTRL = os.path.join(ROOT, "tools", "geo", "control_points.json")
GEO = os.path.join(ROOT, "data", "geo", "countries.json")

GRID = (41, 23)          # warp grid nodes (cols, rows)
SMOOTH = 4.0             # warp smoothness weight
CANDIDATES = {
    "cylindrical": [{"type": "miller", "lon0": 0}, {"type": "mercator", "lon0": 0},
                    {"type": "equirectangular", "lon0": 0}],
    "regional": ["orthographic", "perspective", "lcc"],
}


# ---------------------------------------------------------------- image side
def image_lines(path):
    a = np.asarray(Image.open(path).convert("RGB"))
    r = cv2.GaussianBlur(a[..., 0], (5, 5), 0)
    land = (r > 14).astype(np.uint8)
    land = cv2.morphologyEx(land, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    coast = cv2.morphologyEx(land, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    g = a.astype(np.float32).mean(2)
    tophat = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, np.ones((5, 5), np.uint8))
    borders = tophat > 35
    # drop speckle (mountain texture) - keep connected line pieces only
    n, lab, stats, _ = cv2.connectedComponentsWithStats(borders.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 40
    borders = keep[lab]
    lines = coast | borders
    return a, land, coast, lines


# ----------------------------------------------------------------- geo side
def load_samples():
    """Country outlines as one point array plus ring split indices (lon/lat)."""
    feats = json.load(open(GEO))["features"]
    rings = [np.array(r, float) for f in feats.values() for r in f["rings"]]
    lens = [len(r) for r in rings]
    return np.concatenate(rings), np.cumsum(lens)[:-1]


def densify(xy, splits, W, H, step=4.0):
    out = []
    for ring in np.split(xy, splits):
        if not np.isfinite(ring).all():
            continue
        seg = np.vstack([ring, ring[:1]])
        d = np.diff(seg, axis=0)
        L = np.hypot(d[:, 0], d[:, 1])
        if L.max(initial=0) > W * 0.3:      # wrapped across the antimeridian
            continue
        for p, dd, l in zip(seg[:-1], d, L):
            n = max(1, int(l // step))
            t = np.arange(n)[:, None] / n
            out.append(p + t * dd)
    if not out:
        return np.zeros((0, 2))
    pts = np.concatenate(out)
    m = (pts[:, 0] >= 2) & (pts[:, 0] < W - 2) & (pts[:, 1] >= 2) & (pts[:, 1] < H - 2)
    return pts[m]


def projected(proj, lonlat):
    x, y, vis = project(proj, lonlat[:, 0], lonlat[:, 1])
    xy = np.stack([x, y], 1)
    xy[~vis] = np.nan
    return xy


def apply_affine(aff, xy):
    a, b, c, d, e, f = aff
    return np.stack([a * xy[:, 0] + b * xy[:, 1] + c, d * xy[:, 0] + e * xy[:, 1] + f], 1)


def invert_to_unit(aff, px):
    a, b, c, d, e, f = aff
    M = np.array([[a, b], [d, e]])
    return (px - [c, f]) @ np.linalg.inv(M).T


# --------------------------------------------------------------------- warp
def bilinear_weights(pts, W, H):
    cols, rows = GRID
    gx = pts[:, 0] / W * (cols - 1)
    gy = pts[:, 1] / H * (rows - 1)
    i0 = np.clip(np.floor(gx).astype(int), 0, cols - 2)
    j0 = np.clip(np.floor(gy).astype(int), 0, rows - 2)
    fx, fy = gx - i0, gy - j0
    idx = np.stack([j0 * cols + i0, j0 * cols + i0 + 1, (j0 + 1) * cols + i0, (j0 + 1) * cols + i0 + 1], 1)
    w = np.stack([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy], 1)
    return idx, w


def warp_points(pts, warp, W, H):
    if warp is None:
        return pts
    idx, w = bilinear_weights(pts, W, H)
    dx = (np.asarray(warp["dx"])[idx] * w).sum(1)
    dy = (np.asarray(warp["dy"])[idx] * w).sum(1)
    return pts + np.stack([dx, dy], 1)


def laplacian():
    cols, rows = GRID
    n = cols * rows
    r, c, v = [], [], []
    k = 0
    for j in range(rows):
        for i in range(cols):
            nb = [(i + di, j + dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if 0 <= i + di < cols and 0 <= j + dj < rows]
            r.append(k); c.append(j * cols + i); v.append(float(len(nb)))
            for ii, jj in nb:
                r.append(k); c.append(jj * cols + ii); v.append(-1.0)
            k += 1
    return sparse.csr_matrix((v, (r, c)), shape=(n, n))


def match(pts, dist, idx, radius):
    H, W = dist.shape
    xi = np.clip(np.round(pts[:, 0]).astype(int), 0, W - 1)
    yi = np.clip(np.round(pts[:, 1]).astype(int), 0, H - 1)
    d = dist[yi, xi]
    ok = d < radius
    tgt = np.stack([idx[1][yi, xi], idx[0][yi, xi]], 1).astype(float)
    return tgt, ok, d


def render_land(proj, aff, lonlat, splits, W, H, warp=None):
    xy = apply_affine(aff, projected(proj, lonlat))
    polys = []
    for ring in np.split(xy, splits):
        if not np.isfinite(ring).all() or np.abs(np.diff(ring[:, 0])).max(initial=0) > W * 0.3:
            continue
        if ring[:, 0].max() < -W or ring[:, 0].min() > 2 * W or ring[:, 1].max() < -H or ring[:, 1].min() > 2 * H:
            continue
        ring = warp_points(ring, warp, W, H)
        polys.append(np.round(ring * 8).astype(np.int32))
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, polys, 1, shift=3)
    return m


def coast_pixels(mask, step=2):
    edge = cv2.morphologyEx(mask, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    edge[:3, :] = edge[-3:, :] = False
    edge[:, :3] = edge[:, -3:] = False
    ys, xs = np.nonzero(edge)
    pts = np.stack([xs, ys], 1).astype(float)
    return pts[::step]


def solve_affine_icp(proj, aff, lonlat, splits, W, H, cdist, cidx, radii, cps=None):
    """ICP on coastline pixels; cps=(lonlat, px, weight) anchors the solve."""
    score = 1e9
    for R in radii:
        for _ in range(3):
            land = render_land(proj, aff, lonlat, splits, W, H)
            pts = coast_pixels(land, 3)
            if len(pts) < 100:
                return aff, 1e9
            tgt, ok, d = match(pts, cdist, cidx, R)
            if ok.sum() < 100:
                return aff, 1e9
            u = invert_to_unit(aff, pts[ok])
            t = tgt[ok]
            w = np.ones(len(u))
            if cps is not None:
                cu = projected(proj, cps[0])
                u = np.vstack([u, cu]); t = np.vstack([t, cps[1]])
                w = np.concatenate([w, np.full(len(cu), cps[2] * len(w) / max(1, len(cu)))])
            A = np.hstack([u, np.ones((len(u), 1))]) * np.sqrt(w)[:, None]
            ax = np.linalg.lstsq(A, t[:, 0] * np.sqrt(w), rcond=None)[0]
            ay = np.linalg.lstsq(A, t[:, 1] * np.sqrt(w), rcond=None)[0]
            aff = list(ax) + list(ay)
        score = float(np.mean(np.minimum(d, R)))
    return aff, score


def fit_view(vid, spec, ctrl, lonlat, splits):
    W, H = spec["width"], spec["height"]
    _, land_img, coast_img, lines_img = image_lines(os.path.join(ROOT, spec["image"]))
    cdist, cidx = ndimage.distance_transform_edt(~coast_img, return_indices=True)
    cl = np.array([[c["lon"], c["lat"]] for c in ctrl])
    cp = np.array([c["px"] for c in ctrl], float)
    # share of the least-squares solve given to control points (0 = seed only)
    cpw = spec.get("controlPointWeight", 0.0)

    def seed_affine(proj):
        xy = projected(proj, cl)
        A = np.hstack([xy, np.ones((len(xy), 1))])
        ax = np.linalg.lstsq(A, cp[:, 0], rcond=None)[0]
        ay = np.linalg.lstsq(A, cp[:, 1], rcond=None)[0]
        return list(ax) + list(ay)

    def cp_rms(proj, aff):
        xy = apply_affine(aff, projected(proj, cl))
        return float(np.sqrt(((xy - cp) ** 2).sum(1).mean())) if np.isfinite(xy).all() else 1e9

    # 1+2: choose the projection by control-point fit, then refine affine by ICP
    kind = spec.get("calibrationKind", "regional")
    seed = spec.get("calibrationSeed", {})
    trials = []
    if kind == "cylindrical":
        trials = [dict(p) for p in CANDIDATES["cylindrical"]]
    else:
        for t in CANDIDATES["regional"]:
            for l0 in np.arange(seed["lon0"] - 30, seed["lon0"] + 30.1, 5):
                for p0 in np.arange(seed["lat0"] - 20, seed["lat0"] + 20.1, 5):
                    p = {"type": t, "lon0": float(l0), "lat0": float(p0)}
                    if t == "perspective":
                        p["distance"] = 2.5
                    if t == "lcc":
                        for span in (8, 15, 25):
                            q = dict(p, lat1=float(max(5, p0 - span)), lat2=float(min(84, p0 + span)))
                            trials.append(q)
                        continue
                    trials.append(p)
    scored = []
    for p in trials:
        try:
            aff = seed_affine(p)
        except np.linalg.LinAlgError:
            continue
        scored.append((cp_rms(p, aff), p, aff))
    scored.sort(key=lambda s: s[0])
    # ICP the best few seeds of each projection type; keep the best coastline match
    picks = []
    for t in {p["type"] for _, p, _ in scored}:
        picks += [s for s in scored if s[1]["type"] == t][:3]
    best = None
    for rms, p, a in picks:
        a2, sc = solve_affine_icp(p, a, lonlat, splits, W, H, cdist, cidx, (60, 30, 15, 10),
                                  cps=(cl, cp, cpw) if cpw > 0 else None)
        if best is None or sc < best[0]:
            best = (sc, rms, p, a2)
    score, rms0, proj, aff = best
    print(f"  {vid:14s} {proj['type']:15s} lon0={proj.get('lon0', 0):7.2f} lat0={proj.get('lat0', 0):6.2f}"
          f"  control-point rms={rms0:.1f}px -> {cp_rms(proj, aff):.1f}px after ICP")

    # 3: warp grid, fitted on coastline pixels and anchored by the control points
    cols, rows = GRID
    n = cols * rows
    L = laplacian()
    base = coast_pixels(render_land(proj, aff, lonlat, splits, W, H), 2)
    cbase = apply_affine(aff, projected(proj, cl))
    allp = np.vstack([base, cbase])
    bidx, bw = bilinear_weights(allp, W, H)
    B = sparse.csr_matrix((bw.ravel(), (np.repeat(np.arange(len(allp)), 4), bidx.ravel())), shape=(len(allp), n))
    warp = {"cols": cols, "rows": rows, "dx": np.zeros(n), "dy": np.zeros(n)}
    for R in (60, 40, 28, 20, 14, 10, 7, 5):
        for _ in range(2):
            cur = warp_points(base, warp, W, H)
            tgt, ok, d = match(cur, cdist, cidx, R)
            wts = ok * (1.0 / (1.0 + (d / (0.5 * R)) ** 2))
            # control points: strong early, fading as coastlines take over
            cw = max(cpw, 0.3 if R >= 28 else 0.0) * max(wts.sum(), 1.0) / len(cl) * (R / 60.0)
            wall = np.concatenate([wts, np.full(len(cl), cw)])
            tall = np.vstack([tgt, cp])
            lam = SMOOTH * max(1.0, wts.sum() / n) * 0.05
            M = (B.T @ sparse.diags(wall) @ B + lam * (L.T @ L) + 1e-3 * sparse.eye(n)).tocsc()
            warp["dx"] = spsolve(M, B.T @ (wall * (tall[:, 0] - allp[:, 0])))
            warp["dy"] = spsolve(M, B.T @ (wall * (tall[:, 1] - allp[:, 1])))
    land = render_land(proj, aff, lonlat, splits, W, H, warp)
    pts = coast_pixels(land, 2)
    _, _, d = match(pts, cdist, cidx, 1e9)
    inter = (land & land_img).sum(); dice = 2 * inter / (land.sum() + land_img.sum())
    cerr = np.hypot(*(warp_points(cbase, warp, W, H) - cp).T)
    print(f"  {vid:14s} after warp: coast median error {np.median(d):.1f}px, "
          f"{(d <= 4).mean() * 100:.0f}% within 4px, land dice {dice:.3f}, control points rms {np.sqrt((cerr**2).mean()):.1f}px")
    return {
        "projection": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in proj.items()},
        "affine": [round(float(v), 4) for v in aff],
        "warp": {"cols": cols, "rows": rows,
                 "dx": [round(float(v), 1) for v in warp["dx"]],
                 "dy": [round(float(v), 1) for v in warp["dy"]]},
        "fit": {"tool": "tools/geo/calibrate.py", "coastMedianErrorPx": round(float(np.median(d)), 1),
                "coastWithin4px": round(float((d <= 4).mean()), 3), "landDice": round(float(dice), 3)},
    }


def preview(vid, spec, lonlat, splits):
    os.makedirs(OUT, exist_ok=True)
    img = np.asarray(Image.open(os.path.join(ROOT, spec["image"])).convert("RGB")).copy()
    W, H = spec["width"], spec["height"]
    cal = spec["calibration"]
    xy = apply_affine(cal["affine"], projected(cal["projection"], lonlat))
    for ring in np.split(xy, splits):
        if not np.isfinite(ring).all() or np.abs(np.diff(ring[:, 0])).max(initial=0) > W * 0.3:
            continue
        ring = warp_points(ring, cal.get("warp"), W, H)
        cv2.polylines(img, [np.round(ring * 8).astype(np.int32)], True, (255, 190, 40), 1, cv2.LINE_AA, shift=3)
    Image.fromarray(img).save(os.path.join(OUT, f"{vid}.png"))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    maps = json.load(open(MAPS))
    ctrl = json.load(open(CTRL))
    lonlat, splits = load_samples()
    for vid, spec in maps["views"].items():
        if args and vid not in args:
            continue
        if "--preview" not in sys.argv:
            spec["calibration"] = fit_view(vid, spec, ctrl[vid], lonlat, splits)
            with open(MAPS, "w") as fh:
                json.dump(maps, fh, indent=2)
                fh.write("\n")
        preview(vid, spec, lonlat, splits)
        print(f"  {vid:14s} overlay -> tools/geo/out/{vid}.png")


if __name__ == "__main__":
    main()
