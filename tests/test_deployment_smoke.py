from __future__ import annotations

import unittest

from incidentlab.deployment_smoke import normalize_deployment_url, run_probes


class DeploymentSmokeTests(unittest.TestCase):
    def test_normalizes_a_prefixed_public_url(self) -> None:
        self.assertEqual(
            normalize_deployment_url("https://example.com/project/rootsignalbench"),
            "https://example.com/project/rootsignalbench/",
        )

    def test_rejects_unsafe_or_ambiguous_urls(self) -> None:
        invalid = (
            "not-a-url",
            "http://example.com/project/rootsignalbench",
            "https://user:secret@example.com/project/rootsignalbench",
            "https://example.com/project/rootsignalbench?debug=1",
            "https://example.com/project/rootsignalbench#demo",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_deployment_url(value)

    def test_playground_mode_checks_public_flow_without_backend(self) -> None:
        requested: list[str] = []

        def fetch(url: str, _: float) -> tuple[int, str, bytes, str]:
            requested.append(url)
            if url.endswith("favicon.svg"):
                return 200, "image/svg+xml", b"<svg/>", url
            return 200, "text/html", b"<title>RootSignal</title>", url

        results = run_probes("https://example.com/project/rootsignalbench", fetch=fetch)

        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(len(results), 3)
        self.assertNotIn("https://example.com/project/rootsignalbench/api/system", requested)

    def test_full_stack_mode_validates_system_capabilities(self) -> None:
        def fetch(url: str, _: float) -> tuple[int, str, bytes, str]:
            if url.endswith("api/system"):
                return 200, "application/json", b'{"execution_modes": {}, "retrieval": {}}', url
            if url.endswith("favicon.svg"):
                return 200, "image/svg+xml", b"<svg/>", url
            return 200, "text/html", b"RootSignal", url

        results = run_probes("https://example.com/root", full_stack=True, fetch=fetch)

        self.assertEqual(len(results), 4)
        self.assertTrue(all(result["ok"] for result in results))

    def test_reports_content_and_cross_origin_redirect_failures(self) -> None:
        def fetch(url: str, _: float) -> tuple[int, str, bytes, str]:
            if url.endswith("playground"):
                return 200, "text/html", b"wrong product", url
            if url.endswith("favicon.svg"):
                return (
                    200,
                    "image/svg+xml",
                    b"<svg/>",
                    "https://other.example/favicon.svg",
                )
            return 200, "text/html", b"RootSignal", url

        results = run_probes("https://example.com/root", fetch=fetch)

        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertIn("does not contain", str(results[1]["error"]))
        self.assertFalse(results[2]["ok"])
        self.assertIn("outside deployment origin", str(results[2]["error"]))


if __name__ == "__main__":
    unittest.main()
