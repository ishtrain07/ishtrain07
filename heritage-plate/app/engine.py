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
    "diabetes": "type 2 diabetes (focus: carbohydrates that raise blood sugar)",
    "bp": "high blood pressure (focus: sodium from salt and salty sauces)",
    "cholesterol": "high cholesterol (focus: saturated fat from ghee, butter, cream, cheese and fatty meat)",
}
CUISINES = {
    "south_asian": "South Asian (Indian, Pakistani, Bangladeshi, Sri Lankan)",
    "east_asian": "East Asian (Chinese, Korean, Japanese)",
    "southeast_asian": "Southeast Asian (Filipino, Vietnamese, Thai, Malaysian)",
    "continental": "Continental European (Italian, French, British, Eastern European)",
    "middle_eastern": "Middle Eastern and North African",
    "latin_american": "Latin American and Caribbean",
    "other": "home cooking from any tradition",
}
LANGUAGES = (
    "English", "Hindi", "Punjabi", "Gujarati", "Urdu", "Bengali", "Tamil", "Telugu",
    "Mandarin", "Cantonese", "Korean", "Japanese", "Tagalog", "Vietnamese", "Thai",
    "Arabic", "Farsi", "Spanish", "Portuguese", "Italian", "French", "Polish",
)
FOCUS_KEY = {"diabetes": "net_carbs_g", "bp": "sodium_mg", "cholesterol": "sat_fat_g"}
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
BREAKFAST_HINTS = ("paratha", "poha", "upma", "idli", "dosa", "oats", "oatmeal", "chilla", "cheela", "thepla",
                   "congee", "jook", "porridge", "omelette", "omelet", "pancake", "silog", "huevos", "chilaquiles", "toast")
DESSERT_HINTS = ("kheer", "halwa", "ladoo", "laddu", "barfi", "payasam", "gulab", "jalebi", "flan", "cake",
                 "pudding", "tiramisu", "mochi", "leche", "churro", "baklava", "biko", "pie", "cookie")


def _mock_trace(step: str, tier: str) -> dict:
    return {"step": step, "tier": tier, "model": f"mock (Nemotron {tier.title()} when live)",
            "ms": 0, "tokens": None, "fallback": False, "cached": False}


def normalize_ingredients(raw: object) -> list[dict]:
    """Snap item names to the food table, merge duplicates, clean up grams."""
    out: dict[str, dict] = {}
    for ing in raw if isinstance(raw, list) else []:
        if not isinstance(ing, dict):
            continue
        name = str(ing.get("item", "")).strip()[:60]
        if not name:
            continue
        try:
            grams = max(0.0, min(float(ing.get("grams") or 0), 5000.0))
        except (TypeError, ValueError):
            grams = 0.0
        if grams <= 0:
            continue
        food = nutrition.match(name)
        key = food.name if food else name.lower()
        if key in out:
            out[key]["grams"] += grams
        else:
            out[key] = {"item": key, "grams": grams, "matched": food is not None}
    for ing in out.values():
        ing["grams"] = round(ing["grams"], 1) if ing["grams"] < 10 else round(ing["grams"])
    return list(out.values())[:40]


def _servings(value: object, default: int = 4) -> int:
    try:
        return max(1, min(int(float(str(value).split("-")[0])), 20))
    except (TypeError, ValueError):
        return default


def _meal_type(name: str, ingredients: list[dict]) -> str:
    lower = name.lower()
    if any(h in lower for h in DESSERT_HINTS):
        return "dessert"
    if any(h in lower for h in BREAKFAST_HINTS):
        return "breakfast"
    total = sum(i["grams"] for i in ingredients) or 1
    sweet = sum(i["grams"] for i in ingredients if i["item"] in ("sugar", "brown sugar", "jaggery", "honey"))
    return "dessert" if sweet / total > 0.08 else "main"


