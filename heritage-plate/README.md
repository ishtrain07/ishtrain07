# Heritage Plate

**Keep the family's food. Fix the numbers.**

Heritage Plate turns a family's real recipes, written or spoken the way a parent says them ("3 katori atta, 2 boiled aloo, ghee on top"), into versions that work for a parent's type 2 diabetes, high blood pressure or high cholesterol. It doesn't swap the family's food for bland diet food. Then it plans the week and writes the shopping list.

Built for the **Nebius x NVIDIA Global AI Hackathon** (Best Apps & Agents track).

## How it works

| Step | What happens | Powered by |
|---|---|---|
| Read recipe | Free-text or spoken recipe → structured ingredients in grams | **NVIDIA Nemotron 3 Nano** on Nebius Token Factory |
| Adapt dish | Up to 4 swaps that keep the dish recognizable (flour mix, less rice/ghee/sugar/salt, more vegetables) | **Nemotron 3 Super** |
| Plan the week | 7-day plan, warm message to the parent in their own language, tips | **Nemotron 3 Ultra** (falls back to Super automatically) |
| Nutrition and shopping list | Carbs, fibre, fat, sodium and kcal per serving, before and after; weekly quantities | **Plain code + `data/foods.csv`**, never the LLM |

The numbers come from a food-composition table, not from the model, so every "24% less net carbs" claim can be reproduced. The values are approximate and based on USDA FoodData Central and the Indian Food Composition Tables; verify them before any clinical use. The app's "Under the hood" panel shows which Nemotron tier ran each step, with latency and tokens.

## Run it

```bash
cd heritage-plate
pip install -r requirements.txt
cp .env.example .env               # add NEBIUS_API_KEY for live mode
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload
# open http://localhost:8000 → "Load demo family" → "Adapt all" → "Make our week"
```

- **Demo mode** (no key, or `MOCK=1`): deterministic swap rules stand in for the models, so the whole flow works offline.
- **Live mode:** set `NEBIUS_API_KEY`. Check the base URL and model IDs first:

```bash
python scripts/check_models.py
```

## Tests

```bash
python -m pytest -q
```

## Project layout

```
app/main.py        FastAPI routes (/api/health, /api/demo, /api/parse, /api/adapt, /api/plan)
app/engine.py      parse → adapt → plan pipeline (live Nemotron or mock rules)
app/llm.py         Token Factory client, JSON parsing, Ultra → Super fallback, trace
app/prompts.py     system prompts per Nemotron tier
app/nutrition.py   deterministic nutrition math over data/foods.csv
data/              food table and a fictional demo family
static/            single-page UI (plain HTML/CSS/JS)
```

## Disclaimer

General healthy-eating guidance, not medical advice. Check changes with a doctor or registered dietitian.

## License

MIT
