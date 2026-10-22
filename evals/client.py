"""A minimal OpenAI-compatible chat client: temperature 0, retries with backoff, capped concurrency."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field

import httpx

OPENROUTER = "https://openrouter.ai/api/v1"
RETRY_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
# These fail every request the same way (bad key, no credit, unknown model), so the run stops at once.
FATAL_STATUSES = {401, 402, 403, 404}


class ApiError(Exception):
    """One request failed after every retry."""


class FatalApiError(ApiError):
    """Every request will fail the same way; stop the run."""


@dataclass
class Completion:
    text: str
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens and, on OpenRouter, cost
    attempts: int = 1
    finish_reason: str | None = None  # "length" means the reply was cut off at max_tokens


class ChatClient:
    def __init__(self, model: str, base_url: str = OPENROUTER, api_key: str | None = None, *,
                 concurrency: int = 8, timeout: float = 180.0, retries: int = 5, backoff: float = 2.0,
                 max_tokens: int = 8000, reasoning_effort: str | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.is_openrouter = self.base_url.startswith("https://openrouter.ai")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if self.is_openrouter and not self.api_key:
            raise FatalApiError("OPENROUTER_API_KEY isn't set")
        self.retries, self.backoff, self.max_tokens = retries, backoff, max_tokens
        self.reasoning_effort = reasoning_effort
        self._semaphore = asyncio.Semaphore(concurrency)
        headers = {"X-Title": "ttune evals", "HTTP-Referer": "https://github.com/LeonLiu368/ttune"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._http = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(self, messages: list[dict]) -> Completion:
        body = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens}
        if self.is_openrouter:
            body["usage"] = {"include": True}  # report tokens and cost in each response
        if self.reasoning_effort:
            body["reasoning"] = {"effort": self.reasoning_effort}  # OpenRouter's switch for thinking models
        error = ""
        async with self._semaphore:
            for attempt in range(1, self.retries + 1):
                try:
                    resp = await self._http.post(f"{self.base_url}/chat/completions", json=body)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    await self._wait(attempt, None)
                    continue
                if resp.status_code in FATAL_STATUSES:
                    raise FatalApiError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                if resp.status_code in RETRY_STATUSES:
                    error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    await self._wait(attempt, resp.headers.get("retry-after"))
                    continue
                if resp.status_code != 200:
                    raise ApiError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                if "error" in data:  # OpenRouter can report a provider error with HTTP 200
                    error = f"provider error: {str(data['error'])[:200]}"
                    await self._wait(attempt, None)
                    continue
                try:
                    choice = data["choices"][0]
                    text = choice["message"].get("content") or ""
                except (KeyError, IndexError, TypeError):
                    error = f"unexpected response: {str(data)[:200]}"
                    await self._wait(attempt, None)
                    continue
                return Completion(text, data.get("usage") or {}, attempt, choice.get("finish_reason"))
        raise ApiError(f"{error} (after {self.retries} attempts)")

    async def _wait(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= self.retries:
            return
        delay = self.backoff * 2 ** (attempt - 1)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        await asyncio.sleep(min(delay, 60))
