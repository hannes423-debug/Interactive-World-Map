# Interactive World Map

A reusable, static (no build, no backend) map interface for choosing where a game career starts: world map → region → territory → league → teams. Each game brings its own data files; the map images, boundaries and interface are shared.

https://hannes423-debug.github.io/Interactive-World-Map/

- `index.html` – landing page listing the games
- `career-map.html?game=nhl13` – the map (`#/world`, `#/europe/t/swe/info`, `#/europe/l/shl`, …)
- `calendar.html?game=nhl13` – career calendar, standings and simulator (`#/day/all/2026-10-10`, `#/table/shl`, `#/team/frolunda-hc`, …)

## Run it locally

The page loads JSON with `fetch`, which browsers block on `file://`, so serve the folder over HTTP. Any static server works:

```sh
cd Interactive-World-Map
python3 -m http.server 8000
# open http://localhost:8000/career-map.html?game=nhl13
```

No Node.js, npm or build step is needed to run or host the map.

## Career calendar and league simulator

`calendar.html?game=nhl13` is the season view: a day-by-day calendar of every league, standings, club schedules and a simulator that advances the whole hockey world (Sim day / week / to a date / to the user's next game / to season end). Each league panel on the map links to it.

**Fixtures.** `data/hockey/fixtures/2026-27/<league>.json` holds the published 2026–27 regular-season schedules, with venue-local dates and start times exactly as the leagues issue them, and `index.json` records each source and fetch date. Refresh them with:

```sh
python3 tools/fixtures/fetch_fixtures.py            # all leagues with a source
python3 tools/fixtures/fetch_fixtures.py --only shl # one league
```

| Official source | Leagues |
|---|---|
| NHL (api-web.nhle.com) | NHL |
| HockeyTech league feeds | AHL, ECHL, OHL, WHL, QMJHL, USHL |
| League sites | SHL (shl.se), HockeyAllsvenskan (hockeyallsvenskan.se), Liiga (liiga.fi), Mestis (mestis.fi), National League (nationalleague.ch), PENNY DEL (penny-del.org), DEL2 (del-2.org), Tipsport extraliga (hokej.cz), Tipsport liga SVK (hockeyslovakia.sk), ICE Hockey League (ice.hockey feed), KHL (khl.ru), VHL (vhlru.ru) |

KHL and VHL times are Moscow time (shown as MSK). hokej.cz and vhlru.ru stop showing the start time once a game has been played, so those games keep their date only. The MHL and the Swiss League have no complete published schedule that can be read automatically (the MHL site pages its calendar per session, and the SIHF data service only returns the current day), so both use generated schedules for now.

Every source club must match a club in `teams.json` (by name, or `tools/fixtures/aliases.json`). If one doesn't, that league is not written. A league without a fixtures file gets a generated double round-robin. The calendar labels it **Simulated schedule**, and each of its games carries a *Sim fixture* tag, so a generated schedule is never presented as the real one.

**Results.** All results are simulated. A result depends only on the career's seed and the game, so the same save always replays the same season. Club ratings are placeholders (league strength plus a fixed per-club offset) until rosters exist. Points follow each league's system: 3-2-1 for SHL, Liiga, NL, DEL and similar leagues, and 2 points per win plus 1 for an overtime loss elsewhere.

**Career save** (stored in the browser; *Career… → Export / Import save*):

```json
{ "format": "iwm-career/1", "game": "nhl13", "season": "2026–27", "seed": 42,
  "date": "2026-12-15", "team": "frolunda-hc",
  "results": { "shl:<game id>": { "h": 3, "a": 2, "end": "OT" } } }
```

`date` is the next day to be played: games before it are final. `results` overrides the simulator for games played in the actual game. Keys are `<league>:<id>` from the fixtures file, and `end` is `REG`, `OT` or `SO`. This is the hook for the NHL 13 port: write the user's played games into `results`, then import the save.

## League editor

`editor.html` edits leagues, teams, logos and map positions, with the game view open next to it (it reloads on every save). It needs its local server, which keeps the data in a separate league database folder:

```sh
python3 tools/editor/server.py --db /path/to/LeagueDatabase
# editor:    http://127.0.0.1:8765/editor.html
# game view: http://127.0.0.1:8765/career-map.html?game=nhl13&live=1
```

See [EDITOR-GUIDE.md](EDITOR-GUIDE.md) for the full guide, including what images to use.

## Publish with GitHub Pages

1. Push the repository to GitHub.
2. *Settings → Pages → Build and deployment*: Source **Deploy from a branch**, branch `main` (or the branch you want), folder `/ (root)`.
3. The site appears at `https://<user>.github.io/Interactive-World-Map/` and the map at `…/Interactive-World-Map/career-map.html?game=nhl13`.

All asset paths are relative, so the site works under a project sub-path. Routes live in the URL hash, so refreshing or opening a deep link works without server rewrites. The `.nojekyll` file stops Jekyll from processing the site.

## Layout

```
index.html, career-map.html      pages
css/career-map.css               styles
js/                              ES modules, no dependencies
  main.js      routing, header, breadcrumbs, panels
  map.js       map stage: image, territory layer, badge layer, camera, transitions
  panel.js     territory and league information panels
  data.js      loads a game's data, builds indexes, resolves geometry
  projection.js  lon/lat → image pixels (twin of tools/geo/projections.py)
  router.js    hash routes
  calendar.js  career calendar page; season.js fixtures + rules; sim.js results + standings
assets/maps/                     background images (see below)
assets/badges/placeholder/       generated placeholder league badges
data/maps.json                   map images, sizes and calibration (shared by all games)
data/hockey/fixtures/2026-27/    published league schedules (tools/fixtures/fetch_fixtures.py)
data/geo/                        boundary data (shared by all games)
  countries.json, subdivisions.json   Natural Earth lon/lat outlines
  views/<map>.json                    outlines traced to each image, in image pixels
games/<game>/                    one folder per game
  game.json  territories.json  leagues.json  teams.json  badges.json
games/test-missing-data/         broken-on-purpose fixture used by the tests
tools/                           optional dev tools (Python / Node), never needed at runtime
```

## Map assets

| View | File | Size |
|---|---|---|
| World | `assets/maps/world.png` | 1672 × 940 |
| North America | `assets/maps/north-america.png` | 1672 × 941 |
| Europe | `assets/maps/europe.png` | 1672 × 940 |
| Russia & Eurasia | `assets/maps/eurasia.png` | 1672 × 940 |

These are the supplied images, byte-for-byte; they were only given descriptive file names. They are drawn at their own aspect ratio (never stretched): the map fills the screen when the window has a similar shape ("cover"), and on very different shapes (e.g. a portrait phone) it zooms part-way and can be dragged.

To replace an image, keep the file name (or change `image` in `data/maps.json`), then re-run the calibration (see *Correcting territory boundaries*).

## Data model

Everything is linked by stable ids, never by display names.

- **Territory** (`territories.json`): `id`, `name`, `kind` (`country`, `subdivision`, `region`), `geo` (boundary ids: ISO alpha-3 country codes such as `SWE`, or ISO 3166-2 codes such as `CA-ON`), `views` (maps it appears on), `homeView`, optional `parent` and `members`, plus career fields.
  - Subdivisions use `parent` (e.g. Ontario → Canada). Canada, the USA and Russia have province/state outlines ready; add a territory to use one.
  - Hockey regions that do not follow political borders use `kind: "region"` and either `geo` (several units) or `members` (other territories), e.g. `alps-adriatic` or `maritimes`.
- **League** (`leagues.json`): `territories` (a league can span several, including regions), `tier`, `teamCount`, `season`, `salary`, `career`, `eligibility`, `clubs` (team ids), `logo` / `placeholderBadge`.
- **Team** (`teams.json`): `id`, `name`, `city`, `league`, `territory`, `geo`, `lonlat` (`[longitude, latitude]` of the home city: with a league open, each club's logo is drawn there), optional `position` (per-map pixel nudge) and `logo` (overrides the branding library).
- **Badge** (`badges.json`): where a league thumbnail appears (see below).

### Verified data vs placeholders

Every informational value is stored as `{ "value": …, "status": …, "asOf"?, "note"? }` and the panels show the status next to it:

| status | meaning |
|---|---|
| `verified` | checked against a cited source (none yet) |
| `reference` | widely reported real-world fact, **not re-verified for 2026–27** (team counts and club lists as of 2025–26) |
| `placeholder` | game-design value (ratings, salary ranges) – not real-world data |
| `game` | defined by the career mode (e.g. the season) |
| `unknown` | no data yet; the UI says so instead of guessing |

Salary ranges and financial / accessibility ratings in the sample data are game-balance placeholders, not real contract or financial figures.

## How to…

### Add a territory

1. Add an entry to `games/<game>/territories.json`:
   ```json
   { "id": "nor", "name": "Norway", "kind": "country", "geo": ["NOR"],
     "views": ["world", "europe"], "homeView": "europe" }
   ```
   `geo` ids come from `data/geo/views/<map>.json` (open it and search for the name). Career fields (`financialStrength`, `salaryRange`, `development`, `accessibility`, `restrictions`) are optional.
2. To make it clickable on a map, add its id to that view's `territories` list in `games/<game>/game.json`. Subdivisions and regions do not need this: subdivisions appear when their parent is selected, and regions are listed in the side list and in league coverage.
3. A territory with no boundary (`"geo": []`) still works: it is listed in the side list and its panel says the boundary is missing. If a boundary id exists in the lon/lat data but was not traced for a map, the outline is projected through the calibration and drawn dashed as approximate.

### Add a league

1. Add an entry to `games/<game>/leagues.json` with a new `id`, `territories` (territory ids – regions allowed), `homeView`, and the info fields. Unknown values: use `{ "value": null, "status": "unknown" }`.
2. Optional clubs: add teams to `teams.json` and list their ids in the league's `clubs`.
3. Logo: set `"logo": "assets/badges/<file>.png"`. Without a logo a placeholder is used; generate one with `python3 tools/data/make_placeholder_badges.py nhl13` (it writes `assets/badges/placeholder/<id>.svg`, clearly marked PLACEHOLDER).
4. Add a badge (next section) if it should appear on the map. Leagues without a badge are still reachable from territory panels.

### Position a league thumbnail

Badges live in `games/<game>/badges.json`, separate from the images:

```json
{ "id": "badge-shl", "league": "shl", "image": null,
  "views": ["world", "europe"], "minLevel": "world",
  "anchor": [15.5, 62.5], "position": { "europe": [760, 300] },
  "priority": 80, "action": { "type": "league", "id": "shl" } }
```

- `anchor` – `[longitude, latitude]`; projected onto every map through its calibration, so one value works on all views.
- `position` – optional per-view pixel override in the image's own pixel coordinates (e.g. read from an image editor). It wins over `anchor`.
- `views` – maps the badge can appear on. `minLevel` – `world` (visible from the world map down), `region` (region maps), or `territory` (only when a territory where the league plays is selected). This keeps the world map to the main competitions.
- `priority` – higher badges get their preferred spot first when badges would overlap; the others move to a nearby free slot, connected to their anchor by a short line.
- `image` – optional badge-specific image; otherwise the league `logo`, then its placeholder.
- `action` – `league` (default), `territory` or `view`, each with an `id`.

### Correct territory boundaries

Boundaries are data, kept apart from the images, and can be fixed at three levels:

1. **Edit one outline directly** – each unit in `data/geo/views/<map>.json` is an SVG path (`d`) in image pixels. Edit it in any SVG editor: make an SVG with the map image as background and the path on top, adjust, copy the new `d` back. The file is regenerated by the tracer, so keep a note of hand edits or stop re-running the tracer for that map.
2. **Re-trace against the artwork** – `python3 tools/geo/trace_views.py <map>`. Outlines snap to the borders painted in the image (seeded watershed). `traceMaxErode` in `data/maps.json` sets how far (px) a border may move to find a painted line.
3. **Re-calibrate the projection** – add or fix landmarks in `tools/geo/control_points.json` (`lon`, `lat`, image `px`), then `python3 tools/geo/calibrate.py <map>` and re-trace. `controlPointWeight` in `data/maps.json` sets how strongly landmarks hold against coastline matching.

Check the result with `python3 tools/geo/check_alignment.py` (share of each territory outline lying on a painted line) and the overlays it writes to `tools/geo/out/`.

The Python tools need `numpy scipy opencv-python-headless scikit-image Pillow`. Boundary source data (Natural Earth 1:50m, public domain) is rebuilt with `python3 tools/geo/build_geo.py`.

## Branding library

League, club, federation, national-team, tournament and flag identities live in `assets/branding/`:

```
assets/branding/
  manifest.json            every asset: source, licence, identity check, technical checks, outputs
  masters/<type>s/         original files (SVG preferred) that may be published
  generated/<type>/        PNG variants: 128, 256, 512, 1024 px canvases (flags keep their proportions)
  validation-report.json   machine-readable result of the last processing run
  validation-report.md     readable summary
  contact-sheet.html       every entity on one page for visual review
  local/                   git-ignored: files kept locally that are not cleared for publication
```

Club membership for 2026–27 is in `data/hockey/memberships-2026-27.json` (one stable id per club, used by the game data, the manifest and the UI). Each competition cites the Wikipedia season article it was read from.

**How assets are chosen.** For every entity the tools read the logo currently shown in its Wikipedia infobox. If that file is on Wikimedia Commons under a public-domain tag (typically `PD-textlogo`) or a free licence, it is downloaded and published. If it is a non-free (fair-use) file, it is *not* redistributed: the manifest records the source and `rights.status = "restricted"`, and the tools look for a freely licensed Commons file that visually matches the current logo (score ≥ 0.80). Without a match the map shows a consistent generic badge and says why.

Rights statuses: `public_domain` and `licensed` (publishable), `restricted` (non-free; not redistributed), `unverified` (e.g. "public domain in the US only"), `permission_required`. Public-domain status refers to copyright only; logos remain trademarks of their owners and their use here does not imply endorsement.

Identity statuses: `verified_secondary` (the file shown in the current Wikipedia infobox), `verified_visual` (free file matched to it visually), `not_current` (older identity kept as an alternate), `unverified`.

### Updating the library

```sh
pip install pillow numpy resvg-py          # resvg-py renders SVG without system libraries
python3 tools/branding/discover_members.py  # 2026-27 participants -> tools/branding/out/members-candidates.json
python3 tools/branding/curate_members.py    # -> data/hockey/memberships-2026-27.json (overrides.json for fixes)
python3 tools/branding/commons_pool.py      # free logo files on Commons -> tools/branding/out/commons-pool.json
python3 tools/branding/fetch.py             # acquire + manifest   (--only liiga,khl,flag ...)
python3 tools/branding/process.py           # validate + generate PNG variants + reports
python3 tools/branding/contact_sheet.py     # contact-sheet.html (+ PNG sheets in tools/branding/out)
python3 tools/branding/build_game_data.py   # memberships -> games/nhl13/{teams,leagues,badges}.json
```

All network access is cached in `tools/branding/.cache/` and paced; Wikimedia throttles bulk downloads, so a full run can take hours.

**Add or replace one asset by hand.** Put the file in `assets/branding/masters/<type>s/<id>.svg` and add or edit its entry in `manifest.json` (copy an existing one): set `master`, `source` (where it came from), `rights` (`status`, `basis`, `publish`) and `identity`. Point `entities["club:<id>"].active` at it; keep the previous asset under `alternates` (with `season`) instead of deleting it. Then run `process.py`. Never mark an asset `public_domain` or `licensed` without a documented basis.

**Locally kept files that may not be published.** `python3 tools/branding/fetch.py --include-restricted` also saves non-free current logos under `assets/branding/local/` (git-ignored) and lists them in `local/manifest.local.json`. Open the map with `?branding=local` (e.g. `career-map.html?game=nhl13&branding=local`) to use them on your own machine. They never reach the public site.

## Testing

```sh
node tools/test/verify.mjs   # needs the `playwright` package and a Chromium
```

It serves the repo under `/Interactive-World-Map/` (like GitHub Pages) and checks image loading, navigation and back/Escape/browser-back, hover and selection, info panels, badge positions, league panels, the broken-data fixture, unknown routes, layouts from 1920×1080 down to 390×844, and that no request leaves the project sub-path. Screenshots go to `tools/test/out/`.

## Known limitations

- The images are stylised artwork rather than exact projections. Outlines follow the painted borders closely on the World, North America and Europe maps. On Russia & Eurasia the painted borders are fainter and the geography more distorted, so Belarus, Kazakhstan and China are less exact there: about 70–80 % of their outline lies within 2 px of a painted line, against 95–100 % for the other territories (Russia: about 88 % on both the Europe and Eurasia maps). Measured with `tools/geo/check_alignment.py`; the line detector also picks up some terrain texture, so treat the numbers as indicative.
- Russian federal subjects are traced but the artwork shows few of their borders, so their outlines on the Eurasia map are approximate. No Russian subdivision is used as a career territory yet.
- Zooming into small territories enlarges the 1672 px wide images up to 2.4×, which softens them. Higher-resolution versions of the same artwork would fix this without code changes.
- The sample database is small and its real-world values are unverified references (see above). League logos are placeholders.
