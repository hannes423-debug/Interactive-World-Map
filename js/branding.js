// Branding lookup: the only place the UI turns an entity into an image path.
//
//   brand.src('club:tappara', 64)  -> { src, alt, kind: 'asset' | 'local' | 'fallback', asset }
//
// Keys are stable entity keys from assets/branding/manifest.json:
//   league:<id>  club:<id>  flag:<country>  federation:<country>
//   national-team:<country>  tournament:<id>
// Only files present in this repository are used - nothing is loaded from
// external sites at runtime. assets/branding/local/manifest.local.json (git-
// ignored) can add locally kept masters that are not cleared for publication;
// it is only requested when the page URL contains ?branding=local.

const MANIFEST = 'assets/branding/manifest.json';
const LOCAL = 'assets/branding/local/manifest.local.json';

let manifest = { assets: {}, entities: {} };
let local = { assets: {} };
// logos set in the game data (league.logo, team.logo) win over the library
let overrides = new Map();
// logo background plates: league.logoBg / team.logoBg ('none' = no plate), else measured
let plateOverrides = new Map();
const plates = new Map();
const LIGHT = '#eef2f7', DARK = '#16233b';

/** Use the game's own logo files: league.logo -> league:<id>, team.logo -> club:<id>. */
export function useGameLogos(db) {
  overrides = new Map();
  plateOverrides = new Map();
  for (const l of db.leagues.values()) {
    if (l.logo) overrides.set(`league:${l.id}`, l.logo);
    if (l.logoBg) plateOverrides.set(`league:${l.id}`, l.logoBg);
  }
  for (const t of db.teams.values()) {
    if (t.logo) overrides.set(`club:${t.id}`, t.logo);
    if (t.logoBg) plateOverrides.set(`club:${t.id}`, t.logoBg);
  }
}

/** Light plate behind mostly dark or colourful logos, dark plate behind mostly white ones. */
function measure(src) {
  if (!plates.has(src)) {
    plates.set(src, new Promise((resolve) => {
      const im = new Image();
      im.onload = () => {
        try {
          const c = document.createElement('canvas');
          c.width = c.height = 40;
          const g = c.getContext('2d', { willReadFrequently: true });
          g.drawImage(im, 0, 0, 40, 40);
          const d = g.getImageData(0, 0, 40, 40).data;
          let n = 0, light = 0;
          for (let i = 0; i < d.length; i += 4) {
            if (d[i + 3] < 128) continue;
            n++;
            if ((0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255 > 0.82) light++;
          }
          resolve(!n ? null : light / n > 0.55 ? DARK : LIGHT);
        } catch { resolve(LIGHT); }
      };
      im.onerror = () => resolve(null);
      im.src = src;
    }));
  }
  return plates.get(src);
}

/**
 * Make a logo read on the dark map. Default: a glow hugging the logo's outline
 * (white around dark or colourful logos, icy blue around mostly white ones).
 * league.logoBg / team.logoBg = 'light' | 'dark' | '#rrggbb' gives a round plate instead, 'none' nothing.
 */
export function applyPlate(img, key) {
  const set = (c) => {
    if (!c || c === 'none') return;
    img.classList.add('plated');
    img.style.setProperty('--plate', c);
  };
  const forced = plateOverrides.get(key);
  if (forced) return set(forced === 'light' ? LIGHT : forced === 'dark' ? DARK : forced);
  if (!img.src || img.src.startsWith('data:')) return;  // generic badges have their own shield
  measure(img.src).then((c) => {
    if (!c) return;
    img.classList.add('glow');
    img.style.setProperty('--glow', c === DARK ? 'rgba(143, 208, 255, 0.85)' : 'rgba(255, 255, 255, 0.92)');
  });
}

export async function loadBranding() {
  const get = (u) => fetch(u, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const wantLocal = new URLSearchParams(location.search).get('branding') === 'local';
  const [m, l] = await Promise.all([get(MANIFEST), wantLocal ? get(LOCAL) : null]);
  if (m) manifest = m;
  if (l) local = l;
  return { assets: Object.keys(manifest.assets ?? {}).length, local: Object.keys(local.assets ?? {}).length };
}

/** The active asset record for an entity key, or null. */
export function assetFor(key) {
  const ent = manifest.entities?.[key];
  return ent?.active ? manifest.assets?.[ent.active] ?? null : null;
}

export function entity(key) {
  return manifest.entities?.[key] ?? null;
}

/** Image for an entity at a display size (CSS px). Never returns an empty src. */
export function src(key, size = 64, label = '') {
  if (overrides.has(key)) return { src: overrides.get(key), alt: label, kind: 'custom', asset: null };
  const a = assetFor(key);
  const need = size * Math.min(2, window.devicePixelRatio || 1);
  if (a) {
    const outs = Object.entries(a.outputs ?? {}).map(([s, p]) => [Number(s), p]).sort((x, y) => x[0] - y[0]);
    const pick = outs.find(([s]) => s >= need) ?? outs[outs.length - 1];
    if (pick) return { src: pick[1], alt: a.name, kind: 'asset', asset: a };
    if (a.master) return { src: a.master, alt: a.name, kind: 'asset', asset: a };
    const lm = local.assets?.[a.id]?.master;
    if (lm) return { src: lm, alt: a.name, kind: 'local', asset: a };
  }
  return { src: fallback(label || key.split(':')[1] || '?', key.split(':')[0]), alt: label, kind: 'fallback', asset: a };
}

/** <img> element with automatic fallback if the file fails to load. */
export function img(key, size, label, cls = 'brand-img') {
  const r = src(key, size, label);
  const el = document.createElement('img');
  el.className = `${cls} brand-${r.kind}`;
  el.width = size;
  el.height = key.startsWith('flag:') ? Math.round(size * 0.66) : size;
  el.alt = r.alt || label || '';
  el.loading = 'lazy';
  el.decoding = 'async';
  el.src = r.src;
  el.title = r.kind === 'fallback' ? `${label || key}: no cleared logo in this build` : r.alt;
  el.addEventListener('error', () => { el.src = fallback(label || '?', key.split(':')[0]); el.className = `${cls} brand-fallback`; }, { once: true });
  applyPlate(el, key);
  return el;
}

const COLORS = { league: '#2b3a55', club: '#26324a', flag: '#2a3346', federation: '#2d3a4f', 'national-team': '#2d3a4f', tournament: '#33304d' };

/** One consistent, clearly generic fallback: initials on a neutral shield. */
export function fallback(label, type = 'club') {
  const words = String(label).replace(/[^\p{L}\p{N} -]/gu, ' ').split(/[\s-]+/).filter(Boolean);
  let txt = words.length > 1 ? words.slice(0, 3).map((w) => w[0]).join('') : (words[0] ?? '?').slice(0, 4);
  txt = txt.toUpperCase();
  const fs = txt.length <= 2 ? 34 : txt.length === 3 ? 28 : 22;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M50 6 88 20v30c0 22-17 37-38 44C29 87 12 72 12 50V20Z" fill="${COLORS[type] ?? '#26324a'}" stroke="#55657f" stroke-width="2" stroke-dasharray="5 4"/><text x="50" y="${50 + fs / 3}" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-weight="700" font-size="${fs}" fill="#c9d4e5">${txt.replace(/[<&>]/g, '')}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
