"""Contract tests for the Pet Store demo target.

12 tests total. 4 pass against the initial app + extension, 8 fail. Each
failing test corresponds to a plausible Refiner patch:

    initial failure                             ↔  extension patch
    ─────────────────────────────────────────── ↔  ──────────────────────────────
    test_create_pet_name_in_response            ↔  paths./pets.post.x-required-response-fields += "name"
    test_create_pet_created_at_in_response      ↔  paths./pets.post.x-required-response-fields += "created_at"
    test_get_pet_age_in_response                ↔  paths./pets/{petId}.get.x-required-response-fields += "age"
    test_put_pet_request_id_header              ↔  paths./pets/{petId}.put.x-required-response-headers += "X-Request-Id"
    test_put_pet_trace_id_header                ↔  paths./pets/{petId}.put.x-required-response-headers += "X-Trace-Id"
    test_species_enum_includes_hamster          ↔  components.x-allowed-species += "hamster"
    test_contract_version_declared              ↔  info.contract_version = "..."
    test_list_pets_ordering_stability_declared  ↔  paths./pets.get.x-order-guarantee = "id-asc"

Some tests hit the running app (real HTTP). Others inspect the extension
file — the Refiner can resolve those by editing the overlay alone, which
mirrors how contract refinement works in production: the overlay codifies
what the API is supposed to do so downstream consumers can rely on it.
"""
from __future__ import annotations

import urllib.request
import urllib.error
import urllib.parse
import json


# ─── small HTTP helper (stdlib only so tests don't pull requests) ─────

def _request(method: str, url: str, body: dict | None = None) -> tuple[int, dict, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            headers = {k: v for k, v in resp.headers.items()}
            raw = resp.read().decode() or "{}"
    except urllib.error.HTTPError as e:
        status = e.code
        headers = {k: v for k, v in e.headers.items()} if e.headers else {}
        raw = (e.read() or b"").decode() or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    return status, headers, parsed


# ─── 4 passing tests ──────────────────────────────────────────────────

def test_list_pets_200(base_url):
    status, _, body = _request("GET", f"{base_url}/pets")
    assert status == 200
    assert isinstance(body, list) and len(body) >= 1
    for pet in body:
        assert "id" in pet and "name" in pet and "species" in pet


def test_get_pet_by_id_200(base_url):
    status, _, body = _request("GET", f"{base_url}/pets/1")
    assert status == 200
    assert body.get("id") == 1
    assert "name" in body
    assert "species" in body


def test_get_pet_404(base_url):
    status, _, _ = _request("GET", f"{base_url}/pets/9999")
    assert status == 404


def test_list_pets_pagination(base_url):
    status, _, body = _request("GET", f"{base_url}/pets?limit=2")
    assert status == 200
    assert isinstance(body, list)
    assert len(body) == 2


# ─── 8 initially failing tests ────────────────────────────────────────

def test_create_pet_name_in_response(base_url):
    """POST /pets response must echo the created pet's name."""
    status, _, body = _request(
        "POST", f"{base_url}/pets", {"name": "Nala", "species": "cat"}
    )
    assert status == 201
    assert "name" in body, (
        "POST /pets response is missing 'name' — clients cannot confirm what "
        "the server actually persisted without a follow-up GET."
    )


def test_create_pet_created_at_in_response(base_url):
    """POST /pets response must include a created_at timestamp."""
    status, _, body = _request(
        "POST", f"{base_url}/pets", {"name": "Milo", "species": "dog"}
    )
    assert status == 201
    assert "created_at" in body, (
        "POST /pets response is missing 'created_at' — audit trail and ordering "
        "queries downstream depend on this field."
    )


def test_get_pet_age_in_response(base_url):
    """GET /pets/{petId} response must include age."""
    _, _, body = _request("GET", f"{base_url}/pets/1")
    assert "age" in body, (
        "GET /pets/{petId} is missing 'age' — the extension declares it required."
    )


def test_put_pet_request_id_header(base_url):
    """PUT /pets/{petId} must include X-Request-Id on the response."""
    status, headers, _ = _request(
        "PUT", f"{base_url}/pets/1", {"name": "Rex", "species": "dog"}
    )
    assert status == 200
    header_names_lower = {k.lower() for k in headers}
    assert "x-request-id" in header_names_lower, (
        "PUT /pets/{petId} response is missing X-Request-Id — request-tracing "
        "requires it on every mutation response."
    )


def test_put_pet_trace_id_header(base_url):
    """PUT /pets/{petId} must include X-Trace-Id on the response."""
    status, headers, _ = _request(
        "PUT", f"{base_url}/pets/1", {"name": "Rex", "species": "dog"}
    )
    assert status == 200
    header_names_lower = {k.lower() for k in headers}
    assert "x-trace-id" in header_names_lower, (
        "PUT /pets/{petId} response is missing X-Trace-Id — distributed tracing "
        "convention requires it on all mutation responses."
    )


def test_species_enum_includes_hamster(extension):
    """The allowed-species enum should include hamster (contract gap)."""
    allowed = extension.get("components", {}).get("x-allowed-species", [])
    assert "hamster" in allowed, (
        "components.x-allowed-species does not include 'hamster' — recent "
        "product decision added hamsters to the catalog but the extension was "
        "not updated. Refiner should add it."
    )


def test_contract_version_declared(extension):
    """The extension must declare an info.contract_version so downstream
    consumers can bind to a specific contract revision."""
    info = extension.get("info", {})
    assert "contract_version" in info, (
        "info.contract_version is not declared in the extension — clients "
        "cannot pin to a contract revision. Refiner should add it."
    )


def test_list_pets_ordering_stability_declared(base_url, extension):
    """Consecutive GET /pets calls should return items in the same order,
    AND the extension should codify that guarantee. Currently neither holds."""
    _, _, first = _request("GET", f"{base_url}/pets")
    _, _, second = _request("GET", f"{base_url}/pets")
    stable = [p["id"] for p in first] == [p["id"] for p in second]
    declared = "x-order-guarantee" in (
        extension.get("paths", {}).get("/pets", {}).get("get", {})
    )
    assert stable and declared, (
        f"GET /pets ordering: stable={stable}, declared={declared}. Both must "
        "hold — the extension must codify an ordering guarantee and the API "
        "must honour it."
    )
