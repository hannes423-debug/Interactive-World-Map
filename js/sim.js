// League simulator: results and standings for a career save.
//
// Every result is a pure function of (career seed, game key), so a save only
// stores its seed, the current date and any results reported by the game
// itself (career.results); re-opening a save reproduces the same season.

import { rules } from './season.js';

/** 32-bit string hash (FNV-1a) -> seed. */
function hash(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 0x01000193);
  return h >>> 0;
}

function rng(seed) {  // mulberry32
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function poisson(r, lambda) {
  const L = Math.exp(-lambda);
  let k = 0, p = 1;
  do { k++; p *= r(); } while (p > L);
  return k - 1;
}

/** Placeholder rating: league strength plus a fixed per-club offset for this career. */
export function rating(career, season, teamId, leagueId) {
  const r = rng(hash(`${career.seed}|rating|${teamId}`));
  const gauss = Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r());
  return season.leagues.get(leagueId).rules.strength + gauss * 5;
}

/** Result of a game: { h, a, end: 'REG'|'OT'|'SO', reported } or null if not played yet. */
export function result(career, season, g, teams) {
  if (career.results?.[g.key]) return { ...career.results[g.key], reported: true };
  if (g.date >= career.date) return null;
  const r = rng(hash(`${career.seed}|${g.key}`));
  const lg = season.leagues.get(g.league).rules;
  const rh = rating(career, season, g.home, teams.get(g.home)?.league ?? g.league);
  const ra = rating(career, season, g.away, teams.get(g.away)?.league ?? g.league);
  const d = (rh - ra) / 22 + 0.1;  // home ice
  let h = poisson(r, lg.goals * Math.exp(d / 2));
  let a = poisson(r, lg.goals * Math.exp(-d / 2));
  let end = 'REG';
  if (h === a) {
    const homeWins = r() < 1 / (1 + Math.exp(-d));
    end = r() < 0.6 ? 'OT' : 'SO';
    if (homeWins) h++; else a++;
  }
  return { h, a, end, reported: false };
}

/** Standings rows for a league as of the career date. */
export function standings(career, season, leagueId, teams) {
  const entry = season.leagues.get(leagueId);
  const three = entry.rules.points === '3pt';
  const rows = new Map(entry.clubs.map((id) => [id, { id, gp: 0, w: 0, otw: 0, otl: 0, l: 0, gf: 0, ga: 0, pts: 0, form: [] }]));
  for (const g of entry.games) {
    const res = result(career, season, g, teams);
    if (!res) continue;
    for (const [id, gf, ga] of [[g.home, res.h, res.a], [g.away, res.a, res.h]]) {
      const row = rows.get(id);
      if (!row) continue;  // the other side of an inter-league game
      row.gp++; row.gf += gf; row.ga += ga;
      const won = gf > ga;
      if (res.end === 'REG') { if (won) { row.w++; row.pts += three ? 3 : 2; } else row.l++; }
      else if (won) { row.otw++; row.pts += 2; }
      else { row.otl++; row.pts += 1; }
      row.form.push(won ? 'W' : res.end === 'REG' ? 'L' : 'O');
    }
  }
  return [...rows.values()]
    .map((r) => ({ ...r, form: r.form.slice(-5) }))
    .sort((x, y) => y.pts - x.pts || x.gp - y.gp || (y.w - x.w) || (y.gf - y.ga) - (x.gf - x.ga) || y.gf - x.gf
      || (teams.get(x.id)?.name ?? '').localeCompare(teams.get(y.id)?.name ?? ''));
}
