// Map projections that place lon/lat points on a background image.
// JavaScript twin of tools/geo/projections.py - keep both in sync.
//
// A view calibration (data/maps.json -> views.<id>.calibration) is:
//   projection: { type, ...params in degrees }
//   affine:     [a, b, c, d, e, f]   px = a*x + b*y + c, py = d*x + e*y + f
//   warp:       { cols, rows, dx: [], dy: [] }  pixel offsets on a regular grid

const D2R = Math.PI / 180;
const wrap = (d) => ((((d + 180) % 360) + 360) % 360) - 180;

export function project(p, lon, lat) {
  switch (p.type) {
    case 'equirectangular':
    case 'mercator':
    case 'miller': {
      const x = wrap(lon - (p.lon0 || 0)) * D2R;
      const phi = Math.max(-85, Math.min(85, lat)) * D2R;
      const y = p.type === 'equirectangular' ? phi
        : p.type === 'mercator' ? Math.log(Math.tan(Math.PI / 4 + phi / 2))
        : 1.25 * Math.log(Math.tan(Math.PI / 4 + 0.4 * phi));
      return [x, y, true];
    }
    case 'orthographic':
    case 'perspective': {
      const l0 = p.lon0 * D2R, p0 = p.lat0 * D2R;
      const lam = lon * D2R, phi = lat * D2R, dl = lam - l0;
      const cosc = Math.sin(p0) * Math.sin(phi) + Math.cos(p0) * Math.cos(phi) * Math.cos(dl);
      let x = Math.cos(phi) * Math.sin(dl);
      let y = Math.cos(p0) * Math.sin(phi) - Math.sin(p0) * Math.cos(phi) * Math.cos(dl);
      if (p.type === 'perspective') {
        const k = (p.distance - 1) / (p.distance - cosc);
        return [x * k, y * k, cosc > 1 / p.distance];
      }
      return [x, y, cosc > 0];
    }
    case 'lcc': {
      const p0 = p.lat0 * D2R, p1 = p.lat1 * D2R, p2 = p.lat2 * D2R;
      const t = (v) => Math.tan(Math.PI / 4 + v / 2);
      const n = Math.log(Math.cos(p1) / Math.cos(p2)) / Math.log(t(p2) / t(p1));
      const F = (Math.cos(p1) * Math.pow(t(p1), n)) / n;
      const phi = Math.max(-80, Math.min(89.5, lat)) * D2R;
      const rho = F / Math.pow(t(phi), n);
      const rho0 = F / Math.pow(t(p0), n);
      const th = n * wrap(lon - p.lon0) * D2R;
      return [rho * Math.sin(th), rho0 - rho * Math.cos(th), true];
    }
    default:
      throw new Error(`Unknown projection "${p.type}"`);
  }
}

function warpOffset(warp, x, y, W, H) {
  if (!warp) return [0, 0];
  const { cols, rows, dx, dy } = warp;
  const gx = (x / W) * (cols - 1), gy = (y / H) * (rows - 1);
  const i0 = Math.max(0, Math.min(cols - 2, Math.floor(gx)));
  const j0 = Math.max(0, Math.min(rows - 2, Math.floor(gy)));
  const fx = gx - i0, fy = gy - j0;
  const k = j0 * cols + i0;
  const w = [(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy];
  const idx = [k, k + 1, k + cols, k + cols + 1];
  let ox = 0, oy = 0;
  for (let i = 0; i < 4; i++) { ox += dx[idx[i]] * w[i]; oy += dy[idx[i]] * w[i]; }
  return [ox, oy];
}

/** lon/lat -> image pixel for a calibrated map view. Returns null if not visible. */
export function toPixel(view, lon, lat) {
  const cal = view.calibration;
  if (!cal) return null;
  const [x, y, vis] = project(cal.projection, lon, lat);
  if (!vis || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  const [a, b, c, d, e, f] = cal.affine;
  const px = a * x + b * y + c, py = d * x + e * y + f;
  const [ox, oy] = warpOffset(cal.warp, px, py, view.width, view.height);
  return [px + ox, py + oy];
}

/** Lon/lat rings -> SVG path string in image pixels (approximate fallback outlines). */
export function ringsToPath(view, rings) {
  let d = '';
  for (const ring of rings) {
    const pts = [];
    let ok = true;
    for (const [lon, lat] of ring) {
      const p = toPixel(view, lon, lat);
      if (!p) { ok = false; break; }
      if (pts.length && Math.abs(p[0] - pts[pts.length - 1][0]) > view.width * 0.3) { ok = false; break; }
      pts.push(p);
    }
    if (!ok || pts.length < 3) continue;
    d += 'M' + pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z';
  }
  return d;
}
