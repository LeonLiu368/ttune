"""Before any model request: check the model exists on OpenRouter and, unless paid runs are allowed, that it's free."""

from __future__ import annotations

import httpx

MODELS_URL = "https://openrouter.ai/api/v1/models"
FREE = "free"
# Small open instruct models (3-8B), in order of preference, for model="free".
FREE_PREFERENCES = (
    "meta-llama/llama-3.1-8b-instruct:free",
    "qwen/qwen3-8b:free",
    "qwen/qwen-2.5-7b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-3-4b-it:free",
    "meta-llama/llama-3.2-3b-instruct:free",
)
PRICE_FIELDS = ("prompt", "completion", "request")


class CostGuardError(Exception):
    pass


def fetch_models(url: str = MODELS_URL) -> list[dict]:
    resp = httpx.get(url, timeout=60, headers={"X-Title": "ttune evals"})
    resp.raise_for_status()
    return resp.json()["data"]


def is_free(model: dict) -> bool:
    pricing = model.get("pricing") or {}
    try:
        return all(float(pricing.get(field) or 0) == 0 for field in PRICE_FIELDS)
    except (TypeError, ValueError):
        return False


def choose_model(models: list[dict], requested: str, allow_paid: bool) -> dict:
    """The model to run. Raises CostGuardError if it's unknown, or costs money and paid runs aren't allowed."""
    by_id = {m["id"]: m for m in models}
    if requested == FREE:
        for slug in FREE_PREFERENCES:
            if slug in by_id and is_free(by_id[slug]):
                return by_id[slug]
        free = sorted(m["id"] for m in models if is_free(m))
        raise CostGuardError(f"none of the preferred free models is listed; free models now: {', '.join(free[:40])}")
    if requested not in by_id:
        raise CostGuardError(f"OpenRouter doesn't list a model called {requested!r}")
    model = by_id[requested]
    if not is_free(model) and not allow_paid:
        raise CostGuardError(f"{requested} costs money ({model.get('pricing')}); refusing to run it. "
                             "Choose a free (:free) model, or set allow_paid to run it anyway.")
    return model
