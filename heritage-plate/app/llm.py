"""Thin client for NVIDIA Nemotron models on Nebius Token Factory (OpenAI-compatible API)."""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache

# Verify both against your Token Factory console; run scripts/check_models.py.
BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/")
MODELS = {
    "nano": os.getenv("NEMOTRON_NANO", "nvidia/nemotron-3-nano-30b-a3b"),
    "super": os.getenv("NEMOTRON_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
    "ultra": os.getenv("NEMOTRON_ULTRA", "nvidia/nemotron-3-ultra-550b-a55b"),
}
TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "60"))


class LLMError(RuntimeError):
    pass


def is_live() -> bool:
    return bool(os.getenv("NEBIUS_API_KEY")) and os.getenv("MOCK", "0") != "1"


@lru_cache
def _client():
    from openai import OpenAI

    return OpenAI(base_url=BASE_URL, api_key=os.environ["NEBIUS_API_KEY"], timeout=TIMEOUT_S)


def _extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def chat_json(tier: str, system: str, user: str, *, step: str, max_tokens: int = 2000) -> tuple[dict, dict]:
    """Call a Nemotron tier and parse a JSON object from the reply.

    Returns (data, trace). Ultra falls back to Super if the call fails, so a
    missing or overloaded model never breaks the demo.
    """
    tiers = [tier, "super"] if tier == "ultra" else [tier]
    last_error: Exception | None = None
    for current in tiers:
        model = MODELS[current]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in range(2):
            started = time.perf_counter()
            try:
                resp = _client().chat.completions.create(
                    model=model, messages=messages, temperature=0.2, max_tokens=max_tokens
                )
                content = resp.choices[0].message.content or ""
                data = _extract_json(content)
            except ValueError as exc:  # bad JSON: ask once more, firmly
                last_error = exc
                messages = [*messages, {"role": "user", "content": "Reply with only one valid JSON object."}]
                continue
            except Exception as exc:  # API / network error: try the next tier
                last_error = exc
                break
            usage = getattr(resp, "usage", None)
            trace = {
                "step": step,
                "tier": current,
                "model": model,
                "ms": round((time.perf_counter() - started) * 1000),
                "tokens": getattr(usage, "total_tokens", None),
                "fallback": current != tier,
            }
            return data, trace
    raise LLMError(f"{step}: Nemotron call failed ({last_error})")
