"""Run the whole demo flow against live Nemotron and report latency, tokens and cost.

Usage:  HP_LIVE=1 python scripts/live_run.py
Adapts every dish of the 4 demo families, plans each family's week, then reads,
adapts and plans one typed recipe. Prints one row per model call and totals.

Cost needs your Token Factory prices (USD per 1M tokens, input,output), e.g.
  HP_PRICE_NANO=0.06,0.24 HP_PRICE_SUPER=0.30,0.90 HP_PRICE_ULTRA=0.60,1.80
Without them the cost column is left blank.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app import llm
from app.main import app

TYPED = {
    "text": "Aloo gobi: 3 boiled aloo, 1 gobi, 2 onion, 2 tomato, 3 spoon ghee, 1 tsp salt, haldi, jeera",
    "cuisine": "south_asian",
    "condition": "diabetes",
    "language": "Hindi",
}


def _prices() -> dict[str, tuple[float, float]]:
    out = {}
    for tier in llm.MODELS:
        raw = os.getenv(f"HP_PRICE_{tier.upper()}", "")
        try:
            inp, outp = (float(x) for x in raw.split(","))
            out[tier] = (inp, outp)
        except ValueError:
            pass
    return out


def main() -> None:
    if not llm.is_live():
        sys.exit("Live mode is off: set NEBIUS_API_KEY, or HP_LIVE=1 for a network-secret key.")
    client = TestClient(app)
    rows: list[dict] = []

    def post(path: str, body: dict, label: str) -> dict:
        started = time.perf_counter()
        resp = client.post(path, json=body)
        wall = round((time.perf_counter() - started) * 1000)
        if resp.status_code != 200:
            print(f"  FAIL {label} {path}: {resp.status_code} {resp.text[:200]}")
            rows.append({"label": label, "step": path, "tier": "-", "model": "-", "ms": wall, "error": True})
            return {}
        data = resp.json()
        for t in data["trace"]:
            rows.append({"label": label, **t})
        return data

    def run_family(label: str, recipes: list[dict], cuisine: str, condition: str, language: str) -> None:
        adapted = []
        for r in recipes:
            out = post("/api/adapt", {"recipe": r, "condition": condition, "cuisine": cuisine}, label)
            if out:
                adapted.append(out["recipe"])
        if adapted:
            post("/api/plan", {"recipes": adapted, "condition": condition, "language": language}, label)

    for fam in client.get("/api/demo").json():
        full = client.get(f"/api/demo/{fam['id']}").json()
        print(f"{fam['id']}: {len(full['recipes'])} dishes, {fam['condition']}, {fam['language']}")
        run_family(fam["id"], full["recipes"], fam["cuisine"], fam["condition"], fam["language"])

    print("typed recipe")
    parsed = post("/api/parse", {"text": TYPED["text"], "cuisine": TYPED["cuisine"]}, "typed")
    if parsed:
        run_family("typed", [parsed["recipe"]], TYPED["cuisine"], TYPED["condition"], TYPED["language"])

    prices = _prices()
    print(f"\n{'run':7} {'step':14} {'tier':6} {'ms':>7} {'in':>6} {'out':>6} {'cost $':>9}  notes")
    total_cost, total_tokens, any_cost = 0.0, 0, False
    for r in rows:
        cost = ""
        if r.get("tier") in prices and r.get("prompt_tokens") is not None:
            inp, outp = prices[r["tier"]]
            c = (r["prompt_tokens"] * inp + (r.get("completion_tokens") or 0) * outp) / 1e6
            total_cost += c
            any_cost = True
            cost = f"{c:.5f}"
        total_tokens += r.get("tokens") or 0
        notes = ", ".join(
            n for n, on in (("ERROR", r.get("error")), ("FELL BACK to Super", r.get("fallback")),
                            ("cached", r.get("cached")), ("schedule rejected", r.get("schedule_valid") is False)) if on
        )
        print(f"{r['label']:7} {r['step'][:14]:14} {r['tier']:6} {r['ms']:>7} {r.get('prompt_tokens') or '':>6} "
              f"{r.get('completion_tokens') or '':>6} {cost:>9}  {notes}")

    calls = [r for r in rows if not r.get("error") and not r.get("cached")]
    by_tier: dict[str, list[int]] = {}
    for r in calls:
        by_tier.setdefault(r["tier"], []).append(r["ms"])
    print(f"\n{len(rows)} calls, {sum(1 for r in rows if r.get('error'))} errors, {total_tokens} tokens"
          + (f", ${total_cost:.4f}" if any_cost else ", cost: set HP_PRICE_<TIER> to compute"))
    for tier, ms in sorted(by_tier.items()):
        ms.sort()
        print(f"  {tier:5} n={len(ms):2}  median {ms[len(ms) // 2]} ms  max {ms[-1]} ms")
    plans = [r for r in rows if r.get("step") == "Plan the week" and not r.get("error")]
    fell_back = sum(1 for r in plans if r.get("fallback"))
    print(f"  Ultra fell back to Super on {fell_back}/{len(plans)} plans")


if __name__ == "__main__":
    main()
