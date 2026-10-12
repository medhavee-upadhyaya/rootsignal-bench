from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ProductionDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(
            (ROOT / "deploy/production.compose.yaml").read_text(encoding="utf-8")
        )

    def test_only_web_is_exposed_and_api_network_is_private(self) -> None:
        services = self.compose["services"]
        self.assertNotIn("ports", services["api"])
        self.assertEqual(services["api"]["expose"], ["8000"])
        self.assertIn("ports", services["web"])
        self.assertTrue(self.compose["networks"]["backend"]["internal"])
        self.assertEqual(services["api"]["networks"], ["backend"])
        self.assertEqual(services["web"]["networks"], ["frontend", "backend"])

    def test_state_security_and_resource_limits_are_explicit(self) -> None:
        services = self.compose["services"]
        self.assertEqual(services["api"]["volumes"], ["rootsignal-data:/data"])
        for service in services.values():
            self.assertTrue(service["read_only"])
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertIn("no-new-privileges:true", service["security_opt"])
            self.assertIn("healthcheck", service)
            self.assertIn("mem_limit", service)
            self.assertIn("cpus", service)
            self.assertIn("pids_limit", service)

    def test_required_secrets_fail_closed_and_path_matches_portfolio(self) -> None:
        api_environment = self.compose["services"]["api"]["environment"]
        web = self.compose["services"]["web"]
        self.assertIn(":?", api_environment["ROOTSIGNAL_API_KEYS"])
        self.assertIn(":?", api_environment["INCIDENTLAB_LLM_URL"])
        self.assertIn(":?", api_environment["INCIDENTLAB_MODEL"])
        self.assertEqual(
            web["build"]["args"]["ROOTSIGNAL_BASE_PATH"],
            "${ROOTSIGNAL_BASE_PATH:-/project/rootsignalbench}",
        )
        self.assertEqual(web["environment"]["INCIDENTLAB_API_URL"], "http://api:8000")

    def test_ci_validates_topology_and_builds_prefixed_image(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("docker compose -f deploy/production.compose.yaml config --quiet", workflow)
        self.assertIn("ROOTSIGNAL_BASE_PATH=/project/rootsignalbench", workflow)


if __name__ == "__main__":
    unittest.main()
