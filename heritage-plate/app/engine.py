"""Parse -> adapt -> plan pipeline.

Live mode calls Nemotron on Token Factory (Nano parses, Super adapts, Ultra plans).
Mock mode uses deterministic rules so the app works without an API key.
Nutrition and the shopping list are always computed in code.
"""

from __future__ import annotations

import json
import re

from . import llm, nutrition, prompts

CONDITIONS = {
    "diabetes": "type 2 diabetes (focus: carbohydrates)",
    "bp": "high blood pressure (focus: salt and fats)",
    "cholesterol": "high cholesterol (focus: ghee, butter and fried fats)",
}
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
BREAKFAST_HINTS = ("paratha", "poha", "upma", "idli", "dosa", "oats", "chilla", "cheela", "thepla")
DESSERT_HINTS = ("kheer", "halwa", "ladoo", "laddu", "barfi", "payasam", "gulab", "jalebi")


def _mock_trace(step: str, tier: str) -> dict:
    return {"step": step, "tier": tier, "model": f"mock (Nemotron {tier.title()} when live)", "ms": 0, "tokens": None, "fallback": False}


def normalize_ingredients(raw: list[dict]) -> list[dict]:
    """Snap item names to the food table and clean up grams."""
    out: dict[str, dict] = {}
    for ing in raw or []:
        name = str(ing.get("item", "")).strip()
        if not name:
            continue
        try:
            grams = max(0.0, min(float(ing.get("grams") or 0), 5000.0))
        except (TypeError, ValueError):
            grams = 0.0
        food = nutrition.match(name)
        key = food.name if food else name.lower()
        if key in out:
            out[key]["grams"] += grams
        else:
            out[key] = {"item": key, "grams": grams, "matched": food is not None}
    for ing in out.values():
        ing["grams"] = round(ing["grams"])
    return [i for i in out.values() if i["grams"] > 0]


def _meal_type(name: str, ingredients: list[dict]) -> str:
    lower = name.lower()
    if any(h in lower for h in DESSERT_HINTS):
        return "dessert"
    if any(h in lower for h in BREAKFAST_HINTS):
        return "breakfast"
    total = sum(i["grams"] for i in ingredients) or 1
    sweet = sum(i["grams"] for i in ingredients if i["item"] in ("sugar", "jaggery"))
    return "dessert" if sweet / total > 0.08 else "main"


def _recipe(name: str, servings: int, ingredients: list[dict], source_text: str = "") -> dict:
    return {
        "name": name,
        "servings": servings,
        "meal": _meal_type(name, ingredients),
        "ingredients": ingredients,
        "source_text": source_text,
        "nutrition": nutrition.per_serving(ingredients, servings),
    }


# ---------- parse ----------

def _mock_parse(text: str) -> dict:
    """Find known foods in the text and assume a typical family-size amount of each.

    Live mode does real quantity reading with Nemotron Nano; this only keeps the
    demo usable without an API key.
    """
    ingredients = []
    norm = nutrition._norm(text)
    for food, pos in nutrition.find_mentions(text):
        window = norm[max(0, pos - 12) : pos]
        factor = 0.5 if re.search(r"\b(half|thoda|little)\s*$", window) else 1.0
        ingredients.append({"item": food.name, "grams": food.default_g * factor})
    first_line = text.strip().splitlines()[0] if text.strip() else "My recipe"
    name = first_line.split(":")[0].strip()[:60] or "My recipe"
    return {"name": name, "servings": 4, "ingredients": ingredients}


def parse_recipe(text: str, servings: int | None = None) -> tuple[dict, list[dict]]:
    if llm.is_live():
        system = prompts.PARSE.format(names=", ".join(nutrition.canonical_names()))
        data, trace = llm.chat_json("nano", system, text, step="Read recipe")
    else:
        data, trace = _mock_parse(text), _mock_trace("Read recipe", "nano")
    ingredients = normalize_ingredients(data.get("ingredients", []))
    serves = int(servings or data.get("servings") or 4)
    return _recipe(str(data.get("name") or "My recipe"), max(serves, 1), ingredients, text), [trace]


# ---------- adapt ----------

def _scale(ings: dict[str, float], item: str, factor: float) -> float:
    before = ings.get(item, 0.0)
    ings[item] = before * factor
    return before - ings[item]


