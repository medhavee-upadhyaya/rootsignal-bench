# Release process

RootSignal releases keep the Python package, web package, API, citation metadata, container tags, documentation, and changelog on one semantic version. `tests/test_release.py` enforces this contract in CI and again before release images are built.

## Prepare

1. Choose the semantic version and update every location covered by the release contract.
2. Change the matching changelog heading from `Unreleased` to the release date.
3. Add `date-released` to `CITATION.cff`.
4. Run the complete verification suite:

```bash
./scripts/verify.sh
python -m unittest tests.test_release -v
docker compose config --quiet
```

5. Commit and push the release preparation. Wait for CI and security checks to pass.

## Tag

Create an annotated tag only after the release commit is on `main`:

```bash
git tag -a v0.2.0 -m "RootSignal v0.2.0"
git push origin v0.2.0
```

The release workflow rejects a tag that differs from `pyproject.toml`. A valid tag builds API and web images for AMD64 and ARM64, attaches SBOM and provenance metadata, and publishes semantic-version and Git-SHA tags to GHCR.

## Verify

Confirm the release workflow succeeds, inspect both package pages, and create GitHub release notes from the reviewed changelog. For production, deploy image digests from the completed workflow instead of relying on a mutable tag.

Do not tag the current `0.2.0` state until its changelog heading and citation release date are finalized.
