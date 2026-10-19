from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Probe:
    name: str
    path: str
    content_type: str
    marker: str | None = None


PLAYGROUND_PROBES = (
    Probe("homepage", "", "text/html", "RootSignal"),
    Probe("browser playground", "playground", "text/html", "RootSignal"),
    Probe("prefixed asset", "favicon.svg", "image/svg+xml"),
)
FULL_STACK_PROBES = PLAYGROUND_PROBES + (
    Probe("backend-for-frontend", "api/system", "application/json"),
)


def normalize_deployment_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("deployment URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("deployment URL must not contain credentials, a query, or a fragment")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("deployment URL must use HTTPS outside local development")
    path = parsed.path.rstrip("/") + "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _fetch(url: str, timeout: float) -> tuple[int, str, bytes, str]:
    request = Request(
        url,
        headers={"Accept": "*/*", "User-Agent": "RootSignal-deployment-smoke/0.2"},
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return (
            response.status,
            response.headers.get_content_type(),
            response.read(),
            response.geturl(),
        )


def run_probes(
    deployment_url: str,
    *,
    full_stack: bool = False,
    timeout: float = 10,
    fetch: Callable[[str, float], tuple[int, str, bytes, str]] = _fetch,
) -> list[dict[str, object]]:
    base_url = normalize_deployment_url(deployment_url)
    expected_origin = urlsplit(base_url).netloc
    probes = FULL_STACK_PROBES if full_stack else PLAYGROUND_PROBES
    results: list[dict[str, object]] = []

    for probe in probes:
        url = urljoin(base_url, probe.path)
        try:
            status, content_type, body, final_url = fetch(url, timeout)
            if status != 200:
                raise RuntimeError(f"unexpected HTTP status {status}")
            if content_type != probe.content_type:
                raise RuntimeError(
                    f"expected {probe.content_type}, received {content_type or 'no content type'}"
                )
            if urlsplit(final_url).netloc != expected_origin:
                raise RuntimeError(f"redirected outside deployment origin to {final_url}")
            text = body.decode("utf-8", errors="replace")
            if probe.marker and probe.marker not in text:
                raise RuntimeError(f"response does not contain {probe.marker!r}")
            if probe.path == "api/system":
                payload = json.loads(text)
                if "execution_modes" not in payload or "retrieval" not in payload:
                    raise RuntimeError("system response is missing capability metadata")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            results.append({"name": probe.name, "url": url, "ok": False, "error": str(exc)})
        else:
            results.append({"name": probe.name, "url": url, "ok": True})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rootsignal-smoke",
        description="Verify a deployed RootSignal public path end to end.",
    )
    parser.add_argument("url", help="Public app URL, including any path prefix")
    parser.add_argument(
        "--full-stack",
        action="store_true",
        help="also require the RootSignal API through the web backend-for-frontend",
    )
    parser.add_argument("--timeout", type=float, default=10, help="seconds per request")
    args = parser.parse_args()

    try:
        results = run_probes(args.url, full_stack=args.full_stack, timeout=args.timeout)
    except ValueError as exc:
        parser.error(str(exc))

    for result in results:
        symbol = "PASS" if result["ok"] else "FAIL"
        detail = "" if result["ok"] else f" — {result['error']}"
        print(f"[{symbol}] {result['name']}: {result['url']}{detail}")

    failures = [result for result in results if not result["ok"]]
    print(f"\n{len(results) - len(failures)}/{len(results)} deployment checks passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