def _mock_adapt(recipe: dict, condition: str) -> dict:
    ings = {i["item"]: float(i["grams"]) for i in recipe["ingredients"]}
    changes: list[dict] = []

    def add(item: str, grams: float) -> None:
        ings[item] = ings.get(item, 0.0) + grams

    is_dessert = recipe.get("meal") == "dessert"
    if condition == "diabetes":
        if ings.get("white rice"):
            cut = _scale(ings, "white rice", 0.6)
            if is_dessert:
                changes.append({"what": "Use 40% less rice and serve a small katori", "why": "Fewer carbs per bowl, same creamy kheer."})
            else:
                add("cauliflower", cut * 1.5)
                changes.append({"what": "Use 40% less rice and mix in riced cauliflower", "why": "Same full plate, far fewer fast carbs."})
        if ings.get("whole wheat flour"):
            original = ings["whole wheat flour"]
            _scale(ings, "whole wheat flour", 0.6)
            add("gram flour", original * 0.25)
            changes.append({"what": "Make the dough 70% atta + 30% besan, one roti less each", "why": "Besan adds protein and fibre, so sugar rises more slowly."})
        if ings.get("potato"):
            cut = _scale(ings, "potato", 0.5)
            add("cauliflower", cut)
            changes.append({"what": "Swap half the aloo for gobi", "why": "Potato is mostly starch; gobi keeps the texture."})
        if ings.get("flattened rice"):
            cut = _scale(ings, "flattened rice", 0.65)
            add("green peas", cut * 0.5)
            add("carrot", cut * 0.5)
            changes.append({"what": "Use a third less poha, more peas and carrot", "why": "Lower carbs per bowl, more fibre."})
        for sweet in ("sugar", "jaggery"):
            if ings.get(sweet):
                _scale(ings, sweet, 0.4)
                changes.append({"what": f"Use 60% less {'gur' if sweet == 'jaggery' else 'sugar'}", "why": "Gur and sugar raise blood sugar the same way."})
    if condition == "bp" and ings.get("salt"):
        _scale(ings, "salt", 0.6)
        changes.append({"what": "Use 40% less salt; finish with lemon and roasted jeera", "why": "Sour and smoky flavours hide the missing salt."})
    fat_factor = {"diabetes": 0.7, "bp": 0.75, "cholesterol": 0.5}[condition]
    fats = [f for f in ("ghee", "butter", "vegetable oil") if ings.get(f)]
    for fat in fats:
        _scale(ings, fat, fat_factor)
    if fats:
        pct = round((1 - fat_factor) * 100)
        changes.append({"what": f"Use {pct}% less ghee/oil; temper at the end", "why": "A final tadka gives the aroma with much less fat."})
    if condition == "cholesterol" and ings.get("paneer"):
        cut = _scale(ings, "paneer", 0.7)
        add("chickpeas", cut * 0.5)
        changes.append({"what": "Replace 30% of the paneer with chickpeas", "why": "Less saturated fat, same protein."})

    return {
        "ingredients": [{"item": k, "grams": v} for k, v in ings.items()],
        "changes": changes[:4] or [{"what": "Keep it as is, watch the portion", "why": "This dish already fits well."}],
        "cooking_tip": "Fill half the plate with sabzi or salad first, then the dish.",
    }


def adapt_recipe(recipe: dict, condition: str) -> tuple[dict, list[dict]]:
    condition = condition if condition in CONDITIONS else "diabetes"
    if llm.is_live():
        system = prompts.ADAPT.format(condition=CONDITIONS[condition], names=", ".join(nutrition.canonical_names()))
        user = json.dumps({k: recipe[k] for k in ("name", "servings", "ingredients")})
        data, trace = llm.chat_json("super", system, user, step="Adapt dish")
    else:
        data, trace = _mock_adapt(recipe, condition), _mock_trace("Adapt dish", "super")

    ingredients = normalize_ingredients(data.get("ingredients", [])) or recipe["ingredients"]
    after = nutrition.per_serving(ingredients, recipe["servings"])
    before = recipe["nutrition"]
    adapted = {
        **recipe,
        "ingredients": ingredients,
        "nutrition": after,
        "changes": [c for c in data.get("changes", []) if isinstance(c, dict)][:4],
        "cooking_tip": str(data.get("cooking_tip", "")),
        "original": {"ingredients": recipe["ingredients"], "nutrition": before},
        "delta": {k: round(after[k] - before[k], 1) for k in ("carbs_g", "net_carbs_g", "fat_g", "sodium_mg", "kcal")},
        "condition": condition,
    }
    return adapted, [trace]


# ---------- plan ----------

