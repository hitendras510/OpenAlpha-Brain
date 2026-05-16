"""
OpenAlpha - Quant — LLM API Client
Supports Anthropic (default) and OpenAI via httpx.AsyncClient.
All retries use tenacity with exponential backoff.
API key is never logged.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

logger = logging.getLogger(__name__)

# HTTP status codes that warrant a retry
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Groq is OpenAI-compatible — just a different base URL
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(Exception):
    """Raised when the LLM fails permanently after all retries."""
    def __init__(self, message: str, cycle: int = 0, session_id: str = ""):
        super().__init__(message)
        self.cycle = cycle
        self.session_id = session_id


def _is_retryable(exc: BaseException) -> bool:
    """Return True for HTTP errors with retryable status codes."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUSES
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    return False


async def generate(
    system_prompt: str,
    history: list[dict],
    user_msg: str,
    session_id: str = "",
    cycle: int = 0,
) -> str:
    """
    Call the configured LLM and return the assistant text response.

    Args:
        system_prompt: The full IQC researcher system prompt (not in history).
        history: List of {role, content} dicts from prior turns.
        user_msg: The new user message for this call.
        session_id: For logging context only.
        cycle: For logging and error context only.

    Returns:
        Raw assistant response string.

    Raises:
        LLMError: On permanent failure after retries.
    """
    if not settings.LLM_API_KEY:
        raise LLMError(
            "LLM_API_KEY is not set. Add it to your .env file.",
            cycle=cycle,
            session_id=session_id,
        )

    provider = settings.LLM_PROVIDER.lower()
    if provider == "anthropic":
        return await _call_anthropic(system_prompt, history, user_msg, session_id, cycle)
    elif provider == "openai":
        return await _call_openai(system_prompt, history, user_msg, session_id, cycle)
    elif provider == "groq":
        return await _call_groq(system_prompt, history, user_msg, session_id, cycle)
    elif provider == "gemini":
        return await _call_gemini(system_prompt, history, user_msg, session_id, cycle)
    else:
        raise LLMError(
            f"Unknown LLM_PROVIDER '{provider}'. Use 'anthropic', 'openai', 'groq', or 'gemini'.",
            cycle=cycle,
            session_id=session_id,
        )


async def _call_anthropic(
    system_prompt: str,
    history: list[dict],
    user_msg: str,
    session_id: str,
    cycle: int,
) -> str:
    """Call Anthropic /v1/messages endpoint."""
    messages = [*history, {"role": "user", "content": user_msg}]

    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
        "system": system_prompt,
        "messages": messages,
    }

    headers = {
        "x-api-key": settings.LLM_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    raw_text = await _post_with_retry(
        url="https://api.anthropic.com/v1/messages",
        headers=headers,
        payload=payload,
        session_id=session_id,
        cycle=cycle,
    )

    import json
    data = json.loads(raw_text)

    # Anthropic wraps content in a list of blocks
    content_blocks = data.get("content", [])
    text = " ".join(
        block.get("text", "") for block in content_blocks if block.get("type") == "text"
    )

    # Warn if the model was cut off mid-response
    stop_reason = data.get("stop_reason", "")
    if stop_reason == "max_tokens":
        logger.warning(
            "[%s] cycle=%d Anthropic stop_reason=max_tokens — consider raising LLM_MAX_TOKENS",
            session_id, cycle,
        )

    return text.strip()


async def _call_openai(
    system_prompt: str,
    history: list[dict],
    user_msg: str,
    session_id: str,
    cycle: int,
) -> str:
    """Call OpenAI /v1/chat/completions endpoint."""
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_msg},
    ]

    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
        "messages": messages,
    }

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "content-type": "application/json",
    }

    raw_text = await _post_with_retry(
        url="https://api.openai.com/v1/chat/completions",
        headers=headers,
        payload=payload,
        session_id=session_id,
        cycle=cycle,
    )

    import json
    data = json.loads(raw_text)
    choice = data.get("choices", [{}])[0]

    finish_reason = choice.get("finish_reason", "")
    if finish_reason == "length":
        logger.warning(
            "[%s] cycle=%d OpenAI finish_reason=length — consider raising LLM_MAX_TOKENS",
            session_id, cycle,
        )

    return choice.get("message", {}).get("content", "").strip()


