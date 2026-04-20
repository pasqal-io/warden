# Releasing Warden

Warden releases are built from committed sources. Before publishing, make sure the
version, lockfile, and exported requirements files are all in sync.

## Prepare a release

1. Update the version in `pyproject.toml`.
2. Refresh the lockfile and exported requirements:

   ```bash
   poetry lock
   make update-requirements
   ```

3. Open and merge a PR with the version bump, `poetry.lock`, and the updated
   `requirements*.txt` files.

Pull requests now include a warning-only CI check when the committed
`requirements*.txt` files drift from a fresh Poetry export. The release workflow
enforces the same check strictly and will fail if the committed exports are stale.

## Publish a release

There are two supported publish paths:

- Run the `Release` workflow manually with a version like `1.2.3`.
  - Run it from the merged release branch, usually `main`.
  - The workflow normalizes this to the tag `v1.2.3`.
  - If the tag does not exist yet, GitHub creates it while creating the Release.
- Push an existing tag like `v1.2.3`.
  - The workflow creates the GitHub Release if it does not already exist.

In both cases the workflow is idempotent:

- the tag and Release version must match `pyproject.toml`
- the committed `requirements*.txt` files must match a fresh Poetry export
- the workflow generates one CycloneDX SBOM per exported requirements file
- the workflow builds wheel and source distribution artifacts
- the workflow uploads the SBOMs, package artifacts, and SHA-256 checksum files to
  the GitHub Release

## Release assets

Each release uploads:

- `dist/*.whl`
- `dist/*.tar.gz`
- `warden-sbom-base.cdx.json`
- `warden-sbom-pg.cdx.json`
- `warden-sbom-mariadb.cdx.json`
- one `.sha256` file for each uploaded artifact

GitHub-generated release notes are enabled for new Releases.

## Future hardening

The current workflow includes checksum generation and a base `pip install`
smoke test. If stronger provenance is needed later, add artifact attestations or
Sigstore signing on top of the existing release assets.
