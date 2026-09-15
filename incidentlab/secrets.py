from __future__ import annotations

import re


class SensitiveContentError(ValueError):
    """Raised before user-supplied content containing likely credentials is persisted."""


PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}\b", re.IGNORECASE)),
    (
        "credential assignment",
        re.compile(
            r"\b(?:(?:db|database|service)[_-])?"
            r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)\b"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9._~+/-]{8,}",
            re.IGNORECASE,
        ),
    ),
)


def detected_secret_types(text: str) -> list[str]:
    return [label for label, pattern in PATTERNS if pattern.search(text)]


def reject_secrets(text: str) -> None:
    detected = detected_secret_types(text)
    if detected:
        labels = ", ".join(detected)
        raise SensitiveContentError(
            f"Content appears to contain credentials ({labels}); redact them before importing"
        )