def build_recipe(name: str, servings: int, ingredients: list[dict], source_text: str = "", meal: str | None = None) -> dict:
    return {
        "name": name[:80],
        "servings": servings,
        "meal": meal if meal in ("breakfast", "main", "dessert") else _meal_type(name, ingredients),
        "ingredients": ingredients,
        "source_text": source_text[:1000],
        "nutrition": nutrition.per_serving(ingredients, servings),
        "sources": nutrition.sources_for(ingredients),
    }


# ---------- parse ----------

def _mock_parse(text: str) -> dict:
    """Find known foods in the text and assume a typical family-size amount of each.

    Live mode does real quantity reading with Nemotron Nano; this only keeps the
    demo usable without an API key.
    """
    ingredients = []
    norm = nutrition.normalize(text)
    for food, pos in nutrition.find_mentions(text):
        window = norm[max(0, pos - 12) : pos]
        factor = 0.5 if re.search(r"\b(half|thoda|little)\s*$", window) else 1.0
        ingredients.append({"item": food.name, "grams": food.default_g * factor})
    first_line = text.strip().splitlines()[0] if text.strip() else "My recipe"
    name = first_line.split(":")[0].strip()[:60] or "My recipe"
    return {"name": name, "servings": 4, "ingredients": ingredients}


def parse_recipe(text: str, servings: int | None, cuisine: str) -> tuple[dict, list[dict]]:
    if llm.is_live():
        system = prompts.PARSE.format(cuisine=CUISINES[cuisine], names=", ".join(nutrition.canonical_names()))
        data, trace = llm.chat_json("nano", system, text, step="Read recipe")
    else:
        data, trace = _mock_parse(text), _mock_trace("Read recipe", "nano")
    ingredients = normalize_ingredients(data.get("ingredients"))
    serves = servings or _servings(data.get("servings"))
    return build_recipe(str(data.get("name") or "My recipe"), serves, ingredients, text), [trace]


# ---------- adapt ----------

# item -> (keep fraction, vegetable/legume added per gram removed, what, why)
STARCH_SWAPS = {
    "white rice": (0.6, ("cauliflower", 1.5), "Use 40% less rice and mix in riced cauliflower", "Same full plate, far fewer fast carbs."),
    "glutinous rice": (0.65, ("mushrooms", 1.0), "Use a third less sticky rice, add mushrooms", "Sticky rice spikes sugar fast; mushrooms keep it hearty."),
    "pasta": (0.6, ("zucchini", 1.5), "Use 40% less pasta and toss in zucchini ribbons", "Same bowl size with far fewer carbs."),
    "egg noodles": (0.6, ("bean sprouts", 1.5), "Use 40% less noodles, add bean sprouts and greens", "Keeps the slurp, cuts the starch."),
    "rice noodles": (0.6, ("bean sprouts", 1.5), "Use 40% less rice noodles, add bean sprouts", "Rice noodles are almost pure starch."),
    "potato": (0.5, ("cauliflower", 1.0), "Swap half the potato for cauliflower", "Potato is mostly starch; cauliflower keeps the texture."),
    "flattened rice": (0.65, ("green peas", 1.0), "Use a third less poha, more peas", "Lower carbs per bowl, more fibre."),
    "couscous": (0.6, ("chickpeas", 0.5), "Use 40% less couscous, add chickpeas", "Chickpeas add protein and fibre, so sugar rises slower."),
    "cornmeal": (0.7, ("black beans", 0.4), "Use 30% less cornmeal, serve with beans", "Beans slow the sugar rise from corn."),
    "plantain": (0.6, ("green beans", 1.0), "Use 40% less plantain, add green beans", "Plantain is starchy; beans fill the plate."),
    "cassava": (0.6, ("green beans", 1.0), "Use 40% less cassava, add green beans", "Cassava is very starchy."),
}
FULL_SWAPS = {
    "white bread": ("whole wheat bread", "Use whole-wheat bread instead of white", "More fibre, slower sugar rise."),
    "flour tortilla": ("corn tortilla", "Use corn tortillas instead of flour", "Fewer carbs and less fat per tortilla."),
}
SWEETS = ("sugar", "brown sugar", "jaggery", "honey")
SALTY = {
    "salt": (0.6, "Use 40% less salt; finish with lemon or lime", "Sour and fresh flavours hide the missing salt."),
    "soy sauce": (0.5, "Use half the soy sauce, add a splash of vinegar", "Soy sauce is one of the saltiest things in the kitchen."),
    "fish sauce": (0.5, "Use half the fish sauce, add lime", "Fish sauce is very high in sodium."),
    "oyster sauce": (0.5, "Use half the oyster sauce", "Bottled sauces carry most of the salt."),
    "parmesan cheese": (0.6, "Use 40% less parmesan", "Hard cheeses are salty."),
    "cheddar cheese": (0.6, "Use 40% less cheddar", "Cheese adds a lot of sodium."),
    "queso fresco": (0.6, "Use 40% less queso", "Cheese adds a lot of sodium."),
    "bacon": (0.5, "Use half the bacon", "Cured meat is salty and fatty."),
}


