"""Fixtures for the contract-refiner demo test suite.

Two fixtures matter:

- `extension` returns the parsed contract-extension overlay so tests can
  assert what the overlay declares (this is the Refiner's editing surface).
- `base_url` returns the Pet Store base URL, defaulting to the docker-compose
  service on port 8001. Overridable via the PET_STORE_URL env var so the
  same tests run locally against `uvicorn app.main:app --port 8001`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_FILE = REPO_ROOT / "spec" / "openapi_extension.json"


@pytest.fixture(scope="session")
def extension() -> dict:
    """Parsed contract-extension overlay."""
    return json.loads(EXTENSION_FILE.read_text())


@pytest.fixture(scope="session")
def base_url() -> str:
    """Pet Store base URL. Defaults to the docker-compose port."""
    return os.environ.get("PET_STORE_URL", "http://localhost:8001").rstrip("/")
