"""Retry helper with exponential backoff for async functions."""
import asyncio
import logging
from typing import Tuple, Type

import httpx

logger = logging.getLogger(__name__)

# Transient errors worth retrying
RETRYABLE = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


async def with_retry(
    coro_fn,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    retryable: Tuple[Type[BaseException], ...] = RETRYABLE,
    label: str = "",
    **kwargs,
):
    """
    Call an async function with exponential backoff on transient failures.

    Usage:
        result = await with_retry(some_async_fn, arg1, arg2, label="LLM chat")
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except retryable as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"[Retry] {label or coro_fn.__name__} attempt {attempt}/{max_attempts} "
                f"failed ({type(exc).__name__}), retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

    logger.error(f"[Retry] {label or coro_fn.__name__} failed after {max_attempts} attempts")
    raise last_exc
