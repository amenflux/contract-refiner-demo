"""
Pet Store — minimal FastAPI target for the contract-refiner demo.

Intentionally under-specified:
- POST /pets response omits `name` and `created_at`.
- GET /pets/{petId} omits `age`.
- PUT /pets/{petId} omits the `X-Request-Id` and `X-Trace-Id` response headers.
- GET /pets alternates ordering on consecutive calls to expose lack of an
  ordering guarantee in the contract.
- Species outside {"cat", "dog", "rabbit", "bird"} are rejected with 400.

Every "missing" behavior above corresponds to one failing pytest that the
Refiner loop targets. The service listens on port 8001 to avoid clashing
with other demo services that already use 8000.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel


ALLOWED_SPECIES = {"cat", "dog", "rabbit", "bird"}

app = FastAPI(title="Pet Store API", version="1.0.0")


class PetCreate(BaseModel):
    name: str
    species: str


class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None


# In-memory store, insertion-ordered.
_pets: dict[int, dict] = {
    1: {"id": 1, "name": "Rex",      "species": "dog"},
    2: {"id": 2, "name": "Whiskers", "species": "cat"},
    3: {"id": 3, "name": "Bugs",     "species": "rabbit"},
    4: {"id": 4, "name": "Tweety",   "species": "bird"},
}
_next_id: int = 5
_list_call_counter: int = 0


@app.get("/pets")
def list_pets(limit: Optional[int] = Query(default=None, ge=1, le=100)) -> list[dict]:
    """List pets. Deterministically alternates ordering across calls so the
    ordering-stability test observes a real inconsistency to file against."""
    global _list_call_counter
    _list_call_counter += 1
    items = list(_pets.values())
    if _list_call_counter % 2 == 0:
        items = list(reversed(items))
    if limit is not None:
        items = items[:limit]
    return items


@app.post("/pets", status_code=201)
def create_pet(pet: PetCreate) -> dict:
    """Create a pet. Response envelope deliberately omits `name` and
    `created_at` — both are contract violations the Refiner targets."""
    global _next_id
    if pet.species not in ALLOWED_SPECIES:
        raise HTTPException(
            status_code=400,
            detail=f"species {pet.species!r} not in allowed set",
        )
    new_id = _next_id
    _next_id += 1
    _pets[new_id] = {"id": new_id, "name": pet.name, "species": pet.species}
    return {"id": new_id}


@app.get("/pets/{petId}")
def get_pet(petId: int = Path(..., ge=1)) -> dict:
    """Fetch a pet by id. Response deliberately omits `age`."""
    pet = _pets.get(petId)
    if pet is None:
        raise HTTPException(status_code=404, detail="pet not found")
    return {"id": pet["id"], "name": pet["name"], "species": pet["species"]}


@app.put("/pets/{petId}")
def update_pet(petId: int, body: PetUpdate) -> dict:
    """Update a pet. Response deliberately omits X-Request-Id + X-Trace-Id
    headers required by the extension for distributed tracing."""
    pet = _pets.get(petId)
    if pet is None:
        raise HTTPException(status_code=404, detail="pet not found")
    if body.species is not None and body.species not in ALLOWED_SPECIES:
        raise HTTPException(status_code=400, detail="invalid species")
    if body.name is not None:
        pet["name"] = body.name
    if body.species is not None:
        pet["species"] = body.species
    _pets[petId] = pet
    return {"id": petId}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
