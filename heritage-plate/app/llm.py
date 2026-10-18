"""Thin client for NVIDIA Nemotron models on Nebius Token Factory (OpenAI-compatible API)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from functools import lru_cache

# Verify both against your Token Factory console; run scripts/check_models.py.
BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/")
MODELS = {
    "nano": os.getenv("NEMOTRON_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    "super": os.getenv("NEMOTRON_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
    "ultra": os.getenv("NEMOTRON_ULTRA", "nvidia/nemotron-3-ultra-550b-a55b"),
}
CALL_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
DEADLINE_S = float(os.getenv("LLM_DEADLINE_S", "90"))  # whole chat_json call, retries included
# Nano and Super do structured, well-specified jobs; skip their reasoning traces to save tokens.
NO_THINK_TIERS = {"nano", "super"}

_cache: dict[str, tuple[dict, dict]] = {}


class LLMError(RuntimeError):
    pass


def is_live() -> bool:
    return bool(os.getenv("NEBIUS_API_KEY")) and os.getenv("MOCK", "0") != "1"


@lru_cache
def _client():
    from openai import OpenAI

    return OpenAI(base_url=BASE_URL, api_key=os.environ["NEBIUS_API_KEY"], timeout=CALL_TIMEOUT_S, max_retries=1)


def extract_json(text: str) -> dict:
    """Parse the first JSON object after any reasoning trace."""
    text = text.rsplit("</think>", 1)[-1]
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in model output")
    data, _ = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


def _create(model: str, messages: list[dict], max_tokens: int, no_think: bool):
    kwargs = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    if no_think:
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        return _client().chat.completions.create(**kwargs)
    except Exception as exc:
        # Some deployments reject chat_template_kwargs; retry once without it.
        if no_think and "chat_template" in str(exc).lower():
            kwargs.pop("extra_body")
            return _client().chat.completions.create(**kwargs)
        raise


def chat_json(tier: str, system: str, user: str, *, step: str, max_tokens: int = 2000) -> tuple[dict, dict]:
    """Call a Nemotron tier and parse a JSON object from the reply.

    Returns (data, trace). Ultra falls back to Super if its call fails, so a
    missing or overloaded model never breaks the demo. Identical requests are
    served from an in-memory cache.
    """
    key = hashlib.sha256(json.dumps([tier, system, user, max_tokens]).encode()).hexdigest()
    if key in _cache:
        data, trace = _cache[key]
        return data, {**trace, "cached": True, "ms": 0}

    started_all = time.perf_counter()
    tiers = [tier, "super"] if tier == "ultra" else [tier]
    last_error: Exception | None = None
    for current in tiers:
        model = MODELS[current]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tokens = 0
        for _attempt in range(2):
            if time.perf_counter() - started_all > DEADLINE_S:
                raise LLMError(f"{step}: timed out after {DEADLINE_S:.0f}s")
            try:
                resp = _create(model, messages, max_tokens, current in NO_THINK_TIERS)
            except Exception as exc:  # API or network error: try the next tier
                last_error = exc
                break
            choice = resp.choices[0]
            content = choice.message.content or ""
            usage = getattr(resp, "usage", None)
            tokens += getattr(usage, "total_tokens", 0) or 0
            try:
                if choice.finish_reason == "length":
                    raise ValueError("reply was cut off (max_tokens)")
                data = extract_json(content)
            except ValueError as exc:  # bad or truncated JSON: show it the reply and ask once more
                last_error = exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": content[-2000:]},
                    {"role": "user", "content": "That was not one complete JSON object. Reply with only the JSON object, shorter if needed."},
                ]
                continue
            trace = {
                "step": step,
                "tier": current,
                "model": model,
                "ms": round((time.perf_counter() - started_all) * 1000),
                "tokens": tokens or None,
                "fallback": current != tier,
                "cached": False,
            }
            _cache[key] = (data, trace)
            return data, trace
    raise LLMError(f"{step}: Nemotron call failed ({last_error})")
