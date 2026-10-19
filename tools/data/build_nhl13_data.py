#!/usr/bin/env python3
"""One-off generator for the initial NHL 13 sample database (games/nhl13/*.json).

The JSON files are the source of truth from now on - edit them directly.
This script is kept only to document how the first version was produced and
is NOT meant to be re-run over hand edits.
"""
import json
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "games", "nhl13")

REF = "reference"      # widely reported real-world fact, not re-verified for 2026-27
PH = "placeholder"     # game-design value, not a real-world fact
UNK = "unknown"
AS_OF = "2025–26"


def ref(value, note=None):
    d = {"value": value, "status": REF, "asOf": AS_OF}
    if note:
        d["note"] = note
    return d


def ph(value, note=None):
    d = {"value": value, "status": PH}
    if note:
        d["note"] = note
    return d


def unk(note=None):
    d = {"value": None, "status": UNK}
    if note:
        d["note"] = note
    return d


# ------------------------------------------------------------------ teams
teams = []


def add_teams(league, rows):
    ids = []
    for tid, name, city, geo, terr in rows:
        teams.append({"id": f"{league}-{tid}", "name": name, "city": city, "league": league,
                      "territory": terr, "geo": geo, "status": REF, "asOf": AS_OF})
        ids.append(f"{league}-{tid}")
    return ids


