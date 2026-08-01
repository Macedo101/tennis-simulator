"""Router de jogadores (`/api/v1/players`)."""
from __future__ import annotations

import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, status

from app.api.deps import AdminUser, LookupRepo, MatchRepo, PlayerRepo, PlayerStatsServiceDep
from app.api.pagination import decode_cursor, encode_cursor
from app.api.schemas.common import PaginatedResponse, PaginationMeta
from app.api.schemas.player import (
    PlayerCreateRequest,
    PlayerDetail,
    PlayerListItem,
    PlayerRankingItem,
    RecentFormResponse,
    SurfaceStatsResponse,
)
from app.models.player import Player
from app.repositories.exceptions import EntityNotFoundError

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=PaginatedResponse[PlayerListItem])
async def list_players(
    player_repository: PlayerRepo,
    search: Annotated[str | None, Query(description="Pesquisa fuzzy por nome.")] = None,
    country: Annotated[str | None, Query(description="Código ISO-2 do país.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> PaginatedResponse[PlayerListItem]:
    after_created_at: datetime.datetime | None = None
    after_id: UUID | None = None
    if cursor is not None:
        decoded = decode_cursor(cursor)
        after_created_at, after_id = decoded.created_at, decoded.id

    players = await player_repository.list_paginated(
        limit=limit,
        after_created_at=after_created_at,
        after_id=after_id,
        search=search,
        country_iso=country,
    )

    has_more = len(players) > limit
    page = players[:limit]
    next_cursor = (
        encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    )

    return PaginatedResponse(
        data=[PlayerListItem.model_validate(p) for p in page],
        pagination=PaginationMeta(next_cursor=next_cursor, has_more=has_more, limit=limit),
    )


@router.post("", response_model=PlayerDetail, status_code=status.HTTP_201_CREATED)
async def create_player(
    payload: PlayerCreateRequest,
    player_repository: PlayerRepo,
    _admin: AdminUser,
) -> PlayerDetail:
    """Cria um novo jogador — [admin]. Ver especificação da API REST, secção 5."""
    player = Player(
        first_name=payload.first_name,
        last_name=payload.last_name,
        date_of_birth=payload.date_of_birth,
        country_iso=payload.country_iso,
        height_cm=payload.height_cm,
        plays=payload.plays,
        turned_pro=payload.turned_pro,
    )
    created = await player_repository.add(player)
    return PlayerDetail.model_validate(created)


@router.get("/{player_id}", response_model=PlayerDetail)
async def get_player(
    player_id: Annotated[UUID, Path()], player_repository: PlayerRepo
) -> PlayerDetail:
    player = await player_repository.get_by_id_or_raise(player_id)
    return PlayerDetail.model_validate(player)


@router.get("/{player_id}/rankings", response_model=list[PlayerRankingItem])
async def get_player_rankings(
    player_id: Annotated[UUID, Path()],
    player_repository: PlayerRepo,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[PlayerRankingItem]:
    await player_repository.get_by_id_or_raise(player_id)
    history = await player_repository.get_ranking_history(player_id, limit=limit)
    return [PlayerRankingItem.model_validate(r) for r in history]


@router.get("/{player_id}/matches")
async def get_player_matches(
    player_id: Annotated[UUID, Path()],
    player_repository: PlayerRepo,
    match_repository: MatchRepo,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict]:
    await player_repository.get_by_id_or_raise(player_id)
    matches = await match_repository.list_for_player(player_id, limit=limit)
    return [
        {
            "id": str(m.id),
            "round": m.round,
            "match_date": m.match_date.isoformat(),
            "winner_id": str(m.winner_id) if m.winner_id else None,
            "status": m.status,
        }
        for m in matches
    ]


@router.get("/{player_id}/form", response_model=RecentFormResponse)
async def get_player_recent_form(
    player_id: Annotated[UUID, Path()],
    stats_service: PlayerStatsServiceDep,
    n_matches: Annotated[int, Query(ge=1, le=100)] = 10,
) -> RecentFormResponse:
    """Forma recente do jogador (não presente na especificação original da API,
    mas exposta aqui porque o `PlayerStatsService` já a calcula — evita
    obrigar o frontend a implementar a agregação ele próprio)."""
    result = await stats_service.get_recent_form(player_id, n_matches=n_matches)
    return RecentFormResponse(
        player_id=result.player_id,
        matches_considered=result.matches_considered,
        wins=result.wins,
        losses=result.losses,
        win_rate=result.win_rate,
    )


@router.get("/{player_id}/stats/{surface}", response_model=SurfaceStatsResponse)
async def get_player_surface_stats(
    player_id: Annotated[UUID, Path()],
    surface: Annotated[str, Path(description="Nome da superfície (ex.: 'clay').")],
    stats_service: PlayerStatsServiceDep,
    lookup_repository: LookupRepo,
) -> SurfaceStatsResponse:
    surfaces = await lookup_repository.list_surfaces()
    matching = next((s for s in surfaces if s.name == surface), None)
    if matching is None:
        raise EntityNotFoundError("Surface", surface)

    result = await stats_service.get_surface_stats(player_id, matching.id)
    return SurfaceStatsResponse(
        player_id=result.player_id,
        surface_id=result.surface_id,
        wins=result.wins,
        losses=result.losses,
        matches_played=result.matches_played,
        win_rate=result.win_rate,
        avg_first_serve_pct=result.avg_first_serve_pct,
        avg_first_serve_points_won_pct=result.avg_first_serve_points_won_pct,
    )