def _mock_adapt(recipe: dict, condition: str) -> dict:
    ings = {i["item"]: float(i["grams"]) for i in recipe["ingredients"]}
    changes: list[dict] = []
    is_dessert = recipe.get("meal") == "dessert"

    def scale(item: str, factor: float) -> float:
        before = ings.get(item, 0.0)
        ings[item] = before * factor
        return before - ings[item]

    def add(item: str, grams: float) -> None:
        ings[item] = ings.get(item, 0.0) + grams

    if condition == "diabetes":
        for item, (keep, (veg, ratio), what, why) in STARCH_SWAPS.items():
            if ings.get(item):
                cut = scale(item, keep)
                if is_dessert:
                    changes.append({"what": f"Use {round((1 - keep) * 100)}% less {item} and serve a smaller bowl", "why": "Fewer carbs per serving, same dessert."})
                else:
                    add(veg, cut * ratio)
                    changes.append({"what": what, "why": why})
        for item, (new, what, why) in FULL_SWAPS.items():
            if ings.get(item):
                add(new, ings.pop(item))
                changes.append({"what": what, "why": why})
        if ings.get("whole wheat flour"):
            original = ings["whole wheat flour"]
            scale("whole wheat flour", 0.6)
            add("gram flour", original * 0.25)
            changes.append({"what": "Make the dough 70% atta + 30% besan, one roti less each", "why": "Besan adds protein and fibre, so sugar rises more slowly."})
        if ings.get("all-purpose flour"):
            moved = scale("all-purpose flour", 0.5)
            add("whole wheat flour", moved * 0.8)
            changes.append({"what": "Swap half the white flour for whole-wheat, use a little less", "why": "More fibre, slower sugar rise."})
        for sweet in SWEETS:
            if ings.get(sweet):
                scale(sweet, 0.4)
                changes.append({"what": f"Use 60% less {sweet}", "why": "Every sweetener (sugar, jaggery, honey) raises blood sugar."})
    if condition == "bp":
        for item, (keep, what, why) in SALTY.items():
            if ings.get(item):
                scale(item, keep)
                changes.append({"what": what, "why": why})
    if condition == "cholesterol":
        if ings.get("heavy cream"):
            moved = scale("heavy cream", 0.4)
            add("yogurt", moved)
            changes.append({"what": "Replace most of the cream with yogurt", "why": "Cream is mostly saturated fat; yogurt keeps it creamy."})
        for meat, extra in (("ground beef", "mushrooms"), ("pork", "mushrooms"), ("lamb", "chickpeas"), ("bacon", "mushrooms")):
            if ings.get(meat):
                moved = scale(meat, 0.6)
                add(extra, moved * (1.0 if extra == "mushrooms" else 0.5))
                changes.append({"what": f"Use 40% less {meat}, bulk it up with {extra}", "why": "Less saturated fat, same hearty dish."})
        for cheese in ("cheddar cheese", "mozzarella cheese", "parmesan cheese", "queso fresco", "paneer"):
            if ings.get(cheese):
                scale(cheese, 0.7)
                changes.append({"what": f"Use 30% less {cheese}", "why": "Cheese is a big source of saturated fat."})
    fat_factor = {"diabetes": 0.7, "bp": 0.75, "cholesterol": 0.5}[condition]
    fats = [f for f in ("ghee", "butter", "coconut oil", "vegetable oil", "olive oil", "mustard oil", "groundnut oil", "canola oil") if ings.get(f)]
    for fat in fats:
        scale(fat, fat_factor)
    if fats:
        changes.append({"what": f"Use {round((1 - fat_factor) * 100)}% less ghee, butter or oil", "why": "Measure with a spoon; add the flavourful fat at the end."})

    return {
        "ingredients": [{"item": k, "grams": v} for k, v in ings.items()],
        "changes": changes[:5] or [{"what": "Keep it as is, watch the portion", "why": "This dish already fits well."}],
        "cooking_tip": "Fill half the plate with vegetables or salad first, then the dish.",
    }