nhl_rows = [
    ("ana", "Anaheim Ducks", "Anaheim", "US-CA", "usa"), ("bos", "Boston Bruins", "Boston", "US-MA", "usa"),
    ("buf", "Buffalo Sabres", "Buffalo", "US-NY", "usa"), ("cgy", "Calgary Flames", "Calgary", "CA-AB", "ca-ab"),
    ("car", "Carolina Hurricanes", "Raleigh", "US-NC", "usa"), ("chi", "Chicago Blackhawks", "Chicago", "US-IL", "usa"),
    ("col", "Colorado Avalanche", "Denver", "US-CO", "usa"), ("cbj", "Columbus Blue Jackets", "Columbus", "US-OH", "usa"),
    ("dal", "Dallas Stars", "Dallas", "US-TX", "usa"), ("det", "Detroit Red Wings", "Detroit", "US-MI", "us-mi"),
    ("edm", "Edmonton Oilers", "Edmonton", "CA-AB", "ca-ab"), ("fla", "Florida Panthers", "Sunrise", "US-FL", "usa"),
    ("lak", "Los Angeles Kings", "Los Angeles", "US-CA", "usa"), ("min", "Minnesota Wild", "Saint Paul", "US-MN", "usa"),
    ("mtl", "Montréal Canadiens", "Montréal", "CA-QC", "ca-qc"), ("nsh", "Nashville Predators", "Nashville", "US-TN", "usa"),
    ("njd", "New Jersey Devils", "Newark", "US-NJ", "usa"), ("nyi", "New York Islanders", "Elmont", "US-NY", "usa"),
    ("nyr", "New York Rangers", "New York", "US-NY", "usa"), ("ott", "Ottawa Senators", "Ottawa", "CA-ON", "ca-on"),
    ("phi", "Philadelphia Flyers", "Philadelphia", "US-PA", "us-pa"), ("pit", "Pittsburgh Penguins", "Pittsburgh", "US-PA", "us-pa"),
    ("sjs", "San Jose Sharks", "San Jose", "US-CA", "usa"), ("sea", "Seattle Kraken", "Seattle", "US-WA", "us-wa"),
    ("stl", "St. Louis Blues", "St. Louis", "US-MO", "usa"), ("tbl", "Tampa Bay Lightning", "Tampa", "US-FL", "usa"),
    ("tor", "Toronto Maple Leafs", "Toronto", "CA-ON", "ca-on"), ("uta", "Utah Mammoth", "Salt Lake City", "US-UT", "usa"),
    ("van", "Vancouver Canucks", "Vancouver", "CA-BC", "ca-bc"), ("vgk", "Vegas Golden Knights", "Paradise", "US-NV", "usa"),
    ("wsh", "Washington Capitals", "Washington, D.C.", "US-DC", "usa"), ("wpg", "Winnipeg Jets", "Winnipeg", "CA-MB", "ca-mb"),
]
shl_rows = [
    ("bry", "Brynäs IF", "Gävle", "SWE", "swe"), ("dif", "Djurgårdens IF", "Stockholm", "SWE", "swe"),
    ("fhc", "Frölunda HC", "Gothenburg", "SWE", "swe"), ("fbk", "Färjestad BK", "Karlstad", "SWE", "swe"),
    ("hv71", "HV71", "Jönköping", "SWE", "swe"), ("lif", "Leksands IF", "Leksand", "SWE", "swe"),
    ("lhc", "Linköping HC", "Linköping", "SWE", "swe"), ("lhf", "Luleå HF", "Luleå", "SWE", "swe"),
    ("mif", "Malmö Redhawks", "Malmö", "SWE", "swe"), ("rbk", "Rögle BK", "Ängelholm", "SWE", "swe"),
    ("ske", "Skellefteå AIK", "Skellefteå", "SWE", "swe"), ("tik", "Timrå IK", "Timrå", "SWE", "swe"),
    ("vax", "Växjö Lakers", "Växjö", "SWE", "swe"), ("ohk", "Örebro HK", "Örebro", "SWE", "swe"),
]
nl_rows = [
    ("ajo", "HC Ajoie", "Porrentruy", "CHE", "che"), ("hcap", "HC Ambrì-Piotta", "Ambrì", "CHE", "che"),
    ("scb", "SC Bern", "Bern", "CHE", "che"), ("ehcb", "EHC Biel-Bienne", "Biel/Bienne", "CHE", "che"),
    ("hcd", "HC Davos", "Davos", "CHE", "che"), ("fgo", "HC Fribourg-Gottéron", "Fribourg", "CHE", "che"),
    ("gsh", "Genève-Servette HC", "Geneva", "CHE", "che"), ("ehck", "EHC Kloten", "Kloten", "CHE", "che"),
    ("scl", "SCL Tigers", "Langnau im Emmental", "CHE", "che"), ("lhc", "Lausanne HC", "Lausanne", "CHE", "che"),
    ("hcl", "HC Lugano", "Lugano", "CHE", "che"), ("rjl", "SC Rapperswil-Jona Lakers", "Rapperswil-Jona", "CHE", "che"),
    ("zsc", "ZSC Lions", "Zürich", "CHE", "che"), ("evz", "EV Zug", "Zug", "CHE", "che"),
]
nhl_clubs = add_teams("nhl", nhl_rows)
shl_clubs = add_teams("shl", shl_rows)
nl_clubs = add_teams("nl", nl_rows)

# ---------------------------------------------------------------- leagues
TIER = {
    1: "Top professional league", 2: "Second-tier professional", 3: "Third-tier professional",
}


def league(lid, name, short, terr, home, tier, tier_label, teams_n, clubs=None, salary=None,
           career=None, eligibility=None, multinational=False, kind="professional"):
    return {
        "id": lid, "name": name, "shortName": short, "logo": None,
        "placeholderBadge": f"assets/badges/placeholder/{lid}.svg",
        "kind": kind, "multinational": multinational,
        "territories": terr, "homeView": home,
        "tier": dict(ref(tier_label), level=tier),
        "teamCount": teams_n,
        "season": {"value": "2026–27", "status": "game", "note": "Career mode start season"},
        "salary": salary or ph(None, "No salary data in the sample database yet"),
        "career": career or ph([], "Career notes not written yet"),
        "eligibility": eligibility or unk(),
        "clubs": clubs or [],
    }


