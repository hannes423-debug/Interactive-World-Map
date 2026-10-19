// Hash routes, so deep links and refresh work on static hosting (GitHub Pages).
//
//   #/world
//   #/europe                    region map
//   #/europe/t/swe              territory selected
//   #/europe/t/swe/info         territory information panel
//   #/europe/t/swe/l/shl        league opened from a territory
//   #/europe/l/champions        league opened from the region map

export function parse(hash) {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  const r = { view: parts[0] || null, territory: null, info: false, league: null };
  for (let i = 1; i < parts.length; i++) {
    if (parts[i] === 't') r.territory = parts[++i] ?? null;
    else if (parts[i] === 'l') r.league = parts[++i] ?? null;
    else if (parts[i] === 'info') r.info = true;
  }
  return r;
}

export function format({ view, territory, info, league }) {
  let h = `#/${encodeURIComponent(view)}`;
  if (territory) h += `/t/${encodeURIComponent(territory)}`;
  if (territory && info && !league) h += '/info';
  if (league) h += `/l/${encodeURIComponent(league)}`;
  return h;
}

/** One level up the hierarchy: league -> territory info -> selected -> region -> world. */
export function parent(route, rootView) {
  if (route.league) return { ...route, league: null, info: !!route.territory };
  if (route.info) return { ...route, info: false };
  if (route.territory) return { ...route, territory: null };
  if (route.view !== rootView) return { view: rootView, territory: null, info: false, league: null };
  return null;
}
