from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import httpx

from ..auth import token_provider
from ..config import Config

# ---------- logging ----------
LOGGER_NAME = "foundry.agents.client"
logger = logging.getLogger(LOGGER_NAME)

# Example app-level setup:
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)s %(name)s [corr=%(correlation_id)s] %(message)s",
# )


class _LoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("correlation_id", self.extra.get("correlation_id", "-"))
        return msg, kwargs


# ---------- errors ----------
class FoundryError(Exception):
    """High-level client error with helpful context."""
    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        url: Optional[str] = None,
        body_snippet: Optional[str] = None,
        correlation_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status = status
        self.url = url
        self.body_snippet = body_snippet
        self.correlation_id = correlation_id
        self.detail = detail or {}

    def __str__(self):
        base = super().__str__()
        parts = []
        if self.status is not None:
            parts.append(f"status={self.status}")
        if self.url:
            parts.append(f"url={self.url}")
        if self.correlation_id:
            parts.append(f"corr={self.correlation_id}")
        if self.body_snippet:
            parts.append(f"body={self.body_snippet[:180]}...")
        if parts:
            base += " [" + " | ".join(parts) + "]"
        return base


# ---------- utilities ----------
def _safe_json(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    try:
        return json.loads(obj)  # type: ignore[arg-type]
    except Exception:
        return {}

def _is_retryable(status: Optional[int], exc: Optional[Exception]) -> bool:
    if exc is not None:
        # network glitches, timeouts etc.
        return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))
    if status is None:
        return False
    return status in (408, 409, 425, 429, 500, 502, 503, 504)


# --- client pooling + concurrency guard -------------------------------------

_httpx_limits = httpx.Limits(max_keepalive_connections=100, max_connections=200)
_shared_client: Optional[httpx.AsyncClient] = None

async def _get_client(timeout: float = 30.0) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            timeout=timeout,
            limits=_httpx_limits,
            http2=True,
        )
    return _shared_client

# Global semafor for at dæmpe trykket på varme endpoints
MAX_INFLIGHT = 8  # justér efter kvote
_inflight = asyncio.Semaphore(MAX_INFLIGHT)

# Simpel global circuit breaker ved mange 429'ere
_last_429_until: float = 0.0
_lock = asyncio.Lock()

async def _global_backoff_wait():
    # Hvis vi ved at der er en aktiv 429-backoff periode, vent pænt
    async with _lock:
        wait = max(0.0, _last_429_until - time.time())
    if wait > 0:
        await asyncio.sleep(wait)

def _note_429(delay_seconds: float):
    global _last_429_until
    with contextlib.suppress(Exception):
        _last_429_until = max(_last_429_until, time.time() + delay_seconds)


# --- headers/token -----------------------------------------------------------

async def _headers() -> Dict[str, str]:
    tok = await token_provider.get_token()
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# --- backoff helpers ---------------------------------------------------------

def _with_jitter(seconds: float, frac: float = 0.25) -> float:
    d = seconds * frac
    return max(0.0, seconds - d + random.random() * 2 * d)

def _retry_after_seconds_from_headers(resp: httpx.Response, fallback: float) -> float:
    # Standard Retry-After (seconds or HTTP-date)
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return float(ra)
        except ValueError:
            try:
                dt = parsedate_to_datetime(ra)
                # parsed datetime may be naive or tz-aware
                now = datetime.now(timezone.utc)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return max(0.0, (dt - now).total_seconds())
            except Exception:
                pass

    # Common vendor headers
    for h in ("x-ratelimit-reset", "x-ratelimit-reset-seconds", "retry-after-ms"):
        v = resp.headers.get(h)
        if v:
            try:
                sec = float(v) / (1000.0 if h.endswith("-ms") else 1.0)
                return max(0.0, sec)
            except Exception:
                pass

    return fallback


# --- core request with retries ----------------------------------------------