leagues = [
    league("nhl", "National Hockey League", "NHL", ["usa", "can"], "north-america", 1, TIER[1],
           ref(32, "Includes the Utah Mammoth"), nhl_clubs,
           salary=ph("$0.8M – $12M per season", "Game-balance range for career mode, not real contract data"),
           career=ph(["Highest level in the career mode", "Entry via draft, free agency or AHL call-up"]),
           eligibility=ph("Drafted or signed as a free agent; age 18+ for NHL contracts in career mode"),
           multinational=True),
    league("ahl", "American Hockey League", "AHL", ["usa", "can"], "north-america", 2, "Top development league (NHL affiliates)",
           ref(32), salary=ph("$60k – $400k per season", "Game-balance range, not real contract data"),
           career=ph(["Main route to the NHL", "Most clubs are NHL affiliates"]), multinational=True),
    league("echl", "ECHL", "ECHL", ["usa", "can"], "north-america", 3, TIER[3],
           unk("Team count changes often through expansion and relocation; not yet verified"),
           multinational=True),
    league("whl", "Western Hockey League", "WHL", ["ca-bc", "ca-ab", "ca-sk", "ca-mb", "us-wa", "us-or"],
           "north-america", 4, "Major junior (CHL)", ref(23, "Includes the Penticton expansion team"),
           career=ph(["Ages 16–20", "Major-junior route to the NHL Draft"]),
           eligibility=ph("Ages 16–20 in career mode; CHL import rules apply"), multinational=True, kind="junior"),
    league("ohl", "Ontario Hockey League", "OHL", ["ca-on", "us-mi", "us-pa"], "north-america", 4,
           "Major junior (CHL)", ref(20), career=ph(["Ages 16–20", "Major-junior route to the NHL Draft"]),
           eligibility=ph("Ages 16–20 in career mode"), multinational=True, kind="junior"),
    league("qmjhl", "Quebec Maritimes Junior Hockey League", "QMJHL", ["ca-qc", "maritimes"], "north-america", 4,
           "Major junior (CHL)", ref(18), career=ph(["Ages 16–20", "Major-junior route to the NHL Draft"]),
           eligibility=ph("Ages 16–20 in career mode"), kind="junior"),
    league("ncaa", "NCAA Division I Men's Ice Hockey", "NCAA", ["usa"], "north-america", 4, "College",
           unk("Program count changes as schools add hockey; not yet verified"),
           salary=ph("No salary (amateur)", "Game rule; real-world NIL rules are not modelled"),
           career=ph(["Up to four seasons", "Keeps NHL draft rights open"]), kind="college"),
    league("ushl", "United States Hockey League", "USHL", ["usa"], "north-america", 5, "Junior (Tier I)",
           ref(16), kind="junior"),
    league("shl", "Swedish Hockey League", "SHL", ["swe"], "europe", 1, TIER[1], ref(14), shl_clubs,
           salary=ph("€70k – €700k per season", "Game-balance range, not real contract data"),
           career=ph(["Strong development reputation", "Promotion/relegation with HockeyAllsvenskan"])),
    league("allsvenskan", "HockeyAllsvenskan", "HA", ["swe"], "europe", 2, TIER[2], ref(14)),
    league("liiga", "Liiga", "Liiga", ["fin"], "europe", 1, TIER[1],
           unk("Not yet verified for 2026–27"),
           career=ph(["Closed league with licence system"])),
    league("czech-extraliga", "Czech Extraliga", "ELH", ["cze"], "europe", 1, TIER[1], ref(14)),
    league("nl", "National League", "NL", ["che"], "europe", 1, TIER[1], ref(14), nl_clubs,
           salary=ph("CHF 100k – 900k per season", "Game-balance range, not real contract data"),
           eligibility=ph("Import-player limit applies in career mode")),
    league("del", "Deutsche Eishockey Liga", "DEL", ["deu"], "europe", 1, TIER[1], unk("Not yet verified for 2026–27")),
    league("icehl", "ICE Hockey League", "ICEHL", ["alps-adriatic"], "europe", 1, "Top professional league (multinational)",
           unk("Club line-up changes between seasons; not yet verified"), multinational=True),
    league("eihl", "Elite Ice Hockey League", "EIHL", ["gbr", "gb-nir"], "europe", 1, TIER[1], ref(10)),
    league("champions", "Champions Hockey League", "CHL", ["europe-chl"], "europe", 0,
           "International club competition", ref(24),
           career=ph(["Qualification through domestic leagues", "Not a league you sign with directly"]),
           multinational=True, kind="international"),
    league("khl", "Kontinental Hockey League", "KHL", ["rus", "blr", "kaz", "chn"], "eurasia", 1,
           "Top professional league (multinational)", unk("Membership changes between seasons; not yet verified"),
           salary=ph("$100k – $3M per season", "Game-balance range, not real contract data"),
           multinational=True),
    league("vhl", "Supreme Hockey League", "VHL", ["rus", "kaz"], "eurasia", 2, TIER[2], unk(), multinational=True),
    league("mhl", "Junior Hockey League", "MHL", ["rus"], "eurasia", 4, "Junior", unk(), kind="junior"),
    league("belarus-extraleague", "Belarusian Extraleague", "BXL", ["blr"], "eurasia", 2, "Top domestic league", unk()),
    league("kazakhstan", "Kazakhstan Championship", "KAZ", ["kaz"], "eurasia", 2, "Top domestic league", unk()),
    league("asia-league", "Asia League Ice Hockey", "ALIH", ["jpn", "kor"], "eurasia", 1,
           "Top professional league (multinational)", unk(), multinational=True),
]

