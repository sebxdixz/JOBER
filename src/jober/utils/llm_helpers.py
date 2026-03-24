"""Helpers for LLM output cleanup and resilient invocation."""

from __future__ import annotations

import re

from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from jober.core.logging import logger


RETRYABLE_LLM_MARKERS = (
    "429",
    "rate limit",
    "rate_limit",
    "too many requests",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "server disconnected",
    "overloaded",
)


def strip_markdown_fences(text: str) -> str:
    """Strip fenced markdown blocks from an LLM response."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def is_retryable_llm_exception(exc: Exception) -> bool:
    """Return True when an LLM failure looks transient."""
    message = str(exc).lower()
    if any(marker in message for marker in RETRYABLE_LLM_MARKERS):
        return True
    return exc.__class__.__name__.lower() in {
        "ratelimiterror",
        "apiconnectionerror",
        "apitimeouterror",
        "internalservererror",
    }


async def ainvoke_with_retry(
    llm,
    messages,
    *,
    operation: str,
    max_attempts: int = 4,
    wait_strategy=None,
):
    """Invoke an LLM with exponential backoff on transient failures."""
    wait_strategy = wait_strategy or wait_exponential(multiplier=2, min=4, max=20)

    def _before_sleep(retry_state) -> None:
        exc = retry_state.outcome.exception()
        logger.warning(
            "Retrying {} after attempt {}/{} due to {}",
            operation,
            retry_state.attempt_number,
            max_attempts,
            exc,
        )

    async for attempt in AsyncRetrying(
        retry=retry_if_exception(is_retryable_llm_exception),
        wait=wait_strategy,
        stop=stop_after_attempt(max_attempts),
        before_sleep=_before_sleep,
        reraise=True,
    ):
        with attempt:
            return await llm.ainvoke(messages)

    raise RuntimeError(f"Unexpected retry flow exit while running: {operation}")
