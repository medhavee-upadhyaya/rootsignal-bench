from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.2.0"


class ReleaseContractTests(unittest.TestCase):
    def test_versions_are_aligned(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "web/package-lock.json").read_text(encoding="utf-8"))
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        module = (ROOT / "incidentlab/__init__.py").read_text(encoding="utf-8")
        api = (ROOT / "incidentlab/api.py").read_text(encoding="utf-8")

        self.assertEqual(project["project"]["version"], EXPECTED_VERSION)
        self.assertEqual(package["version"], EXPECTED_VERSION)
        self.assertEqual(lock["version"], EXPECTED_VERSION)
        self.assertEqual(lock["packages"][""]["version"], EXPECTED_VERSION)
        self.assertRegex(citation, rf"(?m)^version: {re.escape(EXPECTED_VERSION)}$")
        self.assertIn(f'__version__ = "{EXPECTED_VERSION}"', module)
        self.assertIn(f'version="{EXPECTED_VERSION}"', api)

    def test_release_artifacts_use_the_version(self) -> None:
        kubernetes = (ROOT / "deploy/kubernetes.yaml").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(kubernetes.count(f":{EXPECTED_VERSION}"), 2)
        self.assertIn(f"## {EXPECTED_VERSION} — Unreleased", changelog)
        self.assertIn("release-v0.2", readme)

    def test_release_workflow_builds_both_images_with_attestations(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("rootsignal-bench-web", workflow)
        self.assertIn("platforms: linux/amd64,linux/arm64", workflow)
        self.assertIn("provenance: mode=max", workflow)
        self.assertIn("sbom: true", workflow)


if __name__ == "__main__":
    unittest.main()
