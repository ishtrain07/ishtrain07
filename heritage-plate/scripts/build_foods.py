"""Build data/foods.csv from published food-composition tables.

Every nutrient value is copied from a citable source record:
  IFCT  - Indian Food Composition Tables 2017, National Institute of Nutrition
          (npm package @ifct2017/compositions, MIT; file index.csv)
  USDA  - USDA National Nutrient Database for Standard Reference, Release 28
          (public domain; npm package fda-nutrient-database; file data/ABBREV.txt)

Usage:
  npm pack @ifct2017/compositions fda-nutrient-database   # then untar both
  python scripts/build_foods.py --ifct <ifct>/index.csv --sr28 <sr28>/data/ABBREV.txt

The curated list (names, home-language aliases, source IDs) lives in
data/ingredients.csv. All values are per 100 g edible portion.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FIELDS = ["kcal", "carbs_g", "fiber_g", "protein_g", "fat_g", "sat_fat_g", "sodium_mg"]
KJ_PER_KCAL = 4.184


def _num(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_ifct(path: Path) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    keys = [h.split(";")[-1].strip() for h in rows[0]]
    out = {}
    for row in rows[1:]:
        r = dict(zip(keys, row))
        available_carbs = _num(r["choavldf"])  # IFCT reports available carbs (fibre excluded)
        fiber = _num(r["fibtg"])
        out[r["code"]] = {
            "desc": r["name"],
            "kcal": _num(r["enerc"]) / KJ_PER_KCAL,  # IFCT energy is in kJ
            "carbs_g": available_carbs + fiber,  # store total carbs, like USDA
            "fiber_g": fiber,
            "protein_g": _num(r["protcnt"]),
            "fat_g": _num(r["fatce"]),
            "sat_fat_g": _num(r["fasat"]),
            "sodium_mg": _num(r["na"]) * 1000,  # IFCT minerals are in g/100 g
        }
    return out


def load_sr28(path: Path) -> dict[str, dict]:
    out = {}
    with open(path, encoding="latin-1") as fh:
        for line in fh:
            f = [x.strip("~") for x in line.rstrip("\n").split("^")]
            out[f[0]] = {
                "desc": f[1],
                "kcal": _num(f[3]),
                "protein_g": _num(f[4]),
                "fat_g": _num(f[5]),
                "carbs_g": _num(f[7]),  # total carbohydrate by difference (includes fibre)
                "fiber_g": _num(f[8]),
                "sodium_mg": _num(f[15]),
                "sat_fat_g": _num(f[44]),
            }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ifct", type=Path, required=True)
    ap.add_argument("--sr28", type=Path, required=True)
    args = ap.parse_args()
    sources = {"IFCT": load_ifct(args.ifct), "USDA": load_sr28(args.sr28)}

    with open(DATA / "ingredients.csv", newline="", encoding="utf-8") as fh:
        ingredients = list(csv.DictReader(fh))

    rows, missing = [], []
    for ing in ingredients:
        rec = sources[ing["source"]].get(ing["source_id"])
        if rec is None:
            missing.append(f'{ing["name"]} ({ing["source"]} {ing["source_id"]})')
            continue
        if rec["kcal"] == 0 and rec["fat_g"] + rec["carbs_g"] + rec["protein_g"] > 1:
            missing.append(f'{ing["name"]} (no energy value in {ing["source"]} {ing["source_id"]})')
            continue
        rows.append({
            **{k: ing[k] for k in ("name", "aliases", "category", "default_g")},
            **{k: round(rec[k], 2) for k in FIELDS},
            "source": "IFCT 2017" if ing["source"] == "IFCT" else "USDA SR28",
            "source_id": ing["source_id"],
            "source_desc": rec["desc"],
        })
    if missing:
        raise SystemExit("Source IDs not found: " + ", ".join(missing))

    cols = ["name", "aliases", "category", "default_g", *FIELDS, "source", "source_id", "source_desc"]
    with open(DATA / "foods.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} foods to {DATA / 'foods.csv'}")


if __name__ == "__main__":
    main()
