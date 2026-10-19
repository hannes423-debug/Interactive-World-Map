#!/usr/bin/env python3
"""Coverage report for the branding library -> assets/branding/coverage.{json,md}.

Per competition it reports separately:
  league identity    the league's current logo: published / restricted / pending / missing
  club coverage      clubs with a published logo, restricted (non-free), pending download, missing
  quality verified   published assets that passed process.py checks
  season identity    published assets whose identity is verified for the season
                     (verified_secondary = file shown in the current infobox,
                      verified_visual   = free file matched to it)
  rights reviewed    assets with a rights status other than "unverified"
"""
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BRAND = os.path.join(ROOT, "assets", "branding")


def state(man, key):
    ent = man["entities"].get(key)
    if not ent:
        return "not-in-manifest", None
    a = man["assets"].get(ent.get("active")) if ent.get("active") else None
    if a and a.get("master"):
        return "published", a
    if ent.get("status") == "pending" or ent.get("pending"):
        return "pending", a
    if ent.get("status") == "restricted":
        return "restricted", a
    return "missing", a


def main():
    man = json.load(open(os.path.join(BRAND, "manifest.json")))
    mem = json.load(open(os.path.join(ROOT, "data", "hockey", "memberships-2026-27.json")))
    rows, out = [], {"leagues": {}, "other": {}}
    for lid, lg in mem["leagues"].items():
        ls, _ = state(man, f"league:{lid}")
        c = Counter()
        q = s = 0
        for club in lg["clubs"]:
            st, a = state(man, f"club:{club['id']}")
            c[st] += 1
            if st == "published":
                q += a.get("technical", {}).get("status") == "verified"
                s += a.get("identity", {}).get("status") in ("verified_secondary", "verified_visual")
        n = len(lg["clubs"])
        out["leagues"][lid] = {"leagueIdentity": ls, "clubs": n, **{k: c[k] for k in ("published", "restricted", "pending", "missing")},
                               "clubCoverage": round(c["published"] / n, 3) if n else 0, "qualityVerified": q, "seasonVerified": s}
        rows.append(f"| {lid} | {ls} | {n} | {c['published']} ({c['published'] / n:.0%}) | {c['restricted']} | {c['pending']} | {c['missing']} | {q} | {s} |")
    other = []
    for t in ("flag", "federation", "national-team", "tournament"):
        keys = [k for k in man["entities"] if k.startswith(t + ":")]
        c = Counter(state(man, k)[0] for k in keys)
        out["other"][t] = {"total": len(keys), **dict(c)}
        other.append(f"| {t} | {len(keys)} | {c['published']} | {c['restricted']} | {c['pending']} | {c['missing']} |")
    rights = Counter(a["rights"]["status"] for a in man["assets"].values())
    reviewed = sum(v for k, v in rights.items() if k != "unverified")
    out["rights"] = dict(rights)
    json.dump(out, open(os.path.join(BRAND, "coverage.json"), "w"), indent=1)
    md = ["# Branding coverage (2026–27)", "",
          "Club coverage counts only logos that are present in this repository and cleared for publication.", "",
          "| Competition | League identity | Clubs | Club logos published | Restricted (non-free) | Pending download | No logo found | Quality verified | Season identity verified |",
          "|---|---|---|---|---|---|---|---|---|"] + rows + [
          "", "| Type | Total | Published | Restricted | Pending | Missing |", "|---|---|---|---|---|---|"] + other + [
          "", f"Rights reviewed (status other than unverified): {reviewed} of {sum(rights.values())} asset records - " +
          ", ".join(f"{k}: {v}" for k, v in sorted(rights.items()))]
    open(os.path.join(BRAND, "coverage.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
