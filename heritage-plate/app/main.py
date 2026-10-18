"""Heritage Plate API: keep the family's food, fix the numbers."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import engine, llm, nutrition

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("heritage_plate")
app = FastAPI(title="Heritage Plate", version="0.2.0")

Condition = Literal["diabetes", "bp", "cholesterol"]
Cuisine = Literal["south_asian", "east_asian", "southeast_asian", "continental", "middle_eastern", "latin_american", "other"]


class Ingredient(BaseModel):
    item: str = Field(min_length=1, max_length=60)
    grams: float = Field(gt=0, le=5000)


class Recipe(BaseModel):
    id: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    servings: int = Field(ge=1, le=20)
    meal: Literal["breakfast", "main", "dessert"] | None = None
    ingredients: list[Ingredient] = Field(min_length=1, max_length=40)
    source_text: str = Field(default="", max_length=1000)

    def build(self) -> dict:
        """Recompute nutrition server-side; client-sent numbers are ignored."""
        ingredients = engine.normalize_ingredients([i.model_dump() for i in self.ingredients])
        recipe = engine.build_recipe(self.name, self.servings, ingredients, self.source_text, self.meal)
        return {**recipe, "id": self.id}


def _language(value: str) -> str:
    if value not in engine.LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(engine.LANGUAGES)}")
    return value


class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    servings: int | None = Field(default=None, ge=1, le=20)
    cuisine: Cuisine = "other"


class AdaptIn(BaseModel):
    recipe: Recipe
    condition: Condition = "diabetes"
    cuisine: Cuisine = "other"


class PlanIn(BaseModel):
    recipes: list[Recipe] = Field(min_length=1, max_length=30)
    condition: Condition = "diabetes"
    language: str = "English"

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        return _language(value)


# Simple per-client limit on model-backed endpoints (protects credits on a public demo URL).
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "200"))  # model-backed requests per client per window
RATE_WINDOW_S, MAX_CLIENTS = 600, 10_000
# Set TRUST_PROXY=1 when deployed behind a proxy that sets X-Forwarded-For (e.g. a hosted endpoint).
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
_hits: dict[str, deque] = defaultdict(deque)


def _client_id(request: Request) -> str:
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request) -> None:
    now = time.monotonic()
    if len(_hits) > MAX_CLIENTS:  # drop idle clients so memory stays bounded
        for key in [k for k, v in _hits.items() if not v or now - v[-1] > RATE_WINDOW_S]:
            del _hits[key]
    hits = _hits[_client_id(request)]
    while hits and now - hits[0] > RATE_WINDOW_S:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few minutes.")
    hits.append(now)


def _guard(fn, *args):
    try:
        return fn(*args)
    except llm.LLMError as exc:
        log.warning("model call failed: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model didn't respond properly. Please try again.") from exc


@lru_cache
def _families() -> list[dict]:
    raw = json.loads((ROOT / "data" / "demo_families.json").read_text(encoding="utf-8"))
    families = []
    for fam in raw:
        recipes = [
            {**engine.build_recipe(r["name"], r["servings"], engine.normalize_ingredients(r["ingredients"]), r["source_text"], r.get("meal")), "id": f'{fam["id"]}-{i}'}
            for i, r in enumerate(fam["recipes"])
        ]
        families.append({**fam, "recipes": recipes})
    return families


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": "live" if llm.is_live() else "mock",
        "models": llm.MODELS,
        "foods": len(nutrition.foods()),
        "cuisines": engine.CUISINES,
        "languages": engine.LANGUAGES,
    }


@app.get("/api/demo")
def demo_list():
    return [{k: f[k] for k in ("id", "family", "parent", "cuisine", "condition", "language")} for f in _families()]


@app.get("/api/demo/{family_id}")
def demo(family_id: str):
    for fam in _families():
        if fam["id"] == family_id:
            return fam
    raise HTTPException(status_code=404, detail="Unknown demo family.")


@app.post("/api/parse")
def parse(body: ParseIn, request: Request):
    _rate_limit(request)
    recipe, trace = _guard(engine.parse_recipe, body.text, body.servings, body.cuisine)
    if not recipe["ingredients"]:
        raise HTTPException(status_code=422, detail="Couldn't find any ingredients. Try listing them with amounts.")
    return {"recipe": recipe, "trace": trace}


@app.post("/api/adapt")
def adapt(body: AdaptIn, request: Request):
    _rate_limit(request)
    adapted, trace = _guard(engine.adapt_recipe, body.recipe.build(), body.condition, body.cuisine)
    return {"recipe": adapted, "trace": trace}


@app.post("/api/plan")
def plan(body: PlanIn, request: Request):
    _rate_limit(request)
    recipes = [r.build() for r in body.recipes]
    result, trace = _guard(engine.make_plan, recipes, body.condition, body.language)
    return {"plan": result, "trace": trace}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
