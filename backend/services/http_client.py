"""Shared, rate-limited, circuit-broken HTTP client for upstream market data.

Why this exists
---------------
The dashboard polls several free quote providers (Sina hq.sinajs.cn,
Tencent qt.gtimg.cn, Sina Market_Center vip.stock.finance.sina.com.cn,
EastMoney push2*) on 30–60s timers, fanning out across many concurrent
requests. Creating a fresh ``httpx.AsyncClient`` per call (no pooling) plus
synchronized polling produces bursty traffic to the same host, which gets the
server IP throttled or banned.

This module centralizes outbound GETs with:

* a single pooled ``AsyncClient`` (keep-alive, connection reuse);
* a per-host concurrency cap + minimum spacing between requests (token bucket);
* a per-host circuit breaker: after N consecutive failures the host is "opened"
  for a cooldown window so callers fail fast and serve cached/stale data instead
  of hammering a host that is already rejecting us;
* bounded retries with backoff for transient errors.

All knobs are env-overridable so behavior can be tuned without code changes.
"""
import os
import time
import asyncio
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def _envf(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except (ValueError, TypeError):
        return default


def _envi(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except (ValueError, TypeError):
        return default


# ── Tunables ──
MAX_CONCURRENCY_PER_HOST = _envi("HTTP_MAX_CONCURRENCY_PER_HOST", 3)
MIN_INTERVAL_PER_HOST = _envf("HTTP_MIN_INTERVAL_PER_HOST", 0.15)   # seconds
CB_FAIL_THRESHOLD = _envi("HTTP_CB_FAIL_THRESHOLD", 4)              # consecutive fails → open
CB_COOLDOWN = _envf("HTTP_CB_COOLDOWN", 30.0)                        # seconds circuit stays open
RETRY_ATTEMPTS = _envi("HTTP_RETRY_ATTEMPTS", 2)                     # extra retries after first try
DEFAULT_TIMEOUT = _envf("HTTP_DEFAULT_TIMEOUT", 10.0)


class CircuitOpenError(Exception):
    """Raised when a host's circuit breaker is open (failing fast)."""


# ── Shared clients (lazy singletons) ──
# `_client` honors the system proxy (HTTP(S)_PROXY); `_direct_client` bypasses it
# (trust_env=False) for callers/deployments that must reach a host directly.
_client: Optional[httpx.AsyncClient] = None
_direct_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

# ── Per-host state ──
_sems: Dict[str, asyncio.Semaphore] = {}
_host_locks: Dict[str, asyncio.Lock] = {}
_last_req: Dict[str, float] = {}
_cb_fails: Dict[str, int] = {}
_cb_open_until: Dict[str, float] = {}


async def get_client(direct: bool = False) -> httpx.AsyncClient:
    """Return a shared pooled client, creating it on first use.

    direct=False → honor the system proxy (required in proxy-only environments).
    direct=True  → bypass the proxy (trust_env=False) for direct connections.
    """
    global _client, _direct_client
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    if direct:
        if _direct_client is None:
            async with _client_lock:
                if _direct_client is None:
                    _direct_client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, limits=limits, trust_env=False)
        return _direct_client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, limits=limits, trust_env=True)
    return _client


def _host_of(url: str) -> str:
    return urlparse(url).netloc or url


def _sem(host: str) -> asyncio.Semaphore:
    sem = _sems.get(host)
    if sem is None:
        sem = asyncio.Semaphore(MAX_CONCURRENCY_PER_HOST)
        _sems[host] = sem
    return sem


def _hlock(host: str) -> asyncio.Lock:
    lk = _host_locks.get(host)
    if lk is None:
        lk = asyncio.Lock()
        _host_locks[host] = lk
    return lk


def circuit_open(host: str) -> bool:
    until = _cb_open_until.get(host, 0.0)
    return bool(until) and time.monotonic() < until


def _record_success(host: str) -> None:
    if _cb_fails.get(host):
        _cb_fails[host] = 0
    _cb_open_until.pop(host, None)


def _record_failure(host: str) -> None:
    n = _cb_fails.get(host, 0) + 1
    _cb_fails[host] = n
    if n >= CB_FAIL_THRESHOLD:
        _cb_open_until[host] = time.monotonic() + CB_COOLDOWN
        logger.warning("circuit OPEN for %s after %d consecutive failures; cooling down %.0fs",
                       host, n, CB_COOLDOWN)


async def _throttle(host: str) -> None:
    """Enforce a minimum interval between requests to the same host."""
    async with _hlock(host):
        now = time.monotonic()
        wait = MIN_INTERVAL_PER_HOST - (now - _last_req.get(host, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        _last_req[host] = time.monotonic()


async def get(url: str, *, params=None, headers=None, timeout: Optional[float] = None,
              retries: Optional[int] = None, direct: bool = False) -> httpx.Response:
    """Rate-limited, circuit-broken GET with retry/backoff.

    Raises ``CircuitOpenError`` immediately if the host circuit is open, or the
    last underlying exception if all retries fail. Callers should treat any
    exception as "no fresh data" and fall back to cache/stale. ``direct=True``
    bypasses the system proxy.
    """
    host = _host_of(url)
    if circuit_open(host):
        raise CircuitOpenError(f"{host} circuit open")

    client = await get_client(direct=direct)
    attempts = RETRY_ATTEMPTS if retries is None else retries
    last_exc: Optional[Exception] = None

    for attempt in range(attempts + 1):
        try:
            async with _sem(host):
                await _throttle(host)
                resp = await client.get(url, params=params, headers=headers,
                                        timeout=timeout or DEFAULT_TIMEOUT)
            resp.raise_for_status()
            _record_success(host)
            return resp
        except Exception as e:  # noqa: BLE001 — transient network/HTTP errors
            last_exc = e
            if attempt >= attempts:
                _record_failure(host)
                raise
            await asyncio.sleep(0.4 * (attempt + 1))

    # Unreachable, but keeps type-checkers happy.
    raise last_exc  # type: ignore[misc]


# ── Test / lifecycle helpers ──

def _set_test_client(client: Optional[httpx.AsyncClient]) -> None:
    """Inject a client (e.g. backed by httpx.MockTransport) for tests.
    Used for both proxy and direct so tests pass regardless of the direct flag."""
    global _client, _direct_client
    _client = client
    _direct_client = client


def _reset_state() -> None:
    """Clear per-host throttle/circuit state (tests)."""
    _sems.clear()
    _host_locks.clear()
    _last_req.clear()
    _cb_fails.clear()
    _cb_open_until.clear()


async def aclose() -> None:
    global _client, _direct_client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _direct_client is not None:
        await _direct_client.aclose()
        _direct_client = None
