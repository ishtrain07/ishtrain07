from app import nutrition


def test_known_recipe_totals():
    atta, ghee = nutrition.foods()["whole wheat flour"].per100, nutrition.foods()["ghee"].per100
    result = nutrition.per_serving([{"item": "atta", "grams": 100}, {"item": "ghee", "grams": 10}], 1)
    assert result["carbs_g"] == round(atta["carbs_g"], 1)
    assert result["fat_g"] == round(atta["fat_g"] + ghee["fat_g"] / 10, 1)
    assert result["net_carbs_g"] == round(result["carbs_g"] - result["fiber_g"], 1)
    assert result["uncounted"] == []


def test_per_serving_divides_and_flags_unknowns():
    result = nutrition.per_serving([{"item": "white rice", "grams": 200}, {"item": "unicorn dust", "grams": 5}], 2)
    assert result["carbs_g"] == round(nutrition.foods()["white rice"].per100["carbs_g"], 1)  # 200 g / 2 servings
    assert result["uncounted"] == ["unicorn dust"]


def test_aliases_match_home_names():
    assert nutrition.match("aloo").name == "potato"
    assert nutrition.match("2 katori toor dal").name == "toor dal"
    assert nutrition.match("brown basmati").name == "brown rice"
    assert nutrition.match("plastic") is None


def test_mentions_prefer_longest_alias():
    names = [food.name for food, _ in nutrition.find_mentions("brown rice with palak")]
    assert names == ["brown rice", "spinach"]
    assert nutrition.match("2 tbsp soy sauce").name == "soy sauce"


def test_every_food_has_a_published_source():
    for food in nutrition.foods().values():
        assert food.source in ("IFCT 2017", "USDA SR28") and food.source_id and food.source_desc
        assert food.per100["kcal"] > 0 or food.name == "salt"


def test_values_match_source_records():
    # IFCT A019 atta: 1340 kJ, 64.17 g available carbs + 11.36 g fibre; USDA 20120 dry pasta: 371 kcal
    atta = nutrition.foods()["whole wheat flour"]
    assert atta.source_id == "A019" and round(atta.per100["kcal"]) == 320
    assert nutrition.foods()["pasta"].per100["kcal"] == 371.0


def test_finds_repeated_and_overlapping_mentions():
    names = [f.name for f, _ in nutrition.find_mentions("brown rice, then plain rice and soy sauce")]
    assert names == ["brown rice", "white rice", "soy sauce"]
