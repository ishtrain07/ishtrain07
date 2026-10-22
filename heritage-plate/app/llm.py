"""Thin client for NVIDIA Nemotron models on Nebius Token Factory (OpenAI-compatible API)."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from functools import lru_cache

# Verify both against your Token Factory console; run scripts/check_models.py.
BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/")
MODELS = {
    "nano": os.getenv("NEMOTRON_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    "super": os.getenv("NEMOTRON_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
    "ultra": os.getenv("NEMOTRON_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b"),
}
CALL_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
# Ultra reasons before answering; 30 s would time it out and always fall back to Super.
TIER_TIMEOUT_S = {"ultra": float(os.getenv("LLM_TIMEOUT_ULTRA_S", "60"))}
DEADLINE_S = float(os.getenv("LLM_DEADLINE_S", "90"))  # whole chat_json call, retries included
# Nano and Super do structured, well-specified jobs; skip their reasoning traces to save tokens.
NO_THINK_TIERS = {"nano", "super"}

CACHE_SIZE = 512
_cache: OrderedDict[str, tuple[dict, dict]] = OrderedDict()
_cache_lock = threading.Lock()
# Process-wide cap on paid model calls per hour: the real guard on credits for a public URL.
MAX_CALLS_PER_HOUR = int(os.getenv("MAX_CALLS_PER_HOUR", "600"))
_calls: list[float] = []
_calls_lock = threading.Lock()
# Flipped off the first time the endpoint rejects chat_template_kwargs.
_send_template_kwargs = True


class LLMError(RuntimeError):
    pass


# When the key is a network secret (injected into outbound requests by a proxy),
# the app never sees it: set HP_LIVE=1 and a placeholder is sent instead.
PLACEHOLDER_KEY = "injected-by-network-secret"


def is_live() -> bool:
    has_key = bool(os.getenv("NEBIUS_API_KEY")) or os.getenv("HP_LIVE", "0") == "1"
    return has_key and os.getenv("MOCK", "0") != "1"


def tracing_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").lower() == "true"


@lru_cache
def _client():
    from openai import OpenAI

    # No SDK retries: chat_json owns retries so the deadline is a real ceiling.
    client = OpenAI(
        base_url=BASE_URL,
        api_key=os.getenv("NEBIUS_API_KEY") or PLACEHOLDER_KEY,
        timeout=CALL_TIMEOUT_S,
        max_retries=0,
    )
    if tracing_enabled():
        # Optional LangSmith tracing: every Nemotron call becomes a trace (model, tokens, latency).
        # Configure with LANGSMITH_TRACING=true, LANGSMITH_ENDPOINT, LANGSMITH_PROJECT, LANGSMITH_API_KEY.
        try:
            from langsmith.wrappers import wrap_openai

            os.environ.setdefault("LANGSMITH_API_KEY", PLACEHOLDER_KEY)
            client = wrap_openai(client)
        except ImportError:
            pass
    return client


def extract_json(text: str) -> dict:
    """Parse the first JSON object after any reasoning trace."""
    text = text.rsplit("</think>", 1)[-1]
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:  # a stray brace in leading prose shouldn't cost a retry
        try:
            data, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(data, dict):
            return data
        start = text.find("{", start + 1)
    raise ValueError("no JSON object in model output")


def _take_budget() -> None:
    now = time.monotonic()
    with _calls_lock:
        while _calls and now - _calls[0] > 3600:
            _calls.pop(0)
        if len(_calls) >= MAX_CALLS_PER_HOUR:
            raise LLMError("hourly model budget used up; try again later")
        _calls.append(now)


def _transient(exc: Exception) -> bool:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )

    return isinstance(exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError))


def _create(model: str, messages: list[dict], max_tokens: int, no_think: bool, timeout: float):
    global _send_template_kwargs
    from openai import BadRequestError

    kwargs = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens, "timeout": timeout}
    if no_think and _send_template_kwargs:
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        return _client().chat.completions.create(**kwargs)
    except BadRequestError as exc:
        # Some gateways reject chat_template_kwargs; stop sending it and retry once.
        if "extra_body" not in kwargs or not any(k in str(exc) for k in ("chat_template_kwargs", "enable_thinking")):
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
    with _cache_lock:
        hit = _cache.get(key)
        if hit:
            _cache.move_to_end(key)
    if hit:
        data, trace = hit
        return data, {**trace, "cached": True, "ms": 0}

    started_all = time.perf_counter()
    tiers = [tier, "super"] if tier == "ultra" else [tier]
    last_error: Exception | None = None
    for current in tiers:
        model = MODELS[current]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tokens = prompt_tokens = completion_tokens = 0
        timeout = TIER_TIMEOUT_S.get(current, CALL_TIMEOUT_S)
        retried = False
        attempt = 0
        while attempt < 2:
            attempt += 1
            remaining = DEADLINE_S - (time.perf_counter() - started_all)
            if remaining < 2:
                raise LLMError(f"{step}: timed out after {DEADLINE_S:.0f}s")
            _take_budget()
            try:
                resp = _create(model, messages, max_tokens, current in NO_THINK_TIERS, min(timeout, remaining))
            except Exception as exc:  # noqa: BLE001 - any API/network error: retry once if brief, else next tier
                last_error = exc
                # Ultra has Super behind it; Nano and Super get one quick retry on a transient error.
                if current != "ultra" and not retried and _transient(exc) and remaining > 5:
                    retried = True
                    attempt -= 1
                    time.sleep(0.8)
                    continue
                break
            usage = getattr(resp, "usage", None)
            tokens += getattr(usage, "total_tokens", 0) or 0
            prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens += getattr(usage, "completion_tokens", 0) or 0
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
                "prompt_tokens": prompt_tokens or None,
                "completion_tokens": completion_tokens or None,
                "fallback": current != tier,
                "cached": False,
            }
            if not trace["fallback"]:  # don't pin a temporary Ultra failure in the cache
                with _cache_lock:
                    _cache[key] = (data, trace)
                    if len(_cache) > CACHE_SIZE:
                        _cache.popitem(last=False)
            return data, trace
    raise LLMError(f"{step}: Nemotron call failed ({last_error})")