# ------------------------------------------------------------- territories
def terr(tid, name, geo, views, home, kind="country", parent=None, members=None, **info):
    t = {"id": tid, "name": name, "kind": kind, "geo": geo, "views": views, "homeView": home}
    if parent:
        t["parent"] = parent
    if members:
        t["members"] = members
    defaults = {
        "financialStrength": ph(None, "Not rated yet"),
        "salaryRange": ph(None, "No salary data yet"),
        "development": ph(None, "Not written yet"),
        "accessibility": ph(None, "Not rated yet"),
        "restrictions": unk(),
    }
    defaults.update(info)
    t.update(defaults)
    return t


def rating(n, label):
    return ph({"rating": n, "max": 5, "label": label}, "Game-design rating, not a real-world measurement")


territories = [
    # North America
    terr("can", "Canada", ["CAN"], ["world", "north-america"], "north-america",
         financialStrength=rating(5, "Very strong"), development=ph("Deepest junior system in the game: CHL major junior plus pro pathways."),
         accessibility=rating(4, "Open to most player types"), subdivisions=True),
    terr("usa", "United States", ["USA"], ["world", "north-america"], "north-america",
         financialStrength=rating(5, "Very strong"), development=ph("College (NCAA), USHL and major-junior teams in border states."),
         accessibility=rating(4, "Open to most player types"), subdivisions=True),
    terr("ca-bc", "British Columbia", ["CA-BC"], ["north-america"], "north-america", "subdivision", "can"),
    terr("ca-ab", "Alberta", ["CA-AB"], ["north-america"], "north-america", "subdivision", "can"),
    terr("ca-sk", "Saskatchewan", ["CA-SK"], ["north-america"], "north-america", "subdivision", "can"),
    terr("ca-mb", "Manitoba", ["CA-MB"], ["north-america"], "north-america", "subdivision", "can"),
    terr("ca-on", "Ontario", ["CA-ON"], ["north-america"], "north-america", "subdivision", "can"),
    terr("ca-qc", "Quebec", ["CA-QC"], ["north-america"], "north-america", "subdivision", "can"),
    terr("maritimes", "Maritime provinces", ["CA-NB", "CA-NS", "CA-PE"], ["north-america"], "north-america",
         "region", "can",
         development=ph("Grouped as one hockey region: New Brunswick, Nova Scotia and Prince Edward Island.")),
    terr("us-wa", "Washington", ["US-WA"], ["north-america"], "north-america", "subdivision", "usa"),
    terr("us-or", "Oregon", ["US-OR"], ["north-america"], "north-america", "subdivision", "usa"),
    terr("us-mi", "Michigan", ["US-MI"], ["north-america"], "north-america", "subdivision", "usa"),
    terr("us-pa", "Pennsylvania", ["US-PA"], ["north-america"], "north-america", "subdivision", "usa"),
    # Europe
    terr("swe", "Sweden", ["SWE"], ["world", "europe"], "europe",
         financialStrength=rating(4, "Strong"), development=ph("Renowned junior development (J20 Nationell) feeding SHL clubs."),
         accessibility=rating(4, "Good for young players")),
    terr("fin", "Finland", ["FIN"], ["world", "europe"], "europe", financialStrength=rating(3, "Solid"),
         accessibility=rating(4, "Good for young players")),
    terr("nor", "Norway", ["NOR"], ["world", "europe"], "europe"),
    terr("dnk", "Denmark", ["DNK"], ["world", "europe"], "europe"),
    terr("deu", "Germany", ["DEU"], ["world", "europe"], "europe", financialStrength=rating(4, "Strong")),
    terr("che", "Switzerland", ["CHE"], ["world", "europe"], "europe", financialStrength=rating(5, "Very strong"),
         restrictions=ph("Import-player limit applies in career mode", "Game rule; real-world limits not verified")),
    terr("cze", "Czechia", ["CZE"], ["world", "europe"], "europe", financialStrength=rating(3, "Solid")),
    terr("svk", "Slovakia", ["SVK"], ["world", "europe"], "europe"),
    terr("aut", "Austria", ["AUT"], ["world", "europe"], "europe"),
    terr("ita", "Italy", ["ITA"], ["world", "europe"], "europe"),
    terr("svn", "Slovenia", ["SVN"], ["world", "europe"], "europe"),
    terr("hun", "Hungary", ["HUN"], ["world", "europe"], "europe"),
    terr("fra", "France", ["FRA"], ["world", "europe"], "europe"),
    terr("gbr", "United Kingdom", ["GBR"], ["world", "europe"], "europe"),
    terr("gb-nir", "Northern Ireland", [], ["europe"], "europe", "subdivision", "gbr",
         development=ph("Home of an EIHL club. No separate boundary in the map data yet - shown as part of the United Kingdom.")),
    terr("pol", "Poland", ["POL"], ["world", "europe"], "europe"),
    terr("lva", "Latvia", ["LVA"], ["world", "europe"], "europe"),
    terr("alps-adriatic", "Alps–Adriatic hockey region", ["AUT", "ITA", "SVN", "HUN"], ["europe"], "europe",
         "region", members=["aut", "ita", "svn", "hun"],
         development=ph("Cross-border region used by the ICE Hockey League; not a political territory.")),
    terr("europe-chl", "Champions Hockey League area", [], ["europe"], "europe", "region",
         members=["swe", "fin", "che", "deu", "cze", "svk", "aut", "nor", "dnk", "fra", "gbr", "pol", "lva", "ita", "svn", "hun"],
         development=ph("Competition area of the Champions Hockey League; participating countries vary by season.")),
    # Russia & Eurasia
    terr("rus", "Russia", ["RUS"], ["world", "europe", "eurasia"], "eurasia",
         financialStrength=rating(4, "Strong"), accessibility=rating(3, "Limited for imports"), subdivisions=True),
    terr("blr", "Belarus", ["BLR"], ["world", "europe", "eurasia"], "eurasia"),
    terr("kaz", "Kazakhstan", ["KAZ"], ["world", "eurasia"], "eurasia"),
    terr("chn", "China", ["CHN"], ["world", "eurasia"], "eurasia"),
    terr("jpn", "Japan", ["JPN"], ["world", "eurasia"], "eurasia"),
    terr("kor", "South Korea", ["KOR"], ["world", "eurasia"], "eurasia"),
]

