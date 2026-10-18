import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setenv("MOCK", "1")


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["mode"] == "mock"


def test_demo_to_plan_flow(client):
    family = client.get("/api/demo").json()
    assert len(family["recipes"]) == 6

    adapted = []
    for recipe in family["recipes"]:
        out = client.post("/api/adapt", json={"recipe": recipe, "condition": "diabetes"}).json()["recipe"]
        assert out["nutrition"]["net_carbs_g"] <= recipe["nutrition"]["net_carbs_g"]
        assert out["changes"]
        adapted.append(out)
    # Starchy dishes must show a real reduction, computed from the food table.
    paratha = next(r for r in adapted if "paratha" in r["name"])
    assert paratha["delta"]["net_carbs_g"] < -5

    plan = client.post("/api/plan", json={"recipes": adapted, "condition": "diabetes", "language": "Punjabi"}).json()["plan"]
    assert [d["day"] for d in plan["days"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert all(d["lunch"] != d["dinner"] for d in plan["days"])
    assert sum(1 for d in plan["days"] if d["dessert"]) <= 2
    assert plan["shopping_list"] and plan["message_for_parent"]


def test_parse_free_text(client):
    res = client.post("/api/parse", json={"text": "Masoor dal: 1 katori masoor, half onion, tamatar, a little ghee"})
    recipe = res.json()["recipe"]
    assert recipe["name"] == "Masoor dal"
    assert {"masoor dal", "onion", "tomato", "ghee"} <= {i["item"] for i in recipe["ingredients"]}


def test_parse_rejects_text_without_food(client):
    assert client.post("/api/parse", json={"text": "hello there friend"}).status_code == 422


def test_adapt_requires_parsed_recipe(client):
    assert client.post("/api/adapt", json={"recipe": {"name": "x"}}).status_code == 422


def test_adapting_never_worsens_the_focus_metric(client):
    recipe = client.post("/api/parse", json={"text": "Masoor dal: 1 katori masoor, onion, a little ghee"}).json()["recipe"]
    for condition, key in (("diabetes", "net_carbs_g"), ("bp", "sodium_mg"), ("cholesterol", "fat_g")):
        out = client.post("/api/adapt", json={"recipe": recipe, "condition": condition}).json()["recipe"]
        assert out["nutrition"][key] <= recipe["nutrition"][key]
