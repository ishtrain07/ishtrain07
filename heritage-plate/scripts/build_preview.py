"""Bundle a single-file, serverless preview of the demo (mock) mode.

The preview is the real front end (static/) plus a small in-page stand-in for
the API. All four demo families are precomputed with the real Python engine in
mock mode: every dish x every health focus. The week plan and shopping list are
recomputed in the browser with a direct port of the engine's mock schedule, and
tests/test_preview.py checks that port against the Python output.

Usage:  python scripts/build_preview.py <out.html>
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

os.environ["MOCK"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app import engine, nutrition  # noqa: E402
from app.main import app  # noqa: E402

CONDITIONS = ("diabetes", "bp", "cholesterol")


def precompute() -> dict:
    client = TestClient(app)
    families = {f["id"]: client.get(f"/api/demo/{f['id']}").json() for f in client.get("/api/demo").json()}
    adapt = {}
    for fam in families.values():
        for recipe in fam["recipes"]:
            for condition in CONDITIONS:
                body = {"recipe": recipe, "condition": condition, "cuisine": fam["cuisine"]}
                adapt[f'{recipe["id"]}|{condition}'] = client.post("/api/adapt", json=body).json()
    return {
        "health": client.get("/api/health").json(),
        "demoList": client.get("/api/demo").json(),
        "families": families,
        "adapt": adapt,
        "categories": {name: food.category for name, food in nutrition.foods().items()},
        "focusKey": engine.FOCUS_KEY,
        "messages": engine.FALLBACK_MESSAGES,
        "tips": engine.FALLBACK_TIPS,
        "days": list(engine.DAYS),
    }


SHIM = r"""
// Serverless preview: answers the app's /api calls from data precomputed by the
// real engine in demo mode. The week plan is a direct port of engine._mock_schedule.
(() => {
  const D = window.__HP_DATA__;
  const round1 = (g) => Math.round(Number(g) * 10) / 10;
  const sig = (r) => `${r.id}|${JSON.stringify((r.ingredients || []).map((i) => [i.item, round1(i.grams)]))}`;
  const known = {};
  for (const fam of Object.values(D.families)) for (const r of fam.recipes) known[sig(r)] = r;
  for (const res of Object.values(D.adapt)) known[sig(res.recipe)] = res.recipe;

  const mockTrace = (step, tier) => [{ step, tier, model: `mock (Nemotron ${tier[0].toUpperCase()}${tier.slice(1)} when live)`, ms: 0, tokens: null, fallback: false, cached: false }];
  const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const notInPreview = () => reply(503, { detail: "This preview runs the four demo families. Adding your own recipes needs the full app with a live server." });

  function schedule(recipes, focus) {
    const ids = { breakfast: [], main: [], dessert: [] };
    recipes.forEach((r, i) => ids[r.meal].push(i));
    let mains = ids.main.length ? ids.main : recipes.map((r, i) => (r.meal !== "dessert" ? i : -1)).filter((i) => i >= 0);
    if (!mains.length) mains = recipes.map((_, i) => i);
    const breakfasts = ids.breakfast.length ? ids.breakfast : mains;
    const dinners = [...mains].sort((a, b) => recipes[a].nutrition[focus] - recipes[b].nutrition[focus]);
    return D.days.map((day, d) => {
      const lunch = mains[d % mains.length];
      let dinner = dinners[d % dinners.length];
      if (dinner === lunch && mains.length > 1) dinner = dinners[(d + 1) % dinners.length];
      const dessert = ids.dessert.length && (day === "Sat" || day === "Sun") ? ids.dessert[0] : null;
      return { day, breakfast: breakfasts[d % breakfasts.length], lunch, dinner, dessert };
    });
  }

  function shopping(recipes, days) {
    const need = new Map();
    for (const day of days) for (const slot of ["breakfast", "lunch", "dinner", "dessert"]) {
      const idx = day[slot];
      if (idx === null) continue;
      for (const ing of recipes[idx].ingredients) need.set(ing.item, (need.get(ing.item) || 0) + ing.grams);
    }
    const order = ["grain", "legume", "vegetable", "fruit", "dairy", "protein", "fat", "nuts", "sauce", "sweetener", "spice", "other"];
    const pyRound = (x) => { const f = Math.floor(x); const r = x - f; return r > 0.5 || (r === 0.5 && f % 2 === 1) ? f + 1 : f; };
    const items = [...need].map(([item, grams]) => {
      const step = grams >= 50 ? 50 : 5;
      return { item, grams: Math.max(step, pyRound(grams / step) * step), category: D.categories[item] || "other" };
    });
    const rank = (c) => (order.includes(c) ? order.indexOf(c) : 99);
    return items.sort((a, b) => rank(a.category) - rank(b.category) || (a.item < b.item ? -1 : a.item > b.item ? 1 : 0));
  }

  function plan(body) {
    const recipes = (body.recipes || []).map((r) => known[sig(r)]);
    if (!recipes.length || recipes.some((r) => !r)) return notInPreview();
    const condition = body.condition || "diabetes";
    const language = body.language || "English";
    const days = schedule(recipes, D.focusKey[condition]);
    const named = days.map((d) => ({ day: d.day, ...Object.fromEntries(["breakfast", "lunch", "dinner", "dessert"].map((s) => [s, d[s] === null ? null : recipes[d[s]].name])) }));
    return reply(200, {
      plan: {
        days: named,
        shopping_list: shopping(recipes, days),
        message_for_parent: D.messages[condition],
        language: language === "English" ? "English" : `English (written in ${language} when live)`,
        tips: D.tips[condition],
      },
      trace: mockTrace("Plan the week", "ultra"),
    });
  }

  window.__HP_PLAN__ = plan; // used by tests/test_preview.py
  const realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = async (url, opts = {}) => {
    const path = String(url);
    if (!path.startsWith("/api/")) return realFetch(url, opts);
    const body = opts.body ? JSON.parse(opts.body) : {};
    await new Promise((r) => setTimeout(r, 250)); // feel like a real request
    if (path === "/api/health") return reply(200, D.health);
    if (path === "/api/demo") return reply(200, D.demoList);
    const fam = path.match(/^\/api\/demo\/([a-z]+)$/);
    if (fam) return D.families[fam[1]] ? reply(200, D.families[fam[1]]) : reply(404, { detail: "Unknown demo family." });
    if (path === "/api/adapt") {
      const r = body.recipe || {};
      const hit = known[sig(r)] && D.adapt[`${r.id}|${body.condition || "diabetes"}`];
      return hit ? reply(200, hit) : notInPreview();
    }
    if (path === "/api/plan") return plan(body);
    if (path === "/api/parse") return notInPreview();
    return reply(404, { detail: "Not found." });
  };
})();
"""

BANNER = """<div class="preview-banner" role="note">Preview of demo mode: the four demo families run fully in your browser,
using numbers precomputed by the real engine. Adding your own recipes and live Nemotron need the full app.</div>"""


def build(out: Path) -> None:
    static = ROOT / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    body = re.sub(r'\s*<script src="/static/app.js"></script>', "", body)
    body = body.replace('<main id="main">', BANNER + '\n  <main id="main">', 1)
    css = (static / "styles.css").read_text(encoding="utf-8")
    css += """
:root { color-scheme: light; }
.preview-banner { background: var(--saffron-soft); color: var(--warn-ink); border-bottom: 1px solid var(--line);
  padding: 10px max(16px, env(safe-area-inset-right, 0px)) 10px max(16px, env(safe-area-inset-left, 0px));
  font-size: .95rem; text-align: center; }
"""
    data = json.dumps(precompute(), separators=(",", ":")).replace("</", "<\\/")
    app_js = (static / "app.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    page = f"""<title>Heritage Plate</title>
<meta name="description" content="Keep the family's food. Fix the numbers.">
<style>
{css}
</style>
{body}
<script>window.__HP_DATA__ = {data};</script>
<script>{SHIM}</script>
<script>{app_js}</script>
"""
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "preview.html"))
