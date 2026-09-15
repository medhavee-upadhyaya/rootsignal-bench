from __future__ import annotations

import unittest

from incidentlab.secrets import SensitiveContentError, detected_secret_types, reject_secrets


class SecretScreeningTests(unittest.TestCase):
    def test_detects_common_credentials_without_returning_the_value(self) -> None:
        samples = {
            "private key": "-----BEGIN " + "PRIVATE KEY-----\nredacted-test-material",
            "AWS access key": "AKIA" + "IOSFODNN7EXAMPLE",
            "GitHub token": "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890",
            "OpenAI-style key": "sk-" + "abcdefghijklmnopqrstuvwxyz123456",
            "bearer token": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz.1234",
            "credential assignment": "database_password=correct-horse-battery-staple",
        }
        for expected, content in samples.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, detected_secret_types(content))
                with self.assertRaises(SensitiveContentError) as raised:
                    reject_secrets(content)
                self.assertNotIn(content, str(raised.exception))

    def test_allows_operational_language_and_placeholder_values(self) -> None:
        safe = (
            "Rotate the database password using the secret manager. "
            "Set API_KEY=<redacted> and verify token throughput after deployment."
        )
        self.assertEqual(detected_secret_types(safe), [])
        reject_secrets(safe)
