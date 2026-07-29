"""Router de superfícies (`/api/v1/surfaces`) — dados de referência públicos."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import LookupRepo

router = APIRouter(prefix="/surfaces", tags=["surfaces"])


class SurfaceItem(BaseModel):
    id: int
    name: str


@router.get("", response_model=list[SurfaceItem])
async def list_surfaces(lookup_repository: LookupRepo) -> list[SurfaceItem]:
    surfaces = await lookup_repository.list_surfaces()
    return [SurfaceItem(id=s.id, name=s.name) for s in surfaces]