game = {
    "id": "nhl13",
    "title": "NHL 13 · Modern Career",
    "subtitle": "Choose where your career begins",
    "season": "2026–27",
    "rootView": "world",
    "views": {
        "world": {"title": "World", "map": "world", "level": "world",
                  "regions": ["north-america", "europe", "eurasia"]},
        "north-america": {"title": "North America", "map": "north-america", "level": "region",
                          "worldUnits": ["CAN", "USA"],
                          "territories": ["can", "usa"]},
        "europe": {"title": "Europe", "map": "europe", "level": "region",
                   "worldUnits": ["SWE", "FIN", "NOR", "DNK", "DEU", "CHE", "CZE", "SVK", "AUT", "ITA", "SVN", "HUN",
                                  "FRA", "GBR", "POL", "LVA", "BLR", "IRL", "NLD", "BEL", "ESP", "PRT", "EST", "LTU",
                                  "UKR", "ROU", "BGR", "SRB", "HRV", "BIH", "MNE", "ALB", "MKD", "GRC", "MDA", "LUX", "ISL"],
                   "territories": ["swe", "fin", "nor", "dnk", "deu", "che", "cze", "svk", "aut", "ita", "svn", "hun",
                                   "fra", "gbr", "pol", "lva", "rus", "blr"]},
        "eurasia": {"title": "Russia & Eurasia", "map": "eurasia", "level": "region",
                    "worldUnits": ["RUS", "KAZ", "CHN", "MNG", "JPN", "KOR"],
                    "territories": ["rus", "blr", "kaz", "chn", "jpn", "kor"]},
    },
    "dataNotice": "Sample database. Values marked Reference are widely reported real-world facts that have not "
                  "been re-verified for 2026–27. Placeholder values are game-design numbers, not real-world data.",
}