def adapt_recipe(recipe: dict, condition: str, cuisine: str) -> tuple[dict, list[dict]]:
    # Recompute the "before" numbers server-side; never trust client nutrition.
    before = nutrition.per_serving(recipe["ingredients"], recipe["servings"])
    if llm.is_live():
        system = prompts.ADAPT.format(condition=CONDITIONS[condition], cuisine=CUISINES[cuisine],
                                      names=", ".join(nutrition.canonical_names()))
        user = json.dumps({k: recipe[k] for k in ("name", "servings", "ingredients")})
        data, trace = llm.chat_json("super", system, user, step="Adapt dish")
    else:
        data, trace = _mock_adapt({**recipe, "nutrition": before}, condition), _mock_trace("Adapt dish", "super")

    ingredients = normalize_ingredients(data.get("ingredients")) or recipe["ingredients"]
    after = nutrition.per_serving(ingredients, recipe["servings"])
    # If the model introduced ingredients we can't count, the comparison would flatter it.
    new_unknowns = sorted(set(after["uncounted"]) - set(before["uncounted"]))
    changes = [
        {"what": str(c.get("what", ""))[:200], "why": str(c.get("why", ""))[:240]}
        for c in data.get("changes", []) if isinstance(c, dict) and c.get("what")
    ][:5]
    adapted = {
        **recipe,
        "ingredients": ingredients,
        "nutrition": after,
        "sources": nutrition.sources_for(ingredients),
        "changes": changes,
        "cooking_tip": str(data.get("cooking_tip", ""))[:240],
        "original": {"ingredients": recipe["ingredients"], "nutrition": before},
        "delta": {k: round(after[k] - before[k], 1) for k in ("net_carbs_g", "sat_fat_g", "fat_g", "sodium_mg", "kcal")},
        "focus": FOCUS_KEY[condition],
        "comparable": not new_unknowns,
        "condition": condition,
    }
    return adapted, [trace]


# ---------- plan ----------

def _mock_schedule(recipes: list[dict], focus: str = "net_carbs_g") -> list[dict]:
    ids = {m: [i for i, r in enumerate(recipes) if r["meal"] == m] for m in ("breakfast", "main", "dessert")}
    mains = ids["main"] or [i for i, r in enumerate(recipes) if r["meal"] != "dessert"] or list(range(len(recipes)))
    breakfasts = ids["breakfast"] or mains
    # Dinner rotates from the dish lowest in the condition's focus nutrient.
    dinners = sorted(mains, key=lambda i: recipes[i]["nutrition"][focus])
    days = []
    for d, day in enumerate(DAYS):
        lunch = mains[d % len(mains)]
        dinner = dinners[d % len(dinners)]
        if dinner == lunch and len(mains) > 1:
            dinner = dinners[(d + 1) % len(dinners)]
        dessert = ids["dessert"][0] if ids["dessert"] and day in ("Sat", "Sun") else None
        days.append({"day": day, "breakfast": breakfasts[d % len(breakfasts)], "lunch": lunch, "dinner": dinner, "dessert": dessert})
    return days


