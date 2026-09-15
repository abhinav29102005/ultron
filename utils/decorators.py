"""
utils/decorators.py – Generic Decorators
=============================================
Provides generic helper decorators: singleton, retry, and timed.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, TypeVar

# Type variables for decorators
F = TypeVar("F", bound=Callable[..., Any])


def singleton(cls: type[Any]) -> type[Any]:
    """
    Class decorator to enforce the singleton pattern on a class.
    """
    instances: dict[type[Any], Any] = {}

    @functools.wraps(cls)
    def get_instance(*args: Any, **kwargs: Any) -> Any:
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance  # type: ignore[return-value]


def retry(attempts: int = 3, delay: float = 0.1, exceptions: tuple[type[Exception], ...] = (Exception,)) -> Callable[[F], F]:
    """
    Decorator to retry a function (sync or async) a specified number of times on failure.
    """
    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc = None
                for attempt in range(1, attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt < attempts:
                            await asyncio.sleep(delay)
                raise last_exc  # type: ignore[misc]
            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc = None
                for attempt in range(1, attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt < attempts:
                            time.sleep(delay)
                raise last_exc  # type: ignore[misc]
            return sync_wrapper  # type: ignore[return-value]
    return decorator


def timed(func: F) -> F:
    """
    Decorator to measure and print execution time of a function (sync or async).
    """
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start_time
                print(f"[DEBUG] Async function '{func.__name__}' took {elapsed:.6f}s")
        return async_wrapper  # type: ignore[return-value]
    else:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start_time
                print(f"[DEBUG] Function '{func.__name__}' took {elapsed:.6f}s")
        return sync_wrapper  # type: ignore[return-value]
    return decorator
