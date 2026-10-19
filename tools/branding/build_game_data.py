#!/usr/bin/env python3
"""Merge data/hockey/memberships-2026-27.json into the NHL 13 game data (dev-time tool).

* games/nhl13/teams.json    one entry per club, id = the branding/club id
* games/nhl13/leagues.json  clubs lists and team counts for 2026-27; adds leagues
                            from the membership file that the game did not have yet
* games/nhl13/badges.json   territory-level badges for added leagues
League ids are shared with the branding manifest (league:<id>).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
GAME = os.path.join(ROOT, "games", "nhl13")
MEM = json.load(open(os.path.join(ROOT, "data", "hockey", "memberships-2026-27.json")))

NEW_LEAGUES = {
    "mestis": dict(name="Mestis", shortName="Mestis", territories=["fin"], homeView="europe", level=2, label="Second-tier professional", anchor=[25.5, 61.5]),
    "vhl": dict(name="All-Russian Hockey League (VHL)", shortName="VHL", territories=["rus"], homeView="eurasia", level=2, label="Second-tier professional", anchor=[80, 55]),
    "mhl": dict(name="Junior Hockey League (MHL)", shortName="MHL", territories=["rus"], homeView="eurasia", level=4, label="Junior", anchor=[45, 55], kind="junior"),
    "swiss-league": dict(name="Swiss League", shortName="SL", territories=["che"], homeView="europe", level=2, label="Second-tier professional", anchor=[7.6, 47.2]),
    "del2": dict(name="DEL2", shortName="DEL2", territories=["deu"], homeView="europe", level=2, label="Second-tier professional", anchor=[11.5, 50.0]),
    "slovak-extraliga": dict(name="Slovak Extraliga (Tipsport Liga)", shortName="SVK", territories=["svk"], homeView="europe", level=1, label="Top professional league", anchor=[19.5, 48.7]),
}
ISO_TO_TERR = {"FIN": "fin", "RUS": "rus", "BLR": "blr", "KAZ": "kaz", "CHN": "chn", "USA": "usa", "CAN": "can", "SWE": "swe",
               "CHE": "che", "DEU": "deu", "AUT": "aut", "CZE": "cze", "SVK": "svk", "ITA": "ita", "SVN": "svn", "HUN": "hun",
               "FRA": "fra", "GBR": "gbr", "NOR": "nor", "DNK": "dnk", "POL": "pol", "LVA": "lva", "JPN": "jpn", "KOR": "kor"}


def dump(name, obj):
    with open(os.path.join(GAME, name), "w") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main():
    leagues = json.load(open(os.path.join(GAME, "leagues.json")))
    old_teams = {t["name"]: t for t in json.load(open(os.path.join(GAME, "teams.json")))["teams"]}
    badges = json.load(open(os.path.join(GAME, "badges.json")))
    by_id = {l["id"]: l for l in leagues["leagues"]}

    for lid, spec in NEW_LEAGUES.items():
        if lid in by_id or lid not in MEM["leagues"]:
            continue
        lg = {"id": lid, "name": spec["name"], "shortName": spec["shortName"], "logo": None,
              "kind": spec.get("kind", "professional"), "multinational": False,
              "territories": spec["territories"], "homeView": spec["homeView"],
              "tier": {"value": spec["label"], "status": "reference", "asOf": "2026–27", "level": spec["level"]},
              "teamCount": None, "season": {"value": "2026–27", "status": "game", "note": "Career mode start season"},
              "salary": {"value": None, "status": "placeholder", "note": "No salary data in the sample database yet"},
              "career": {"value": [], "status": "placeholder", "note": "Career notes not written yet"},
              "eligibility": {"value": None, "status": "unknown"}, "clubs": []}
        leagues["leagues"].append(lg)
        by_id[lid] = lg
        if not any(b["league"] == lid for b in badges["badges"]):
            badges["badges"].append({"id": f"badge-{lid}", "league": lid, "image": None, "views": [spec["homeView"]],
                                     "minLevel": "territory", "anchor": spec["anchor"], "priority": 25,
                                     "action": {"type": "league", "id": lid}})

    teams, seen = [], {}
    for lid, m in MEM["leagues"].items():
        lg = by_id.get(lid)
        if not lg:
            continue
        ids = []
        countries = set()
        for c in m["clubs"]:
            if c["id"] in seen:            # e.g. an SHL club also playing in the CHL
                seen[c["id"]].setdefault("competitions", []).append(lid)
                ids.append(c["id"])
                continue
            prev = old_teams.get(c["name"], {})
            terr = prev.get("territory") or ISO_TO_TERR.get(c.get("country"))
            countries.add(ISO_TO_TERR.get(c.get("country")))
            teams.append({"id": c["id"], "name": c["name"], "city": prev.get("city"), "league": lid,
                          "territory": terr, "geo": prev.get("geo") or c.get("country"),
                          "affiliations": [a for a in c.get("affiliations", []) if a.get("club")] or None,
                          "status": "reference", "asOf": "2026–27", "source": m["source"], "article": c.get("article")})
            seen[c["id"]] = teams[-1]
            ids.append(c["id"])
        lg["clubs"] = ids
        lg["teamCount"] = {"value": len(ids), "status": "reference", "asOf": "2026–27",
                           "note": "Clubs listed for 2026–27 in " + m["source"] + (f" ({m['note']})" if m.get("note") else "")}
        lg.pop("placeholderBadge", None)
        # multinational leagues: cover every country a participating club comes from
        extra = [c for c in countries if c and c not in lg["territories"] and not any(
            t in ("alps-adriatic", "europe-chl") for t in lg["territories"])]
        if extra and lid not in ("ahl", "echl", "nhl", "ohl", "whl", "qmjhl"):
            lg["territories"] = lg["territories"] + sorted(extra)
            lg["multinational"] = True
    for lg in leagues["leagues"]:
        lg.pop("placeholderBadge", None)
    dump("teams.json", {"_comment": "Generated by tools/branding/build_game_data.py from data/hockey/memberships-2026-27.json.",
                        "teams": teams})
    dump("leagues.json", leagues)
    dump("badges.json", badges)
    print(f"{len(teams)} teams, {len(leagues['leagues'])} leagues")


if __name__ == "__main__":
    main()
