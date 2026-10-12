from __future__ import annotations

import io
import json
import unittest
import urllib.error
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


class GenerationResponse(io.BytesIO):
    def __init__(self) -> None:
        super().__init__(json.dumps({
            "model": "hosted-model",
            "choices": [{"message": {"content": '{"result":"ok"}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4},
        }).encode())
        self.status = 200

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
            readiness = client.probe()
            self.assertTrue(readiness.healthy)
            self.assertEqual(readiness.status, "ready")
        model_request = request.call_args.args[0]
        self.assertEqual(model_request.full_url, "http://model.local/v1/models")
        self.assertIsNone(model_request.get_header("Authorization"))
        self.assertEqual(request.call_args.kwargs, {"timeout": 2})

    def test_bearer_auth_is_applied_to_discovery_and_generation(self) -> None:
        credential = "provider_" + "secret-value-for-tests"
        client = OpenAICompatibleClient(
            "https://model.example.test", "hosted-model", api_key=credential
        )
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            side_effect=[ModelListResponse(["hosted-model"]), GenerationResponse()],
        ) as urlopen:
            self.assertTrue(client.probe().healthy)
            generation = client.generate_json("Return JSON", "Test request", max_tokens=64)

        self.assertEqual(generation.content, '{"result":"ok"}')
        self.assertEqual(len(urlopen.call_args_list), 2)
        discovery = urlopen.call_args_list[0].args[0]
        completion = urlopen.call_args_list[1].args[0]
        self.assertEqual(discovery.get_header("Authorization"), f"Bearer {credential}")
        self.assertEqual(completion.get_header("Authorization"), f"Bearer {credential}")
        self.assertEqual(completion.get_header("Content-type"), "application/json")
        self.assertNotIn(credential, repr(client))

    def test_health_rejects_reachable_server_without_configured_model(self) -> None:
        client = OpenAICompatibleClient("http://model.local/", "missing-model")
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            return_value=ModelListResponse(["another-model"]),
        ):
            readiness = client.probe()
            self.assertFalse(readiness.healthy)
            self.assertEqual(readiness.status, "model_not_loaded")
            self.assertIn("missing-model", readiness.message)

    def test_health_fails_closed_on_invalid_or_unreachable_responses(self) -> None:
        client = OpenAICompatibleClient("http://model.local", "qwen3:1.7b")
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            return_value=io.BytesIO(b"not-json"),
        ):
            self.assertEqual(client.probe().status, "incompatible_server")
        with patch(
            "incidentlab.llm.urllib.request.urlopen",
            side_effect=OSError("offline"),
        ):
            self.assertEqual(client.probe().status, "server_unreachable")

    def test_health_reports_rejected_provider_credentials_without_exposing_them(self) -> None:
        credential = "provider_" + "rejected-secret-for-tests"
        client = OpenAICompatibleClient(
            "https://model.example.test", "hosted-model", api_key=credential
        )
        rejected = urllib.error.HTTPError(
            "https://model.example.test/v1/models", 401, "Unauthorized", {}, None
        )
        with patch("incidentlab.llm.urllib.request.urlopen", side_effect=rejected):
            readiness = client.probe()
        rejected.close()
        self.assertEqual(readiness.status, "authentication_failed")
        self.assertNotIn(credential, readiness.message)


if __name__ == "__main__":
    unittest.main()