async def _call_groq(
    system_prompt: str,
    history: list[dict],
    user_msg: str,
    session_id: str,
    cycle: int,
) -> str:
    """
    Call Groq /openai/v1/chat/completions endpoint.
    Groq is fully OpenAI-compatible — only the base URL and auth header differ.
    Free tier: 30 RPM, 14,400 req/day. Recommended model: llama-3.3-70b-versatile.
    Get key at: https://console.groq.com/keys
    """
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_msg},
    ]
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "content-type": "application/json",
    }
    raw_text = await _post_with_retry(
        url=GROQ_BASE_URL,
        headers=headers,
        payload=payload,
        session_id=session_id,
        cycle=cycle,
    )
    import json
    data = json.loads(raw_text)
    choice = data.get("choices", [{}])[0]
    finish_reason = choice.get("finish_reason", "")
    if finish_reason == "length":
        logger.warning(
            "[%s] cycle=%d Groq finish_reason=length — consider raising LLM_MAX_TOKENS",
            session_id, cycle,
        )
    return choice.get("message", {}).get("content", "").strip()


async def _call_gemini(
    system_prompt: str,
    history: list[dict],
    user_msg: str,
    session_id: str,
    cycle: int,
) -> str:
    """
    Call Google Gemini generateContent REST endpoint.
    Free tier: 15 RPM, 1M tokens/day. Recommended model: gemini-1.5-flash.
    Get key at: https://aistudio.google.com/app/apikey
    """
    import json
    # Build Gemini contents list: system injected as first user turn
    contents = []
    # Gemini doesn't have a system role — inject system prompt as first user message
    contents.append({
        "role": "user",
        "parts": [{"text": system_prompt}],
    })
    contents.append({
        "role": "model",
        "parts": [{"text": "Understood. I am OpenAlpha - Quant, ready to conduct rigorous alpha research."}],
    })
    # Map prior history
    for turn in history:
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": turn["content"]}]})
    # Add current user message
    contents.append({"role": "user", "parts": [{"text": user_msg}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": settings.LLM_MAX_TOKENS,
            "temperature": settings.LLM_TEMPERATURE,
        },
    }
    url = GEMINI_BASE_URL.format(model=settings.LLM_MODEL)
    headers = {"content-type": "application/json"}
    # Gemini auth: key in query param, not header
    url_with_key = f"{url}?key={settings.LLM_API_KEY}"

    raw_text = await _post_with_retry(
        url=url_with_key,
        headers=headers,
        payload=payload,
        session_id=session_id,
        cycle=cycle,
    )
    data = json.loads(raw_text)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        logger.error("[%s] cycle=%d Gemini response parse error: %s | raw: %s",
                     session_id, cycle, exc, raw_text[:200])
        raise LLMError(f"Gemini response parse error: {exc}", cycle=cycle, session_id=session_id)


async def _post_with_retry(
    url: str,
    headers: dict,
    payload: dict,
    session_id: str,
    cycle: int,
) -> str:
    """POST with up to 5 retries and exponential backoff on retryable errors."""
    import tenacity
    last_exc: Exception | None = None

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_retryable),
            wait=wait_exponential(multiplier=2, min=5, max=60),  # longer waits for 429
            stop=stop_after_attempt(5),   # 5 attempts total
            reraise=False,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        status = exc.response.status_code
                        # Log Retry-After header if present (OpenAI provides it on 429)
                        retry_after = exc.response.headers.get("Retry-After", "unknown")
                        logger.warning(
                            "[%s] cycle=%d HTTP %d from LLM — retry-after=%s",
                            session_id, cycle, status, retry_after,
                        )
                        last_exc = exc
                        raise

                    raw = resp.text
                    logger.debug("[%s] cycle=%d LLM raw response: %s", session_id, cycle, raw)
                    return raw
    except tenacity.RetryError as retry_err:
        raise LLMError(
            f"LLM call failed after 5 retries (last: {last_exc})",
            cycle=cycle,
            session_id=session_id,
        ) from retry_err

    # Unreachable — tenacity either returns or raises RetryError
    raise LLMError(
        f"LLM call failed permanently. Last error: {last_exc}",
        cycle=cycle,
        session_id=session_id,
    )
