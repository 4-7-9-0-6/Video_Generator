"""OpenRouter LLM provider — free `:free` models for songwriting / script generation.

OpenAI-compatible chat API. Key-gated and free (a `:free` model costs $0). Free model IDs
DRIFT and individual models get rate-limited upstream, so this provider discovers the live
`:free` roster from OpenRouter and tries them in a creative-writing preference order, using
the first that answers. The configured OPENROUTER_MODEL is always tried first. Get a free key
at https://openrouter.ai and set OPENROUTER_API_KEY in backend/.env.
"""
from __future__ import annotations

from ...config import settings
from ..base import Availability, Capability, LLMProvider, ProviderInfo

# prefer big general-purpose instruct models for songwriting; avoid coder/safety/vision/tiny
_PREFER = ["hermes-3", "gpt-oss-120b", "nemotron-3-super", "nemotron-3-ultra",
           "qwen3-next", "gemma-4-31b", "llama-3.3-70b", "gpt-oss-20b", "gemma-4", "nemotron"]
_AVOID = ["coder", "safety", "-vl", "thinking", "content", "1.2b", "laguna", "-3b", "nano"]
_SKIP_CODES = {404, 429, 502, 503}        # this model is busy/missing -> try the next one


class OpenRouterLLMProvider(LLMProvider):
    info = ProviderInfo(
        name="openrouter", capability=Capability.LLM, kind="cloud",
        free=True, requires_gpu=False,
    )

    def __init__(self) -> None:
        self._free_cache: list[str] | None = None

    def availability(self) -> Availability:
        if not settings.openrouter_api_key:
            return Availability(
                False, reason="OPENROUTER_API_KEY not set",
                install_hint="Add a free key (https://openrouter.ai) to backend/.env: "
                             "OPENROUTER_API_KEY=sk-or-...",
            )
        return Availability(True, reason=f"OpenRouter free LLM ({settings.openrouter_model})")

    async def _free_models(self, client) -> list[str]:
        if self._free_cache is None:
            try:
                r = await client.get(f"{settings.openrouter_api_base}/models",
                                     headers={"Authorization": f"Bearer {settings.openrouter_api_key}"})
                self._free_cache = [m["id"] for m in r.json().get("data", [])
                                    if str(m.get("id", "")).endswith(":free")]
            except Exception:  # noqa: BLE001 — discovery is best-effort
                self._free_cache = []
        return self._free_cache

    @staticmethod
    def _rank(mid: str):
        if any(a in mid for a in _AVOID):
            return (2, 99)
        for i, p in enumerate(_PREFER):
            if p in mid:
                return (0, i)
        return (1, 0)

    async def complete(self, prompt: str, *, system: str = "", temperature: float = 0.7,
                       max_tokens: int = 2048, **kw: object) -> str:
        import httpx

        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://toonforge.local",
            "X-Title": "ToonForge Studio",
        }
        url = f"{settings.openrouter_api_base}/chat/completions"
        primary = str(kw.get("model") or settings.openrouter_model)

        errors: list[str] = []
        async with httpx.AsyncClient(timeout=180) as client:
            free = await self._free_models(client)
            ordered = [primary] + [m for m in sorted(free, key=self._rank) if m != primary]
            for model in ordered[:8]:        # cap attempts so a bad day fails fast
                payload = {"model": model, "messages": messages,
                           "temperature": temperature, "max_tokens": max_tokens}
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                except httpx.HTTPError as e:
                    errors.append(f"{model}: {e}")
                    continue
                if resp.status_code == 200:
                    try:
                        return resp.json()["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, ValueError):
                        errors.append(f"{model}: malformed response")
                        continue
                if resp.status_code == 401:
                    raise RuntimeError("OpenRouter rejected the API key (401). Check OPENROUTER_API_KEY.")
                if resp.status_code in _SKIP_CODES:
                    errors.append(f"{model}: {resp.status_code}")
                    continue
                errors.append(f"{model}: {resp.status_code} {resp.text[:100]}")

        raise RuntimeError(
            "No free OpenRouter model answered right now (free models get rate-limited "
            "upstream). Try again in a minute, or set OPENROUTER_MODEL to a specific :free "
            "model. Tried — " + "; ".join(errors)[:400])
