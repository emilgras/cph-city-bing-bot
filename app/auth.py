from __future__ import annotations
import os, time, httpx
from .config import Config

class AzureTokenProvider:
    def __init__(self, tenant: str, client_id: str, client_secret: str, scope: str = "hhttps://ai.azure.com/.default"):
        self.tenant = tenant
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._token = None
        self._expires_at = 0.0

    async def get_token(self) -> str:
        now = time.time()
        # Refresh if expires within 60s
        if self._token and now < (self._expires_at - 60):
            return self._token
        url = f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, data=data)
            r.raise_for_status()
            payload = r.json()
        self._token = payload["access_token"]
        self._expires_at = now + int(payload.get("expires_in", 3600))
        return self._token

# Global instance wired to Config
token_provider = AzureTokenProvider(
    tenant=Config.azure_tenant_id,
    client_id=Config.azure_client_id,
    client_secret=Config.azure_client_secret,
)
