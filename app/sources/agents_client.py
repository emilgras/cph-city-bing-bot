from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
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

async def _headers() -> Dict[str, str]:
    tok = await token_provider.get_token()
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

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
    last_exc: Optional[Exception] = None
    last_status: Optional[int] = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            attempt += 1
            try:
                log.debug("HTTP %s %s attempt=%d", method, url, attempt)
                resp = await client.request(method, url, json=json_body, headers=await _headers())
                last_status = resp.status_code

                if 200 <= resp.status_code < 300:
                    # success
                    try:
                        return resp.json()
                    except Exception:
                        # Non-JSON success (shouldn't happen here, but guard anyway)
                        text = resp.text
                        log.warning("Non-JSON response; returning parsed dict if possible")
                        return _safe_json(text)

                # Non-2xx
                body_snip = (resp.text or "")[:400]
                log_fn = log.warning if _is_retryable(resp.status_code, None) else log.error
                log_fn(
                    "HTTP error status=%d url=%s attempt=%d body_snip=%r",
                    resp.status_code, url, attempt, body_snip,
                )

                if attempt <= max_retries and _is_retryable(resp.status_code, None):
                    await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
                    continue

                # Give detailed error
                detail = _safe_json(resp.text)
                raise FoundryError(
                    f"Request failed",
                    status=resp.status_code,
                    url=url,
                    body_snippet=body_snip,
                    correlation_id=correlation_id,
                    detail=detail,
                )

            except Exception as exc:
                last_exc = exc
                if isinstance(exc, FoundryError):
                    raise  # already enriched

                log_fn = log.warning if _is_retryable(None, exc) else log.error
                log_fn("HTTP exception on %s %s attempt=%d: %s", method, url, attempt, repr(exc))

                if attempt <= max_retries and _is_retryable(None, exc):
                    await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
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
    log.info("Polling run id=%s thread=%s (timeout=%.1fs interval=%.1fs)", run_id, thread_id, timeout, interval)

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            attempt += 1
            try:
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

                    await asyncio.sleep(interval)
                    continue

                # Non-200 during poll
                body_snip = resp.text[:300]
                if _is_retryable(resp.status_code, None):
                    log.warning("Poll HTTP status=%d attempt=%d; retrying", resp.status_code, attempt)
                    await asyncio.sleep(min(8.0, 0.6 * (2 ** (attempt - 1))))
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
                    log.warning("Poll exception attempt=%d: %s", attempt, repr(exc))
                    await asyncio.sleep(min(8.0, 0.6 * (2 ** (attempt - 1))))
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
