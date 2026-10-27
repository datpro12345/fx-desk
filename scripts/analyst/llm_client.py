"""Model-agnostic LLM client: OpenRouter and Google AI Studio."""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DEFAULT_FM_OPENROUTER_TOOLS = "/Users/datpro/Documents/Codex/firstmate/data/tools/openrouter"
OPENROUTER_CALLER = "fx-desk:weekly-outlook"
OPENROUTER_TASK_CLASS = "search-summary"

# Weekly outlook fallback when the shared router is absent (models open on 2026-10-27).
PREFERRED_OPENROUTER_MODELS = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "openrouter/free",
)
DEFAULT_OPENROUTER_MODEL = PREFERRED_OPENROUTER_MODELS[0]  # used when .env has no model

_SHARED_ROUTER_UNKNOWN = object()
_shared_router: Any = _SHARED_ROUTER_UNKNOWN


class LLMError(RuntimeError):
    pass


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or (REPO_ROOT / ".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _openrouter_tools_dir() -> Path:
    return Path(os.environ.get("FM_OPENROUTER_TOOLS", DEFAULT_FM_OPENROUTER_TOOLS))


def _load_shared_openrouter() -> tuple[Callable[[str], list[str]], Callable[[], Any]] | None:
    """Return (pick_chain, get_client) when the fleet router is importable."""
    global _shared_router
    if _shared_router is not _SHARED_ROUTER_UNKNOWN:
        return _shared_router

    tools_dir = _openrouter_tools_dir()
    if not tools_dir.is_dir():
        log.warning(
            "Shared OpenRouter router not found at %s; using local PREFERRED_OPENROUTER_MODELS.",
            tools_dir,
        )
        _shared_router = None
        return None

    path = str(tools_dir)
    inserted = False
    if path not in sys.path:
        sys.path.insert(0, path)
        inserted = True
    try:
        from or_models import pick_chain  # type: ignore[import-not-found]
        from orclient import get_client  # type: ignore[import-not-found]

        _shared_router = (pick_chain, get_client)
        return _shared_router
    except Exception as exc:
        log.warning(
            "Shared OpenRouter router import failed (%s); using local PREFERRED_OPENROUTER_MODELS.",
            exc,
        )
        _shared_router = None
        return None
    finally:
        if inserted and _shared_router is None:
            try:
                sys.path.remove(path)
            except ValueError:
                pass


def _openrouter_model_candidates(
    chain: Iterable[str],
    *,
    explicit_model: str | None,
    env_model: str,
) -> list[str]:
    ordered = [explicit_model, *chain, env_model]
    return list(dict.fromkeys(m for m in ordered if m))


def _http_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"HTTP {exc.code} from {url}: {detail[:800]}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Network error calling {url}: {exc}") from exc


def complete_openrouter(
    system: str,
    user: str,
    model: str,
    api_key: str,
    timeout: int = 180,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/datpro12345/ff-transform-data",
        "X-Title": "ff-transform-data weekly analyst",
    }
    data = _http_json(OPENROUTER_URL, payload, headers, timeout)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected OpenRouter response: {data!r}"[:800]) from exc


def _complete_openrouter_shared(
    system: str,
    user: str,
    models: list[str],
    timeout: int,
    client: Any,
    allow_paid: bool,
) -> tuple[str, str]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        result = client.chat_completion(
            messages=messages,
            models=models,
            timeout=timeout,
            temperature=0.2,
            caller=OPENROUTER_CALLER,
            allow_paid=allow_paid,
        )
    except Exception as exc:
        raise LLMError(str(exc)) from exc
    try:
        text = result["content"].strip()
        used_model = result["model"]
    except (KeyError, TypeError) as exc:
        raise LLMError(f"Unexpected shared router response: {result!r}"[:800]) from exc
    return text, used_model


def complete_google(
    system: str,
    user: str,
    model: str,
    api_key: str,
    timeout: int = 180,
) -> str:
    url = GEMINI_URL.format(model=model) + f"?key={api_key}"
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2},
    }
    headers = {"Content-Type": "application/json"}
    data = _http_json(url, payload, headers, timeout)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected Gemini response: {data!r}"[:800]) from exc


def complete(
    system: str,
    user: str,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = 180,
) -> tuple[str, str, str]:
    """Return (text, provider, model). Provider/model fall back to env."""
    load_dotenv()
    chosen = (provider or os.environ.get("LLM_PROVIDER") or "openrouter").strip().lower()
    if chosen == "openrouter":
        env_model = (os.environ.get("OPENROUTER_MODEL") or "").strip()
        shared = _load_shared_openrouter()
        if shared is not None:
            pick_chain, get_client = shared
            client = get_client()
            models = _openrouter_model_candidates(
                pick_chain(OPENROUTER_TASK_CLASS),
                explicit_model=model,
                env_model=env_model,
            )
            allow_paid = any(not client.is_free_model(m) for m in (model, env_model) if m)
            text, used_model = _complete_openrouter_shared(
                system, user, models, timeout, client, allow_paid
            )
            return text, chosen, used_model

        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key or api_key.startswith("your_"):
            raise LLMError("OPENROUTER_API_KEY is missing in .env")
        candidates = _openrouter_model_candidates(
            PREFERRED_OPENROUTER_MODELS,
            explicit_model=model,
            env_model=env_model,
        )
        last_error: LLMError | None = None
        for used_model in candidates:
            try:
                text = complete_openrouter(system, user, used_model, api_key, timeout)
                return text, chosen, used_model
            except LLMError as exc:
                last_error = exc
                if "404" not in str(exc) or used_model == candidates[-1]:
                    raise
        raise last_error or LLMError("OpenRouter complete failed")
    if chosen in {"google", "gemini"}:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key or api_key.startswith("your_"):
            raise LLMError("GEMINI_API_KEY is missing in .env")
        used_model = model or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
        return complete_google(system, user, used_model, api_key, timeout), chosen, used_model
    raise LLMError(f"Unknown LLM_PROVIDER={chosen!r} (use openrouter or google)")