async def _request_json(
    method: str,
    url: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
    max_retries: int = 4,
    base_delay: float = 0.6,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Makes an HTTP request with retries/backoff and returns parsed JSON (dict).
    Raises FoundryError with context on failure.
    """
    log = _LoggerAdapter(logger, {"correlation_id": correlation_id or "-"})
    attempt = 0

    await _global_backoff_wait()

    client = await _get_client(timeout=timeout)
    while True:
        attempt += 1
        try:
            async with _inflight:
                log.debug("HTTP %s %s attempt=%d", method, url, attempt)
                resp = await client.request(method, url, json=json_body, headers=await _headers())

            if 200 <= resp.status_code < 300:
                # success
                try:
                    return resp.json()
                except Exception:
                    text = resp.text
                    log.warning("Non-JSON response; returning parsed dict if possible")
                    return _safe_json(text)

            # Non-2xx
            body_snip = (resp.text or "")[:400]
            retryable = _is_retryable(resp.status_code, None)
            log_fn = log.warning if retryable else log.error
            log_fn(
                "HTTP error status=%d url=%s attempt=%d body_snip=%r",
                resp.status_code, url, attempt, body_snip,
            )

            if attempt <= max_retries and retryable:
                delay = base_delay * (2 ** (attempt - 1))
                if resp.status_code == 429:
                    delay = _retry_after_seconds_from_headers(resp, fallback=delay)
                    _note_429(delay)
                await asyncio.sleep(_with_jitter(min(delay, 120.0)))
                continue

            # Give detailed error
            detail = _safe_json(resp.text)
            raise FoundryError(
                "Request failed",
                status=resp.status_code,
                url=url,
                body_snippet=body_snip,
                correlation_id=correlation_id,
                detail=detail,
            )

        except Exception as exc:
            if isinstance(exc, FoundryError):
                raise  # already enriched
            retryable_exc = _is_retryable(None, exc)
            log_fn = log.warning if retryable_exc else log.error
            log_fn("HTTP exception on %s %s attempt=%d: %s", method, url, attempt, repr(exc))

            if attempt <= max_retries and retryable_exc:
                delay = _with_jitter(min(base_delay * (2 ** (attempt - 1)), 30.0))
                await asyncio.sleep(delay)
                continue

            raise FoundryError(
                "Transport error",
                url=url,
                correlation_id=correlation_id,
                detail={"exception": repr(exc)},
            ) from exc


# ---------- public API ----------
async def create_thread(timeout: float = 30.0) -> str:
    corr = uuid.uuid4().hex[:8]
    log = _LoggerAdapter(logger, {"correlation_id": corr})
    url = f"{Config.agent_project_endpoint}/threads?api-version={Config.agent_api_version}"
    t0 = time.perf_counter()
    data = await _request_json("POST", url, json_body={}, timeout=timeout, correlation_id=corr)
    thread_id = data.get("id")
    if not thread_id:
        raise FoundryError("Missing thread id in response", url=url, correlation_id=corr, detail=data)
    log.info("Thread created id=%s (%.3fs)", thread_id, time.perf_counter() - t0)
    return str(thread_id)

async def post_message(thread_id: str, role: str, content: str) -> Dict[str, Any]:
    corr = uuid.uuid4().hex[:8]
    log = _LoggerAdapter(logger, {"correlation_id": corr})
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/messages?api-version={Config.agent_api_version}"
    payload = {"role": role, "content": content}
    t0 = time.perf_counter()
    data = await _request_json("POST", url, json_body=payload, timeout=30.0, correlation_id=corr)
    log.info("Message posted thread=%s role=%s len=%d (%.3fs)", thread_id, role, len(content), time.perf_counter() - t0)
    return data

async def run_thread(thread_id: str) -> str:
    corr = uuid.uuid4().hex[:8]
    log = _LoggerAdapter(logger, {"correlation_id": corr})
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/runs?api-version={Config.agent_api_version}"
    payload = {"assistant_id": Config.agent_id}
    t0 = time.perf_counter()
    data = await _request_json("POST", url, json_body=payload, timeout=30.0, correlation_id=corr)
    run_id = data.get("id")
    if not run_id:
        raise FoundryError("Missing run id in response", url=url, correlation_id=corr, detail=data)
    log.info("Run started id=%s thread=%s (%.3fs)", run_id, thread_id, time.perf_counter() - t0)
    return str(run_id)

async def poll_run(
    thread_id: str,
    run_id: str,
    *,
    interval: float = 2.0,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    corr = uuid.uuid4().hex[:8]
    log = _LoggerAdapter(logger, {"correlation_id": corr})
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/runs/{run_id}?api-version={Config.agent_api_version}"

    start = time.time()
    attempt = 0
    sleep = max(1.5, interval)  # start en anelse højere for at skåne systemet
    log.info("Polling run id=%s thread=%s (timeout=%.1fs interval≈%.1fs)", run_id, thread_id, timeout, sleep)

    client = await _get_client(timeout=30.0)

    while True:
        attempt += 1
        try:
            async with _inflight:
                resp = await client.get(url, headers=await _headers())

            if resp.status_code == 200:
                data = _safe_json(resp.text) or {}
                status = data.get("status")
                log.debug("Poll attempt=%d status=%s", attempt, status)

                if status in ("completed", "failed", "expired", "cancelled"):
                    elapsed = time.time() - start
                    log.info("Run finished status=%s in %.2fs", status, elapsed)
                    return data

                if time.time() - start > timeout:
                    raise FoundryError(
                        "Run timed out",
                        status=200,
                        url=url,
                        correlation_id=corr,
                        detail=data,
                    )

                await asyncio.sleep(sleep)
                sleep = min(10.0, sleep * 1.6)  # eksponentiel backoff op til 10s
                continue

            # Non-200 during poll
            body_snip = resp.text[:300]
            if _is_retryable(resp.status_code, None):
                # Ved 429/5xx: respekter Retry-After + jitter
                delay = _retry_after_seconds_from_headers(resp, fallback=sleep)
                if resp.status_code == 429:
                    _note_429(delay)
                await asyncio.sleep(_with_jitter(min(delay, 15.0)))
                sleep = min(10.0, max(sleep, delay) * 1.4)
                log.warning("Poll HTTP status=%d attempt=%d; backing off to ≈%.1fs", resp.status_code, attempt, sleep)
                continue

            raise FoundryError(
                "Polling failed",
                status=resp.status_code,
                url=url,
                body_snippet=body_snip,
                correlation_id=corr,
                detail=_safe_json(resp.text),
            )

        except Exception as exc:
            if _is_retryable(None, exc):
                delay = _with_jitter(min(sleep, 15.0))
                log.warning("Poll exception attempt=%d: %s; sleeping ≈%.1fs", attempt, repr(exc), delay)
                await asyncio.sleep(delay)
                sleep = min(10.0, sleep * 1.6)
                continue
            raise FoundryError(
                "Polling transport error",
                url=url,
                correlation_id=corr,
                detail={"exception": repr(exc)},
            ) from exc

async def get_messages(thread_id: str) -> List[Dict[str, Any]]:
    corr = uuid.uuid4().hex[:8]
    log = _LoggerAdapter(logger, {"correlation_id": corr})
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/messages?api-version={Config.agent_api_version}"
    t0 = time.perf_counter()
    data = await _request_json("GET", url, timeout=30.0, correlation_id=corr)
    # API sometimes returns {"data":[...]} or the list directly; normalize:
    items = data.get("data", data if isinstance(data, list) else [])
    if not isinstance(items, list):
        raise FoundryError("Unexpected messages payload", url=url, correlation_id=corr, detail=data)
    log.info("Fetched %d message(s) for thread=%s (%.3fs)", len(items), thread_id, time.perf_counter() - t0)
    return items
