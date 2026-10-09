import tomllib
from pathlib import Path

import pytest

import warden

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def test_version_matches_pyproject():
    expected = tomllib.loads(PYPROJECT.read_text())["tool"]["poetry"]["version"]

    assert warden.__version__ == expected


@pytest.mark.asyncio
async def test_ping_and_openapi_report_warden_version(client):
    assert warden.__version__

    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": f"Warden {warden.__version__} is operational."
    }

    response = await client.get("/openapi.json")
    assert response.json()["info"]["version"] == warden.__version__
