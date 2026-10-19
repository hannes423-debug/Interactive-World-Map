# Interactive World Map

A reusable, static (no build, no backend) map interface for choosing where a game career starts: world map → region → territory → league → teams. Each game brings its own data files; the map images, boundaries and interface are shared.

The first game is **NHL 13 · Modern Career** (the NHL 13 PC port's modern career mode, starting with the 2026–27 season). The hockey engine lives in the separate NHL13Research repository; this repo only contains the career map.

- `index.html` – landing page listing the games
- `career-map.html?game=nhl13` – the map (`#/world`, `#/europe/t/swe/info`, `#/europe/l/shl`, …)

## Run it locally

The page loads JSON with `fetch`, which browsers block on `file://`, so serve the folder over HTTP. Any static server works:

```sh
cd Interactive-World-Map
python3 -m http.server 8000
# open http://localhost:8000/career-map.html?game=nhl13
```

No Node.js, npm or build step is needed to run or host the map.

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
assets/maps/                     background images (see below)
assets/badges/placeholder/       generated placeholder league badges
data/maps.json                   map images, sizes and calibration (shared by all games)
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
- **Team** (`teams.json`): `id`, `name`, `city`, `league`, `territory`, `geo`.
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
