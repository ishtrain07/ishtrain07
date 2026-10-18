"""Thin client for NVIDIA Nemotron models on Nebius Token Factory (OpenAI-compatible API)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
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

CACHE_SIZE = 512
_cache: OrderedDict[str, tuple[dict, dict]] = OrderedDict()
# Flipped off the first time the endpoint rejects chat_template_kwargs.
_send_template_kwargs = True


class LLMError(RuntimeError):
    pass


def is_live() -> bool:
    return bool(os.getenv("NEBIUS_API_KEY")) and os.getenv("MOCK", "0") != "1"


@lru_cache
def _client():
    from openai import OpenAI

    # No SDK retries: chat_json owns retries so the deadline is a real ceiling.
    return OpenAI(base_url=BASE_URL, api_key=os.environ["NEBIUS_API_KEY"], timeout=CALL_TIMEOUT_S, max_retries=0)


def extract_json(text: str) -> dict:
    """Parse the first JSON object after any reasoning trace."""
    text = text.rsplit("</think>", 1)[-1]
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in model output")
    data, _ = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")  # noqa: TRY004 - callers handle ValueError
    return data


def _create(model: str, messages: list[dict], max_tokens: int, no_think: bool, timeout: float):
    global _send_template_kwargs
    from openai import BadRequestError

    kwargs = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens, "timeout": timeout}
    if no_think and _send_template_kwargs:
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        return _client().chat.completions.create(**kwargs)
    except BadRequestError:
        # Some gateways reject chat_template_kwargs; stop sending it and retry once.
        if "extra_body" not in kwargs:
            raise
        _send_template_kwargs = False
        kwargs.pop("extra_body")
        return _client().chat.completions.create(**kwargs)


def chat_json(tier: str, system: str, user: str, *, step: str, max_tokens: int = 2000) -> tuple[dict, dict]:
    """Call a Nemotron tier and parse a JSON object from the reply.

    Returns (data, trace). Ultra falls back to Super if its call fails, so a
    missing or overloaded model never breaks the demo. Identical requests are
    served from an in-memory cache.
    """
    key = hashlib.sha256(json.dumps([tier, system, user, max_tokens]).encode()).hexdigest()
    if key in _cache:
        _cache.move_to_end(key)
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
            remaining = DEADLINE_S - (time.perf_counter() - started_all)
            if remaining < 2:
                raise LLMError(f"{step}: timed out after {DEADLINE_S:.0f}s")
            try:
                resp = _create(model, messages, max_tokens, current in NO_THINK_TIERS, min(CALL_TIMEOUT_S, remaining))
            except Exception as exc:  # noqa: BLE001 - any API/network error: try the next tier
                last_error = exc
                break
            usage = getattr(resp, "usage", None)
            tokens += getattr(usage, "total_tokens", 0) or 0
            choice = resp.choices[0] if resp.choices else None
            content = (choice.message.content or "") if choice else ""
            try:
                if choice is None:
                    raise ValueError("empty reply")
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
            if not trace["fallback"]:  # don't pin a temporary Ultra failure in the cache
                _cache[key] = (data, trace)
                if len(_cache) > CACHE_SIZE:
                    _cache.popitem(last=False)
            return data, trace
    raise LLMError(f"{step}: Nemotron call failed ({last_error})")
