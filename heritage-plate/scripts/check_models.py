"""Check your Token Factory key and Nemotron model IDs.

Usage:  NEBIUS_API_KEY=... python scripts/check_models.py
Lists the NVIDIA models your account can see, then sends a one-line ping to
each configured tier so you know which IDs to put in .env.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import llm

if not llm.is_live():
    sys.exit("Set NEBIUS_API_KEY, or HP_LIVE=1 when the key is a network secret.")

client = llm._client()
print(f"Base URL: {llm.BASE_URL}\n")
try:
    nvidia = sorted(m.id for m in client.models.list().data if "nemotron" in m.id.lower() or "nvidia" in m.id.lower())
    print("NVIDIA models visible to this key:")
    for model_id in nvidia:
        print("  ", model_id)
except Exception as exc:  # noqa: BLE001 - listing is optional
    print("Could not list models:", exc)

print("\nPinging configured tiers:")
for tier, model in llm.MODELS.items():
    started = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "Reply with the word ok."}], max_tokens=20
        )
        ms = round((time.perf_counter() - started) * 1000)
        print(f"  {tier:5} OK   {model}  ({ms} ms): {resp.choices[0].message.content!r}")
    except Exception as exc:  # noqa: BLE001 - report every failure
        print(f"  {tier:5} FAIL {model}: {exc}")
