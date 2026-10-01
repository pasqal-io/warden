import importlib.metadata
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


@pytest.mark.asyncio
async def test_ping_reports_version_when_package_not_installed(client, monkeypatch):
    # `make install` only installs requirements.txt, so the `warden` distribution
    # metadata is missing when running from a source checkout (e.g. systemd).
    def not_installed(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", not_installed)
    expected = tomllib.loads(PYPROJECT.read_text())["tool"]["poetry"]["version"]

    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": f"Warden {expected} is operational."}
