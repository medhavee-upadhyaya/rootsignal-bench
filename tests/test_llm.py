from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from incidentlab.llm import OpenAICompatibleClient


class ModelListResponse(io.BytesIO):
    def __init__(self, models: list[str], status: int = 200) -> None:
        super().__init__(json.dumps({"object": "list", "data": [{"id": item} for item in models]}).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class OpenAICompatibleHealthTests(unittest.TestCase):
    def test_health_uses_standard_model_discovery_and_requires_configured_model(self) -> None:
        client = OpenAICompatibleClient("http://model.local", "qwen3:1.7b")
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            return_value=ModelListResponse(["qwen3:1.7b", "embedding-model"]),
        ) as request:
            self.assertTrue(client.healthy())
        request.assert_called_once_with("http://model.local/v1/models", timeout=2)

    def test_health_rejects_reachable_server_without_configured_model(self) -> None:
        client = OpenAICompatibleClient("http://model.local/", "missing-model")
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            return_value=ModelListResponse(["another-model"]),
        ):
            self.assertFalse(client.healthy())

    def test_health_fails_closed_on_invalid_or_unreachable_responses(self) -> None:
        client = OpenAICompatibleClient("http://model.local", "qwen3:1.7b")
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            return_value=io.BytesIO(b"not-json"),
        ):
            self.assertFalse(client.healthy())
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            side_effect=OSError("offline"),
        ):
            self.assertFalse(client.healthy())


if __name__ == "__main__":
    unittest.main()
