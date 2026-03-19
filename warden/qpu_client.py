import json
from httpx import AsyncClient


class QPUClient:
    """HTTP Client to interact with the pasqos API."""

    def __init__(self, url):
        self.url = url
        self.client = AsyncClient()

    async def get_specs(self) -> str:
        """Get QPU serialized device specs."""
        response = await self.client.get(f"{self.url}/api/v1/system")
        response.raise_for_status()
        return json.dumps(response.json()["data"]["specs"])
