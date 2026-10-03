"""LLMProvider interface + free fallback chain: Gemini -> Groq -> OpenRouter(:free) -> Ollama -> Mock.

generate_json() asks for JSON (using each provider's JSON mode), validates with Pydantic,
does ONE repair retry that includes the validation error, then falls through to the next provider."""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..cache import DiskCache, stable_hash
from ..config import settings
from ..logging_setup import log
from ..ratelimit import (ProviderUnavailable, RateLimited, TransientError, limiter, raise_for_status,
                         with_backoff)
from ..tracking import bypass_cache, tracker
from . import mock_data

logger = logging.getLogger("t2s.llm")
M = TypeVar("M", bound=BaseModel)
TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def configured(self) -> tuple[bool, str]:
        """(ok, reason). Missing key/model -> skip without calling."""

    @abstractmethod
    async def complete(self, system: str, prompt: str, json_mode: bool, schema: dict | None) -> str: ...

    async def ping(self) -> str:
        ok, why = self.configured()
        if not ok:
            return "missing_key"
        if limiter(self.name).is_rate_limited:
            return "rate_limited"
        try:
            await self._ping()
            return "available"
        except RateLimited:
            return "rate_limited"
        except Exception as e:  # noqa: BLE001
            log(logger, "ping failed", provider=self.name, error=str(e)[:200])
            return "unreachable"

    async def _ping(self) -> None:
        pass


class _OpenAICompatible(LLMProvider):
    url: str
    key_env: str
    model_env: str

    def _key(self) -> str: ...
    def _model(self) -> str: ...

    def configured(self) -> tuple[bool, str]:
        if not self._key():
            return False, f"missing key {self.key_env}"
        if not self._model():
            return False, f"missing model {self.model_env}"
        return True, ""

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}

    async def complete(self, system: str, prompt: str, json_mode: bool, schema: dict | None) -> str:
        body: dict[str, Any] = {
            "model": self._model(),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.7,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            try:
                r = await c.post(self.url, headers=self._headers(), json=body)
            except httpx.TransportError as e:
                raise TransientError(f"{self.name}: {e}") from e
        raise_for_status(self.name, r.status_code, dict(r.headers), r.text)
        return r.json()["choices"][0]["message"]["content"] or ""


class GroqProvider(_OpenAICompatible):
    name = "groq"
    url = "https://api.groq.com/openai/v1/chat/completions"
    key_env, model_env = "GROQ_API_KEY", "GROQ_MODEL"
    def _key(self) -> str: return settings.groq_api_key
    def _model(self) -> str: return settings.groq_model

    async def _ping(self) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.groq.com/openai/v1/models", headers=self._headers())
        raise_for_status(self.name, r.status_code, dict(r.headers), r.text)


class OpenRouterProvider(_OpenAICompatible):
    name = "openrouter"
    url = "https://openrouter.ai/api/v1/chat/completions"
    key_env, model_env = "OPENROUTER_API_KEY", "OPENROUTER_MODEL"
    def _key(self) -> str: return settings.openrouter_api_key
    def _model(self) -> str: return settings.openrouter_model

    def configured(self) -> tuple[bool, str]:
        ok, why = super().configured()
        if ok and not self._model().endswith(":free"):
            return False, "OPENROUTER_MODEL must end with ':free' (free-only constraint)"
        return ok, why

    async def _ping(self) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=self._headers())
        raise_for_status(self.name, r.status_code, dict(r.headers), r.text)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def configured(self) -> tuple[bool, str]:
        if not settings.gemini_api_key:
            return False, "missing key GEMINI_API_KEY"
        if not settings.gemini_model:
            return False, "missing model GEMINI_MODEL"
        return True, ""

    async def complete(self, system: str, prompt: str, json_mode: bool, schema: dict | None) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            try:
                r = await c.post(url, params={"key": settings.gemini_api_key}, json=body)
            except httpx.TransportError as e:
                raise TransientError(f"gemini: {e}") from e
        raise_for_status(self.name, r.status_code, dict(r.headers), r.text)
        data = r.json()
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise LLMError(f"gemini: unexpected response {str(data)[:300]}") from e

    async def _ping(self) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}",
                            params={"key": settings.gemini_api_key})
        raise_for_status(self.name, r.status_code, dict(r.headers), r.text)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def configured(self) -> tuple[bool, str]:
        if not settings.ollama_model:
            return False, "missing model OLLAMA_MODEL"
        return True, ""

    async def complete(self, system: str, prompt: str, json_mode: bool, schema: dict | None) -> str:
        body: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.7},
        }
        if json_mode:
            body["format"] = schema or "json"   # structured outputs when the server supports a schema
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as c:
            try:
                r = await c.post(f"{settings.ollama_host}/api/chat", json=body)
            except httpx.ConnectError as e:
                raise ProviderUnavailable(f"ollama not reachable at {settings.ollama_host} (run `ollama serve`)") from e
            except httpx.TransportError as e:
                raise TransientError(f"ollama: {e}") from e
        if r.status_code == 404:
            raise ProviderUnavailable(f"ollama model {settings.ollama_model!r} not pulled (run `ollama pull {settings.ollama_model}`)")
        raise_for_status(self.name, r.status_code, dict(r.headers), r.text)
        return r.json()["message"]["content"]

    async def _ping(self) -> None:
        async with httpx.AsyncClient(timeout=5) as c:
            try:
                r = await c.get(f"{settings.ollama_host}/api/tags")
            except httpx.TransportError as e:
                raise ProviderUnavailable(str(e)) from e
        raise_for_status(self.name, r.status_code)
        names = {m["name"] for m in r.json().get("models", [])}
        if settings.ollama_model not in names and f"{settings.ollama_model}:latest" not in names:
            raise ProviderUnavailable(f"model {settings.ollama_model} not pulled")