def badge(lid, levels, views, anchor, priority, **extra):
    b = {"id": f"badge-{lid}", "league": lid, "image": None, "views": views, "minLevel": levels,
         "anchor": anchor, "priority": priority, "action": {"type": "league", "id": lid}}
    b.update(extra)
    return b


badges = [
    # most important competitions: visible from the world map down
    badge("nhl", "world", ["world", "north-america"], [-97, 42], 100),
    badge("khl", "world", ["world", "eurasia"], [62, 57], 90),
    badge("shl", "world", ["world", "europe"], [15.5, 62.5], 80),
    badge("liiga", "world", ["world", "europe"], [26, 63], 70),
    # regional top leagues
    badge("ahl", "region", ["north-america"], [-84, 39], 60),
    badge("ncaa", "region", ["north-america"], [-100, 37], 40),
    badge("nl", "region", ["europe"], [8.2, 46.8], 60),
    badge("czech-extraliga", "region", ["europe"], [15.4, 49.8], 55),
    badge("del", "region", ["europe"], [10.4, 51.1], 55),
    badge("icehl", "region", ["europe"], [13.5, 47.0], 45),
    badge("eihl", "region", ["europe"], [-2.0, 53.5], 40),
    badge("champions", "region", ["europe"], [9.2, 56.0], 30),
    badge("asia-league", "region", ["eurasia"], [138, 37], 50),
    # revealed when a territory is selected
    badge("echl", "territory", ["north-america"], [-88, 34], 30),
    badge("ushl", "territory", ["north-america"], [-94, 42.5], 25),
    badge("whl", "territory", ["north-america"], [-114, 53], 35),
    badge("ohl", "territory", ["north-america"], [-80.5, 44], 35),
    badge("qmjhl", "territory", ["north-america"], [-70, 47.5], 35),
    badge("allsvenskan", "territory", ["europe"], [14.5, 58.8], 30),
    badge("vhl", "territory", ["eurasia"], [80, 55], 30),
    badge("mhl", "territory", ["eurasia"], [45, 55], 20),
    badge("belarus-extraleague", "territory", ["eurasia", "europe"], [28, 53.5], 25),
    badge("kazakhstan", "territory", ["eurasia"], [68, 48], 25),
]


def dump(name, obj):
    with open(os.path.join(OUT, name), "w") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


dump("game.json", game)
dump("territories.json", {"territories": territories})
dump("leagues.json", {"leagues": leagues})
dump("teams.json", {"teams": teams})
dump("badges.json", {"badges": badges})
print(len(territories), "territories,", len(leagues), "leagues,", len(teams), "teams,", len(badges), "badges")
