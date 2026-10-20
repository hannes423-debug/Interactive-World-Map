// Information panels: territory and league details.
// Every value from the data files is shown with its data-quality status so
// placeholders are never mistaken for real-world facts.

import { leaguesIn, coverage, tierRank, geoUnits, children } from './data.js';
import * as brand from './branding.js';

const STATUS = {
  verified: { label: 'Verified', title: 'Checked against a cited source' },
  reference: { label: 'Reference', title: 'Widely reported real-world value, not yet re-verified for this season' },
  placeholder: { label: 'Placeholder', title: 'Game-design value - not real-world data' },
  game: { label: 'Game setting', title: 'Defined by the career mode' },
  unknown: { label: 'Unknown', title: 'No data yet' },
};

const h = (tag, cls, ...kids) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
};

function chip(datum) {
  const s = STATUS[datum?.status] ? datum.status : 'unknown';
  const c = h('span', `dq dq-${s}`, STATUS[s].label + (datum?.asOf && s === 'reference' ? ` · ${datum.asOf}` : ''));
  c.title = STATUS[s].title + (datum?.note ? ` — ${datum.note}` : '');
  return c;
}

function valueText(v) {
  if (v == null || v === '') return null;
  if (Array.isArray(v)) return v.length ? v : null;
  if (typeof v === 'object' && 'rating' in v) return v;
  return String(v);
}

function rating(v) {
  const wrap = h('span', 'rating');
  for (let i = 1; i <= (v.max || 5); i++) wrap.append(h('i', i <= v.rating ? 'on' : null));
  wrap.append(h('span', 'rating-label', v.label ?? `${v.rating}/${v.max}`));
  return wrap;
}

/** One labelled row: label, value (or "No data yet"), status chip, note. */
function fact(label, datum) {
  const v = valueText(datum?.value);
  let body;
  if (v == null) body = h('span', 'empty', 'No data yet');
  else if (Array.isArray(v)) body = h('ul', 'plain', v.map((x) => h('li', null, x)));
  else if (typeof v === 'object') body = rating(v);
  else body = h('span', null, v);
  const row = h('div', 'fact', h('dt', null, label), h('dd', null, body, chip(datum)));
  if (datum?.note && v != null) row.append(h('p', 'note', datum.note));
  return row;
}

function stat(label, value, sub) {
  return h('div', 'stat', h('span', 'stat-value', value), h('span', 'stat-label', label), sub ? h('span', 'stat-sub', sub) : null);
}

function badgeImg(lg, size = 44) {
  const box = h('span', 'league-mark');
  box.style.setProperty('--s', `${size}px`);
  box.append(brand.img(`league:${lg.id}`, size, lg.shortName));
  return box;
}

/** One line saying where a logo comes from, or why it is not shown. */
function provenance(key, label) {
  const r = brand.src(key, 64, label);
  const a = r.asset;
  if (r.kind === 'asset' && a) {
    const id = a.identity?.status === 'verified_visual' ? ' · matched to current logo' : a.identity?.status === 'unverified' ? ' · identity unverified' : '';
    const el = h('p', 'note full provenance', `${label} logo: `, h('a', null, 'source'), ` (${a.rights?.basis ?? 'rights not recorded'})${id}`);
    const link = el.querySelector('a');
    link.href = a.source?.page ?? '#';
    link.target = '_blank';
    link.rel = 'noopener';
    return el;
  }
  if (r.kind === 'local') return h('p', 'note full provenance', `${label} logo: local copy only - not cleared for publication.`);
  if (r.kind === 'custom') return h('p', 'note full provenance', `${label} logo: from the league database (private copy).`);
  const ent = brand.entity(key);
  return h('p', 'note full provenance', ent?.status === 'restricted'
    ? `${label}: the official logo is not cleared for redistribution, so a generic badge is shown.`
    : `${label}: no logo in the branding library yet - generic badge shown.`);
}

function clubMark(id, name, size = 28) {
  const box = h('span', 'club-mark');
  box.style.setProperty('--s', `${size}px`);
  box.append(brand.img(`club:${id}`, size, name));
  return box;
}

