from __future__ import annotations
import httpx

class FoundryError(Exception): pass

async def create_thread(base: str, ver: str, token: str, timeout: float = 30.0) -> str:
    url = f"{base}/threads?api-version={ver}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json={}, headers=headers)
        r.raise_for_status()
        return r.json()["id"]

async def post_message(base: str, ver: str, token: str, thread_id: str, role: str, content: str):
    url = f"{base}/threads/{thread_id}/messages?api-version={ver}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"role": role, "content": content}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

async def run_thread(base: str, ver: str, token: str, thread_id: str, assistant_id: str) -> str:
    url = f"{base}/threads/{thread_id}/runs?api-version={ver}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"assistant_id": assistant_id}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["id"]

async def poll_run(base: str, ver: str, token: str, thread_id: str, run_id: str, *, interval=2.0, timeout=120.0) -> dict:
    import asyncio, time
    url = f"{base}/threads/{thread_id}/runs/{run_id}?api-version={ver}"
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            if status in ("completed", "failed"):
                return data
            if time.time() - start > timeout:
                raise FoundryError("Run timed out")
            await asyncio.sleep(interval)

async def get_messages(base: str, ver: str, token: str, thread_id: str) -> list[dict]:
    url = f"{base}/threads/{thread_id}/messages?api-version={ver}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        # API commonly returns {"data":[{role,content:[{text:...}]},...]}
        return data.get("data", data)
