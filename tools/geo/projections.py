"""Map projections used to place lon/lat geometry onto the background images.

This is the Python twin of js/projection.js. Both must stay in sync: the
calibration tool fits parameters here and the browser applies the same maths.

A view's calibration is:
    projection: {"type": ..., plus type-specific params (degrees)}
    affine:     [a, b, c, d, e, f]  ->  px = a*x + b*y + c,  py = d*x + e*y + f
where (x, y) is the projected point in unit-sphere coordinates with y pointing
north (so the affine usually has a negative 'e').
"""
import numpy as np

D2R = np.pi / 180.0


def _wrap(dlon):
    return (dlon + 180.0) % 360.0 - 180.0


def project(proj, lon, lat):
    """Return (x, y, visible) arrays for lon/lat arrays in degrees."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    t = proj["type"]
    vis = np.ones(lon.shape, dtype=bool)
    if t in ("equirectangular", "mercator", "miller"):
        lon0 = proj.get("lon0", 0.0)
        x = _wrap(lon - lon0) * D2R
        phi = np.clip(lat, -85.0, 85.0) * D2R
        if t == "equirectangular":
            y = phi
        elif t == "mercator":
            y = np.log(np.tan(np.pi / 4 + phi / 2))
        else:
            y = 1.25 * np.log(np.tan(np.pi / 4 + 0.4 * phi))
        return x, y, vis
    if t in ("orthographic", "perspective"):
        l0, p0 = proj["lon0"] * D2R, proj["lat0"] * D2R
        lam, phi = lon * D2R, lat * D2R
        dl = lam - l0
        cosc = np.sin(p0) * np.sin(phi) + np.cos(p0) * np.cos(phi) * np.cos(dl)
        x = np.cos(phi) * np.sin(dl)
        y = np.cos(p0) * np.sin(phi) - np.sin(p0) * np.cos(phi) * np.cos(dl)
        if t == "perspective":
            P = proj["distance"]  # camera distance from centre, in earth radii
            k = (P - 1.0) / (P - cosc)
            x, y = x * k, y * k
            vis = cosc > 1.0 / P
        else:
            vis = cosc > 0
        return x, y, vis
    if t == "lcc":
        l0, p0 = proj["lon0"] * D2R, proj["lat0"] * D2R
        p1, p2 = proj["lat1"] * D2R, proj["lat2"] * D2R
        n = np.log(np.cos(p1) / np.cos(p2)) / np.log(np.tan(np.pi / 4 + p2 / 2) / np.tan(np.pi / 4 + p1 / 2))
        F = np.cos(p1) * np.tan(np.pi / 4 + p1 / 2) ** n / n
        phi = np.clip(lat, -80.0, 89.5) * D2R
        rho = F / np.tan(np.pi / 4 + phi / 2) ** n
        rho0 = F / np.tan(np.pi / 4 + p0 / 2) ** n
        th = n * _wrap(lon - proj["lon0"]) * D2R
        return rho * np.sin(th), rho0 - rho * np.cos(th), vis
    raise ValueError("unknown projection " + t)


def to_pixels(view, lon, lat):
    x, y, vis = project(view["projection"], lon, lat)
    a, b, c, d, e, f = view["affine"]
    return a * x + b * y + c, d * x + e * y + f, vis