def _mock_schedule(recipes: list[dict]) -> list[dict]:
    ids = {m: [i for i, r in enumerate(recipes) if r["meal"] == m] for m in ("breakfast", "main", "dessert")}
    mains = ids["main"] or list(range(len(recipes)))
    breakfasts = ids["breakfast"] or mains
    # Dinner: rotate mains starting from the lowest-carb dish.
    dinners = sorted(mains, key=lambda i: recipes[i]["nutrition"]["net_carbs_g"])
    days = []
    for d, day in enumerate(DAYS):
        lunch = mains[d % len(mains)]
        dinner = dinners[d % len(dinners)]
        if dinner == lunch and len(mains) > 1:
            dinner = dinners[(d + 1) % len(dinners)]
        dessert = ids["dessert"][0] if ids["dessert"] and day in ("Sat", "Sun") else None
        days.append({"day": day, "breakfast": breakfasts[d % len(breakfasts)], "lunch": lunch, "dinner": dinner, "dessert": dessert})
    return days


def _valid_schedule(days: object, n: int) -> list[dict] | None:
    if not isinstance(days, list) or len(days) != 7:
        return None
    clean = []
    for i, day in enumerate(days):
        if not isinstance(day, dict):
            return None
        slots = {}
        for slot in ("breakfast", "lunch", "dinner", "dessert"):
            val = day.get(slot)
            if val is None and slot == "dessert":
                slots[slot] = None
                continue
            if not isinstance(val, int) or not 0 <= val < n:
                return None
            slots[slot] = val
        clean.append({"day": DAYS[i], **slots})
    return clean


def shopping_list(recipes: list[dict], days: list[dict]) -> list[dict]:
    """Each planned slot cooks one batch of that recipe; sum the grams."""
    need: dict[str, float] = {}
    for day in days:
        for slot in ("breakfast", "lunch", "dinner", "dessert"):
            idx = day.get(slot)
            if idx is None:
                continue
            for ing in recipes[idx]["ingredients"]:
                need[ing["item"]] = need.get(ing["item"], 0) + ing["grams"]
    items = []
    for item, grams in need.items():
        food = nutrition.match(item)
        items.append({"item": item, "grams": int(round(grams / 50.0) * 50) or 50, "category": food.category if food else "other"})
    order = ["grain", "legume", "vegetable", "dairy", "protein", "fat", "nuts", "sweetener", "spice", "other"]
    return sorted(items, key=lambda i: (order.index(i["category"]) if i["category"] in order else 99, i["item"]))


def make_plan(recipes: list[dict], condition: str, language: str) -> tuple[dict, list[dict]]:
    condition = condition if condition in CONDITIONS else "diabetes"
    days = None
    message = ""
    tips: list[str] = []
    trace: dict
    if llm.is_live():
        system = prompts.PLAN.format(condition=CONDITIONS[condition], language=language or "English")
        menu = [
            {"id": i, "name": r["name"], "meal": r["meal"], "net_carbs_per_serving_g": r["nutrition"]["net_carbs_g"]}
            for i, r in enumerate(recipes)
        ]
        data, trace = llm.chat_json("ultra", system, json.dumps(menu), step="Plan the week", max_tokens=2500)
        days = _valid_schedule(data.get("days"), len(recipes))
        message = str(data.get("message_for_parent", ""))
        tips = [str(t) for t in data.get("tips", [])][:3]
        trace["schedule_valid"] = days is not None
    else:
        trace = _mock_trace("Plan the week", "ultra")
    if days is None:
        days = _mock_schedule(recipes)
    if not message:
        language = f"English (translated to {language} in live mode)" if language and language != "English" else "English"
        message = (
            "We kept your favourite dishes on the menu. They're just a little lighter now: "
            "less rice and ghee, more sabzi and dal. Eat slowly, take a short walk after dinner, "
            "and enjoy your kheer on the weekend!"
        )
    if not tips:
        tips = ["Cook rice and roti portions with a measuring katori.", "Walk 10 minutes after the biggest meal.", "Keep roasted chana for snacks instead of namkeen."]

    named_days = [
        {"day": d["day"], **{slot: (recipes[d[slot]]["name"] if d[slot] is not None else None) for slot in ("breakfast", "lunch", "dinner", "dessert")}}
        for d in days
    ]
    result = {
        "days": named_days,
        "shopping_list": shopping_list(recipes, days),
        "message_for_parent": message,
        "language": language or "English",
        "tips": tips,
    }
    return result, [trace]