/** Flag, federation and national team shown as separate identities. */
function nationalBlock(db, iso3, nav) {
  if (!iso3) return null;
  const c = iso3.toLowerCase();
  const fed = brand.entity(`federation:${c}`);
  const nt = brand.entity(`national-team:${c}`);
  const flag = brand.entity(`flag:${c}`);
  if (!fed && !nt && !flag) return null;
  const item = (key, label, sub) => h('div', 'nat-item', brand.img(key, 48, label), h('span', null, h('strong', null, label), h('small', null, sub)));
  const block = h('section', 'block', h('h3', null, 'National hockey'),
    h('div', 'nat-grid',
      item(`flag:${c}`, flag?.name?.replace(/^Flag of /, '') ?? iso3, 'Flag'),
      item(`federation:${c}`, fed?.name ?? 'Federation', 'Federation'),
      item(`national-team:${c}`, nt?.name?.replace(/ men's national ice hockey team$/, '') ?? 'National team', "Men's national team")));
  const tours = Object.values(db.tournaments ?? {});
  if (tours.length) {
    const wrap = h('div', 'chips');
    for (const t of tours.filter((x) => x.featured)) {
      const b = h('button', 'chip-link chip-brand', brand.img(`tournament:${t.id}`, 20, t.name), t.name);
      b.type = 'button';
      b.addEventListener('click', () => nav.tournament(t.id));
      wrap.append(b);
    }
    block.append(h('p', 'note', 'International competitions'), wrap);
  }
  return block;
}

export function tournamentPanel(db, id, nav) {
  const t = (db.tournaments ?? {})[id];
  if (!t) return notFound(`Competition "${id}" is not in the database.`);
  const head = h('header', 'panel-head league-head', (() => { const b = h('span', 'league-mark'); b.style.setProperty('--s', '72px'); b.append(brand.img(`tournament:${t.id}`, 72, t.name)); return b; })(),
    h('div', null, h('p', 'eyebrow', 'International competition'), h('h2', null, t.name), t.edition ? h('p', 'sub', t.edition) : null));
  head.append(provenance(`tournament:${t.id}`, t.name));
  const body = h('section', 'block', h('h3', null, 'About'), h('dl', 'facts',
    fact('Organiser', t.organiser), fact('Format', t.format), fact('Career relevance', t.career)));
  const eds = (t.editions ?? []).map((e) => (db.tournaments ?? {})[e]).filter(Boolean);
  const edBlock = eds.length ? h('section', 'block', h('h3', null, 'Editions'), h('div', 'chips', eds.map((e) => {
    const b = h('button', 'chip-link chip-brand', brand.img(`tournament:${e.id}`, 20, e.name), e.name);
    b.type = 'button'; b.addEventListener('click', () => nav.tournament(e.id)); return b;
  }))) : null;
  return h('div', 'panel-body', head, body, edBlock, legend(db));
}

const KIND = { country: 'Country', subdivision: 'Province / state', region: 'Hockey region' };

export function territoryPanel(db, tid, nav, quality) {
  const t = db.territories.get(tid);
  if (!t) return notFound(`Territory "${tid}" is not in the database.`);
  const list = leaguesIn(db, tid);
  const parent = t.parent ? db.territories.get(t.parent) : null;

  const top = list.filter((x) => tierRank(x.league) < 99)[0]?.league;

  // Teams: only clubs in the database that are located in this territory.
  // League team counts are not summed - multinational leagues would be over-counted.
  const scope = new Set([tid, ...children(db, tid).map((c) => c.id)]);
  const units = new Set(geoUnits(db, tid));
  const clubs = [...db.teams.values()].filter((c) => scope.has(c.territory) || units.has(c.geo));
  const noList = list.filter((x) => !(x.league.clubs ?? []).length && x.league.kind !== 'international').length;

  const head = h('header', 'panel-head',
    h('p', 'eyebrow', KIND[t.kind] ?? 'Territory', parent ? ` · ${parent.name}` : ''),
    h('h2', null, t.name));
  if (quality === 'approximate') head.append(h('p', 'warn', 'Map outline is approximate for this image.'));
  if (quality === 'none') head.append(h('p', 'warn', 'No map boundary for this territory yet.'));

  const stats = h('div', 'stats',
    stat('Highest level', top ? top.shortName : '—', top ? top.tier?.value : null),
    stat('Supported leagues', String(list.length)),
    stat('Known teams', clubs.length ? String(clubs.length) : '—',
      noList ? `${noList} league${noList === 1 ? '' : 's'} without a club list` : clubs.length ? 'in the sample database' : null));

  const leagues = h('section', 'block', h('h3', null, 'Leagues'));
  if (!list.length) leagues.append(h('p', 'empty', 'No supported leagues in this territory yet.'));
  else {
    const ul = h('ul', 'league-list');
    for (const { league: lg, via } of list) {
      const btn = h('button', 'league-row', badgeImg(lg, 40),
        h('span', 'league-row-text',
          h('strong', null, lg.name),
          h('span', null, [lg.tier?.value, typeof lg.teamCount?.value === 'number' ? `${lg.teamCount.value} teams` : null,
            via ? `in ${via.map((v) => db.territories.get(v)?.name ?? v).join(', ')}` : null].filter(Boolean).join(' · '))),
        lg.multinational ? h('span', 'tag', 'Multinational') : null);
      btn.type = 'button';
      btn.addEventListener('click', () => nav.league(lg.id));
      ul.append(h('li', null, btn));
    }
    leagues.append(ul);
  }

  const regions = [...db.territories.values()].filter((r) => r.kind === 'region' && (r.members ?? []).includes(tid));
  const kids = [...db.territories.values()].filter((c) => c.parent === tid);
  const related = h('section', 'block');
  if (kids.length || regions.length) {
    related.append(h('h3', null, kids.length ? 'Areas' : 'Part of'));
    const wrap = h('div', 'chips');
    for (const r of [...kids, ...regions]) {
      const b = h('button', 'chip-link', r.name);
      b.type = 'button';
      b.addEventListener('click', () => nav.territory(r.id));
      wrap.append(b);
    }
    related.append(wrap);
  }

  const facts = h('section', 'block', h('h3', null, 'Career outlook'), h('dl', 'facts',
    fact('Financial strength', t.financialStrength),
    fact('Typical salary range', t.salaryRange),
    fact('Player development', t.development),
    fact('Career accessibility', t.accessibility),
    fact('Restrictions & eligibility', t.restrictions)));

  const country = t.kind === 'country' ? (t.iso3 ?? (t.geo ?? [])[0]) : null;
  return h('div', 'panel-body', head, stats, leagues, related, nationalBlock(db, country, nav), facts, legend(db));
}

export function leaguePanel(db, lid, nav) {
  const lg = db.leagues.get(lid);
  if (!lg) return notFound(`League "${lid}" is not in the database.`);
  const cov = coverage(db, lg);
  const head = h('header', 'panel-head league-head', badgeImg(lg, 72),
    h('div', null,
      h('p', 'eyebrow', lg.kind ? lg.kind[0].toUpperCase() + lg.kind.slice(1) : 'League', lg.multinational ? ' · Multinational' : ''),
      h('h2', null, lg.name),
      h('p', 'sub', lg.shortName)));
  head.append(provenance(`league:${lg.id}`, lg.shortName));

  const stats = h('div', 'stats',
    stat('Tier', lg.tier?.level > 0 ? `Tier ${lg.tier.level}` : '—', lg.tier?.value),
    stat('Teams', typeof lg.teamCount?.value === 'number' ? String(lg.teamCount.value) : '—', lg.teamCount?.asOf ?? null),
    stat('Season', lg.season?.value ?? '—'));

  const cal = h('a', 'calendar-link', 'Schedule, results & standings ›');
  cal.href = `calendar.html?game=${encodeURIComponent(db.id)}#/table/${encodeURIComponent(lg.id)}`;

  const covEl = h('section', 'block', h('h3', null, 'Coverage'));
  const chips = h('div', 'chips');
  for (const id of lg.territories ?? []) {
    const t = db.territories.get(id);
    const b = h('button', 'chip-link', t?.name ?? id);
    b.type = 'button';
    b.addEventListener('click', () => nav.territory(id));
    chips.append(b);
  }
  covEl.append(chips);
  const extra = cov.filter((c) => !(lg.territories ?? []).includes(c));
  if (extra.length) covEl.append(h('p', 'note', `Includes ${extra.map((c) => db.territories.get(c)?.name ?? c).join(', ')}.`));

  const facts = h('section', 'block', h('h3', null, 'Details'), h('dl', 'facts',
    fact('Competitive tier', lg.tier),
    fact('Number of teams', lg.teamCount),
    fact('Current season', lg.season),
    fact('Typical salary range', lg.salary),
    fact('Career opportunities', lg.career),
    fact('Eligibility', lg.eligibility)));

  const clubs = h('section', 'block', h('h3', null, 'Clubs'));
  const ids = (lg.clubs ?? []).filter((c) => db.teams.has(c));
  if (!ids.length) clubs.append(h('p', 'empty', 'Club list not in the sample database yet.'));
  else {
    const first = db.teams.get(ids[0]);
    const withLogo = ids.filter((c) => brand.src(`club:${c}`).kind !== 'fallback').length;
    clubs.append(h('p', 'clubs-status', chip({ status: first.status, asOf: first.asOf, note: first.source ?? 'Club line-ups change between seasons' }),
      ` ${ids.length} clubs · ${withLogo} with a cleared logo`));
    const ul = h('ul', 'club-list');
    for (const id of [...ids].sort((a, b) => db.teams.get(a).name.localeCompare(db.teams.get(b).name))) {
      const t = db.teams.get(id);
      ul.append(h('li', null, clubMark(t.id, t.name), h('strong', null, t.name), h('span', null, t.city ?? t.countryName ?? '')));
    }
    clubs.append(ul);
  }
  return h('div', 'panel-body', head, stats, cal, covEl, facts, clubs, legend(db));
}

function legend(db) {
  const wrap = h('footer', 'panel-legend');
  for (const s of ['reference', 'placeholder', 'unknown']) wrap.append(chip({ status: s }));
  if (db.game.dataNotice) wrap.append(h('p', null, db.game.dataNotice));
  return wrap;
}

function notFound(msg) {
  return h('div', 'panel-body', h('header', 'panel-head', h('h2', null, 'Not found')), h('p', 'empty', msg));
}
