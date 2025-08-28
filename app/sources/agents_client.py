from __future__ import annotations
import httpx
from ..auth import token_provider
from ..config import Config

class FoundryError(Exception): pass

async def _headers():
    tok = await token_provider.get_token()
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

async def create_thread(timeout: float = 30.0) -> str:
    url = f"{Config.agent_project_endpoint}/threads?api-version={Config.agent_api_version}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json={}, headers=await _headers())
        r.raise_for_status()
        return r.json()["id"]

async def post_message(thread_id: str, role: str, content: str):
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/messages?api-version={Config.agent_api_version}"
    payload = {"role": role, "content": content}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=payload, headers=await _headers())
        r.raise_for_status()
        return r.json()

async def run_thread(thread_id: str) -> str:
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/runs?api-version={Config.agent_api_version}"
    payload = {"assistant_id": Config.agent_id}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=payload, headers=await _headers())
        r.raise_for_status()
        return r.json()["id"]

async def poll_run(thread_id: str, run_id: str, *, interval=2.0, timeout=120.0) -> dict:
    import asyncio, time
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/runs/{run_id}?api-version={Config.agent_api_version}"
    start = time.time()
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            r = await client.get(url, headers=await _headers())
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            if status in ("completed", "failed"):
                return data
            if time.time() - start > timeout:
                raise FoundryError("Run timed out")
            await asyncio.sleep(interval)

async def get_messages(thread_id: str) -> list[dict]:
    url = f"{Config.agent_project_endpoint}/threads/{thread_id}/messages?api-version={Config.agent_api_version}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=await _headers())
        r.raise_for_status()
        data = r.json()
        return data.get("data", data)
