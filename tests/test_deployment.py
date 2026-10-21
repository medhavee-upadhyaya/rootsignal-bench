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
        cls.render = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))

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

    def test_manual_deployment_check_runs_real_smoke_probe_and_keeps_evidence(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/deployment-smoke.yml").read_text(encoding="utf-8")
        )
        triggers = workflow.get("on", workflow.get(True))
        dispatch = triggers["workflow_dispatch"]["inputs"]
        self.assertTrue(dispatch["deployment_url"]["required"])
        self.assertEqual(dispatch["full_stack"]["type"], "boolean")
        steps = workflow["jobs"]["verify"]["steps"]
        script = next(step["run"] for step in steps if step.get("id") == "smoke")
        self.assertIn('"$DEPLOYMENT_URL"', script)
        self.assertIn("incidentlab.deployment_smoke", script)
        artifact = next(step for step in steps if step.get("uses") == "actions/upload-artifact@v4")
        self.assertEqual(artifact["if"], "always()")
        self.assertEqual(artifact["with"]["retention-days"], 30)

    def test_vercel_production_deploy_is_manual_guarded_and_smoke_tested(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/deploy-vercel.yml").read_text(encoding="utf-8")
        )
        triggers = workflow.get("on", workflow.get(True))
        self.assertIn("workflow_dispatch", triggers)
        job = workflow["jobs"]["deploy"]
        self.assertEqual(job["environment"], "production")
        self.assertFalse(workflow["concurrency"]["cancel-in-progress"])
        script = "\n".join(str(step.get("run", "")) for step in job["steps"])
        self.assertIn("vercel build --prod", script)
        self.assertIn("vercel deploy --prebuilt --prod", script)
        self.assertIn("incidentlab.deployment_smoke", script)
        self.assertIn("/project/rootsignalbench", script)
        for secret in ("VERCEL_ORG_ID", "VERCEL_PROJECT_ID", "VERCEL_TOKEN"):
            self.assertIn(secret, job["env"])

    def test_render_blueprint_keeps_api_private_and_state_persistent(self) -> None:
        services = {service["name"]: service for service in self.render["services"]}
        api = services["rootsignal-api"]
        web = services["rootsignal-web"]
        self.assertEqual(api["type"], "pserv")
        self.assertEqual(api["disk"]["mountPath"], "/data")
        self.assertEqual(api["disk"]["sizeGB"], 1)
        self.assertEqual(web["type"], "web")
        self.assertEqual(web["healthCheckPath"], "/project/rootsignalbench/")
        api_env = {entry["key"]: entry for entry in api["envVars"]}
        web_env = {entry["key"]: entry for entry in web["envVars"]}
        self.assertEqual(api_env["PORT"]["value"], "8000")
        self.assertEqual(web_env["PORT"]["value"], "3000")
        self.assertEqual(api["autoDeployTrigger"], "checksPass")
        self.assertEqual(web["autoDeployTrigger"], "checksPass")

    def test_render_blueprint_generates_and_reuses_api_credential(self) -> None:
        services = {service["name"]: service for service in self.render["services"]}
        api_env = {entry["key"]: entry for entry in services["rootsignal-api"]["envVars"]}
        web_env = {entry["key"]: entry for entry in services["rootsignal-web"]["envVars"]}
        self.assertTrue(api_env["ROOTSIGNAL_API_KEYS"]["generateValue"])
        self.assertEqual(
            web_env["ROOTSIGNAL_API_KEY"]["fromService"],
            {"type": "pserv", "name": "rootsignal-api", "envVarKey": "ROOTSIGNAL_API_KEYS"},
        )
        self.assertTrue(api_env["INCIDENTLAB_LLM_URL"]["sync"] is False)
        self.assertTrue(api_env["INCIDENTLAB_MODEL"]["sync"] is False)

    def test_render_web_discovers_api_through_private_service_properties(self) -> None:
        services = {service["name"]: service for service in self.render["services"]}
        web_env = {entry["key"]: entry for entry in services["rootsignal-web"]["envVars"]}
        self.assertEqual(web_env["INCIDENTLAB_API_HOST"]["fromService"]["property"], "host")
        self.assertEqual(web_env["INCIDENTLAB_API_PORT"]["fromService"]["property"], "port")
        self.assertEqual(web_env["ROOTSIGNAL_BASE_PATH"]["value"], "/project/rootsignalbench")


if __name__ == "__main__":
    unittest.main()
