from typing import Any

import requests

from app.core.config import settings


class HackerNewsClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.HACKERNEWS_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.HACKERNEWS_TIMEOUT_SECONDS

    def _get_json(self, path: str) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def get_story_ids(self, api_path: str) -> list[int]:
        data = self._get_json(api_path)
        if not isinstance(data, list):
            return []
        return [item_id for item_id in data if isinstance(item_id, int)]

    def get_item(self, item_id: int) -> dict[str, Any] | None:
        data = self._get_json(f"item/{item_id}.json")
        if data is None:
            return None
        if not isinstance(data, dict):
            return None
        return data

    def test_source(self, api_path: str) -> dict[str, Any]:
        story_ids = self.get_story_ids(api_path)
        sample_ids = story_ids[:10]
        return {
            "url": f"{self.base_url}/{api_path.lstrip('/')}",
            "sample_count": len(sample_ids),
            "sample_ids": sample_ids,
        }