class MockProvider(LLMProvider):
    """Deterministic canned outputs per task, so the pipeline runs with no keys and no network."""
    name = "mock"

    def configured(self) -> tuple[bool, str]:
        return True, ""

    async def complete(self, system: str, prompt: str, json_mode: bool, schema: dict | None) -> str:
        raise NotImplementedError("mock uses complete_task")

    def complete_task(self, task: str, context: dict) -> dict:
        return mock_data.llm_response(task, context)

    async def _ping(self) -> None:
        return None


_REGISTRY: dict[str, LLMProvider] = {p.name: p for p in
                                     (GeminiProvider(), GroqProvider(), OpenRouterProvider(), OllamaProvider(), MockProvider())}


def chain() -> list[LLMProvider]:
    if settings.mock_mode:
        return [_REGISTRY["mock"]]
    order = [n.strip() for n in settings.llm_order.split(",") if n.strip() in _REGISTRY and n.strip() != "mock"]
    out = [_REGISTRY[n] for n in order]
    if settings.llm_mock_fallback:
        out.append(_REGISTRY["mock"])
    return out


def all_providers() -> list[LLMProvider]:
    return [p for n, p in _REGISTRY.items()]


_JSON_RE = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> Any:
    """Tolerate code fences / chatter around the JSON that small models add."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if not m:
            raise
        return json.loads(m.group(0))


_cache = DiskCache("llm")


async def generate_json(task: str, system: str, prompt: str, model: type[M],
                        context: dict | None = None, use_cache: bool = True) -> tuple[M, str]:
    """Returns (validated model, provider name). Raises LLMError if every provider fails."""
    t = tracker()
    key = stable_hash({"task": task, "system": system, "prompt": prompt, "schema": model.__name__,
                       "mock": settings.mock_mode})
    use_cache = use_cache and not bypass_cache.get()
    if use_cache and (hit := _cache.get(key)):
        try:
            obj = model.model_validate(hit["data"])
            t.used(task, hit["provider"], cached=True)
            return obj, hit["provider"]
        except ValidationError:
            pass

    schema = model.model_json_schema()
    sys_full = (f"{system}\nRespond with ONLY a JSON object matching this JSON Schema. No prose, no markdown.\n"
                f"{json.dumps(schema, separators=(',', ':'))}")
    errors: list[str] = []
    for prov in chain():
        ok, why = prov.configured()
        if not ok:
            t.fell_back(f"{prov.name}: skipped ({why})")
            continue
        if isinstance(prov, MockProvider):
            obj = model.model_validate(prov.complete_task(task, context or {}))
            t.used(task, prov.name)
            _cache.set(key, {"data": obj.model_dump(), "provider": prov.name})
            return obj, prov.name

        lim = limiter(prov.name)
        user_prompt = prompt
        for attempt in range(2):        # attempt 0 = normal, attempt 1 = repair
            try:
                raw = await with_backoff(lambda: lim.run(lambda: prov.complete(sys_full, user_prompt, True, schema)))
                t.add("llm_tokens_est", (len(sys_full) + len(user_prompt) + len(raw)) // 4)
                t.add("api_requests", 1)
                obj = model.model_validate(extract_json(raw))
                t.used(task, prov.name)
                if prov is not chain()[0]:
                    log(logger, "answered by fallback provider", task=task, provider=prov.name)
                _cache.set(key, {"data": obj.model_dump(), "provider": prov.name})
                return obj, prov.name
            except (ValidationError, json.JSONDecodeError, LLMError) as e:
                err = str(e)[:800]
                log(logger, "invalid JSON from provider", logging.WARNING, task=task, provider=prov.name,
                    attempt=attempt, error=err[:300])
                errors.append(f"{prov.name}: {err[:200]}")
                if attempt == 0:
                    user_prompt = (f"{prompt}\n\nYour previous answer was invalid:\n{err}\n"
                                   f"Return corrected JSON only.")
                    continue
                t.fell_back(f"{prov.name}: invalid JSON after repair")
            except RateLimited:
                t.fell_back(f"{prov.name}: rate-limited")
                errors.append(f"{prov.name}: rate limited")
            except (ProviderUnavailable, TransientError, httpx.HTTPError) as e:
                t.fell_back(f"{prov.name}: {str(e)[:120]}")
                errors.append(f"{prov.name}: {e}")
            break
    raise LLMError(f"All LLM providers failed for {task}. " + " | ".join(errors[-6:]) +
                   " Configure at least one of GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, or run Ollama"
                   " with OLLAMA_MODEL set, or set MOCK_MODE=true.")
