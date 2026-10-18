from app import nutrition


def test_known_recipe_totals():
    # 100 g atta (72 g carbs, 2.5 g fat) + 10 g ghee (10 g fat), 1 serving
    result = nutrition.per_serving([{"item": "atta", "grams": 100}, {"item": "ghee", "grams": 10}], 1)
    assert result["carbs_g"] == 72.0
    assert result["fat_g"] == 12.5
    assert result["net_carbs_g"] == round(72.0 - 10.7, 1)
    assert result["uncounted"] == []


def test_per_serving_divides_and_flags_unknowns():
    result = nutrition.per_serving([{"item": "white rice", "grams": 200}, {"item": "unicorn dust", "grams": 5}], 2)
    assert result["carbs_g"] == 79.0  # 200 g * 79 / 100 / 2
    assert result["uncounted"] == ["unicorn dust"]


def test_aliases_match_home_names():
    assert nutrition.match("aloo").name == "potato"
    assert nutrition.match("2 katori toor dal").name == "toor dal"
    assert nutrition.match("brown basmati").name == "brown rice"
    assert nutrition.match("plastic") is None


def test_mentions_prefer_longest_alias():
    names = [food.name for food, _ in nutrition.find_mentions("brown rice with palak")]
    assert names == ["brown rice", "spinach"]