def _valid_schedule(days: object, recipes: list[dict]) -> list[dict] | None:
    """Accept the model's week only if it follows the rules; otherwise use ours."""
    n = len(recipes)
    if not isinstance(days, list) or len(days) != 7:
        return None
    mains = sum(1 for r in recipes if r["meal"] != "dessert")
    clean, desserts = [], 0
    for i, day in enumerate(days):
        if not isinstance(day, dict):
            return None
        slots: dict[str, int | None] = {}
        for slot in ("breakfast", "lunch", "dinner", "dessert"):
            val = day.get(slot)
            if val is None and slot == "dessert":
                slots[slot] = None
                continue
            if type(val) is not int or not 0 <= val < n:
                return None
            slots[slot] = val
        if slots["dessert"] is not None:
            desserts += 1
            if recipes[slots["dessert"]]["meal"] != "dessert":
                return None
        if mains > 1 and slots["lunch"] == slots["dinner"]:
            return None
        clean.append({"day": DAYS[i], **slots})
    return clean if desserts <= 2 else None


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
        step = 50 if grams >= 50 else 5
        items.append({"item": item, "grams": max(step, int(round(grams / step) * step)), "category": food.category if food else "other"})
    order = ["grain", "legume", "vegetable", "fruit", "dairy", "protein", "fat", "nuts", "sauce", "sweetener", "spice", "other"]
    return sorted(items, key=lambda i: (order.index(i["category"]) if i["category"] in order else 99, i["item"]))


FALLBACK_MESSAGES = {
    "diabetes": "We kept your favourite dishes on the menu. They're just lighter now, with smaller starch portions and more vegetables. Eat slowly, take a short walk after dinner, and enjoy your treat on the weekend.",
    "bp": "Your favourite dishes are all still here, just with less salt and lighter sauces. Taste before adding salt, use lemon and herbs for flavour, and drink water through the day.",
    "cholesterol": "Your favourite dishes are still on the menu, with less ghee, butter, cream and fatty meat. Small changes every day add up. Keep walking and enjoy your food.",
}
FALLBACK_TIPS = {
    "diabetes": ["Measure rice, noodles and roti with the same bowl every time.", "Walk 10 minutes after the biggest meal.", "Keep roasted chickpeas or nuts for snacks."],
    "bp": ["Taste first, then salt.", "Check labels on sauces and stock cubes for sodium.", "Add herbs, garlic, lemon and vinegar for flavour."],
    "cholesterol": ["Measure oil with a spoon, don't pour.", "Choose lean cuts and trim visible fat.", "Add a bowl of beans or lentils a few times a week."],
}


def make_plan(recipes: list[dict], condition: str, language: str) -> tuple[dict, list[dict]]:
    days, message, tips = None, "", []
    message_language = language
    if llm.is_live():
        system = prompts.PLAN.format(condition=CONDITIONS[condition], language=language)
        focus = FOCUS_KEY[condition]
        menu = [{"id": i, "name": r["name"], "meal": r["meal"], focus: r["nutrition"][focus]} for i, r in enumerate(recipes)]
        data, trace = llm.chat_json("ultra", system, json.dumps(menu), step="Plan the week", max_tokens=3000)
        days = _valid_schedule(data.get("days"), recipes)
        message = str(data.get("message_for_parent", ""))[:800]
        raw_tips = data.get("tips")
        tips = [str(t)[:200] for t in raw_tips][:3] if isinstance(raw_tips, list) else []
        trace["schedule_valid"] = days is not None
    else:
        trace = _mock_trace("Plan the week", "ultra")
    if days is None:
        days = _mock_schedule(recipes, FOCUS_KEY[condition])
    if not message:
        message = FALLBACK_MESSAGES[condition]
        if language != "English":
            message_language = f"English (written in {language} when live)"
    tips = tips or FALLBACK_TIPS[condition]

    named_days = [
        {"day": d["day"], **{s: (recipes[d[s]]["name"] if d[s] is not None else None) for s in ("breakfast", "lunch", "dinner", "dessert")}}
        for d in days
    ]
    return {
        "days": named_days,
        "shopping_list": shopping_list(recipes, days),
        "message_for_parent": message,
        "language": message_language,
        "tips": tips,
    }, [trace]
