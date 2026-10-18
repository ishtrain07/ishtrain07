"""Deterministic nutrition math.

Every number shown to the user comes from data/foods.csv (approximate values
per 100 g, based on USDA FoodData Central and the Indian Food Composition
Tables), never from the language model.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NUTRIENTS = ("kcal", "carbs_g", "fiber_g", "protein_g", "fat_g", "sodium_mg")


@dataclass(frozen=True)
class Food:
    name: str
    aliases: tuple[str, ...]
    category: str
    default_g: float
    per100: dict[str, float]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", text.lower())).strip()


@lru_cache
def foods() -> dict[str, Food]:
    table: dict[str, Food] = {}
    with open(DATA_DIR / "foods.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = Food(
                name=row["name"],
                aliases=tuple(a.strip() for a in row["aliases"].split("|") if a.strip()),
                category=row["category"],
                default_g=float(row["default_g"]),
                per100={k: float(row[k]) for k in NUTRIENTS},
            )
    return table


@lru_cache
def _alias_index() -> dict[str, str]:
    """Normalized alias (or canonical name) -> canonical name."""
    index: dict[str, str] = {}
    for food in foods().values():
        for alias in (food.name, *food.aliases):
            index.setdefault(_norm(alias), food.name)
    return index


def canonical_names() -> list[str]:
    return sorted(foods())


def match(item: str) -> Food | None:
    """Map a free-text ingredient name to a food in the table, or None."""
    text = _norm(item)
    index = _alias_index()
    if text in index:
        return foods()[index[text]]
    best: str | None = None
    for alias in index:
        if re.search(rf"\b{re.escape(alias)}\b", text) and (best is None or len(alias) > len(best)):
            best = alias
    return foods()[index[best]] if best else None


def find_mentions(text: str) -> list[tuple[Food, int]]:
    """Foods mentioned in free text, with the character offset of each first mention."""
    norm = _norm(text)
    hits: dict[str, tuple[Food, int, int]] = {}
    for alias, name in _alias_index().items():
        m = re.search(rf"\b{re.escape(alias)}\b", norm)
        if not m:
            continue
        prev = hits.get(name)
        # Prefer the longest alias so "brown rice" beats "rice".
        if prev is None or len(alias) > prev[2]:
            hits[name] = (foods()[name], m.start(), len(alias))
    # Drop foods whose match sits inside a longer match ("rice" inside "brown rice").
    spans = sorted(((pos, pos + ln, f) for f, pos, ln in hits.values()), key=lambda s: s[1] - s[0], reverse=True)
    kept: list[tuple[int, int, Food]] = []
    for start, end, food in spans:
        if not any(s <= start and end <= e for s, e, _ in kept):
            kept.append((start, end, food))
    return [(food, start) for start, _, food in sorted(kept, key=lambda s: s[0])]


def totals(ingredients: list[dict]) -> dict:
    """Sum nutrients for [{"item", "grams"}]; unknown items are listed, not guessed."""
    out = {k: 0.0 for k in NUTRIENTS}
    uncounted: list[str] = []
    for ing in ingredients:
        food = match(ing["item"])
        grams = float(ing.get("grams") or 0)
        if food is None:
            uncounted.append(ing["item"])
            continue
        for k in NUTRIENTS:
            out[k] += food.per100[k] * grams / 100
    out["uncounted"] = uncounted
    return out


def per_serving(ingredients: list[dict], servings: int) -> dict:
    servings = max(int(servings or 1), 1)
    total = totals(ingredients)
    result = {k: round(total[k] / servings, 1) for k in NUTRIENTS}
    result["net_carbs_g"] = round(max(result["carbs_g"] - result["fiber_g"], 0), 1)
    result["uncounted"] = total["uncounted"]
    return result
