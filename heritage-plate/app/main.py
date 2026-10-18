"""Heritage Plate API: keep the family's food, fix the numbers."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import engine, llm, nutrition

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Heritage Plate", version="0.1.0")


class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    servings: int | None = Field(default=None, ge=1, le=20)


class AdaptIn(BaseModel):
    recipe: dict
    condition: str = "diabetes"


class PlanIn(BaseModel):
    recipes: list[dict] = Field(min_length=1, max_length=30)
    condition: str = "diabetes"
    language: str = Field(default="English", max_length=40)


def _guard(fn, *args):
    try:
        return fn(*args)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/health")
def health():
    return {"ok": True, "mode": "live" if llm.is_live() else "mock", "models": llm.MODELS, "foods": len(nutrition.foods())}


@app.get("/api/demo")
def demo():
    """A seeded family whose recipes are already structured (grams), with nutrition computed."""
    family = json.loads((ROOT / "data" / "demo_family.json").read_text(encoding="utf-8"))
    family["recipes"] = [
        engine._recipe(r["name"], r["servings"], engine.normalize_ingredients(r["ingredients"]), r["source_text"])
        for r in family["recipes"]
    ]
    return family


@app.post("/api/parse")
def parse(body: ParseIn):
    recipe, trace = _guard(engine.parse_recipe, body.text, body.servings)
    if not recipe["ingredients"]:
        raise HTTPException(status_code=422, detail="Couldn't find any ingredients. Try listing them with amounts.")
    return {"recipe": recipe, "trace": trace}


def _check_recipe(recipe: dict) -> None:
    if not isinstance(recipe.get("ingredients"), list) or "nutrition" not in recipe:
        raise HTTPException(status_code=422, detail="Recipe must come from /api/parse or /api/demo.")


@app.post("/api/adapt")
def adapt(body: AdaptIn):
    _check_recipe(body.recipe)
    adapted, trace = _guard(engine.adapt_recipe, body.recipe, body.condition)
    return {"recipe": adapted, "trace": trace}


@app.post("/api/plan")
def plan(body: PlanIn):
    for r in body.recipes:
        _check_recipe(r)
    result, trace = _guard(engine.make_plan, body.recipes, body.condition, body.language)
    return {"plan": result, "trace": trace}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
