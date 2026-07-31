"""Router de jogos (`/api/v1/matches`)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query

from app.api.deps import LookupRepo, MatchRepo, PlayerRepo, TournamentRepo
from app.api.schemas.match import (
    HeadToHeadMatchSummary,
    HeadToHeadResponse,
    MatchDetailResponse,
    MatchSetSchema,
    MatchStatisticsSchema,
    PlayerRef,
    TournamentEditionRef,
)
from app.repositories.exceptions import EntityNotFoundError

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/head-to-head", response_model=HeadToHeadResponse)
async def get_head_to_head(
    match_repository: MatchRepo,
    player_repository: PlayerRepo,
    player1_id: Annotated[UUID, Query()],
    player2_id: Annotated[UUID, Query()],
) -> HeadToHeadResponse:
    for pid in (player1_id, player2_id):
        await player_repository.get_by_id_or_raise(pid)

    matches = await match_repository.get_head_to_head(player1_id, player2_id)
    player1_wins = sum(1 for m in matches if m.winner_id == player1_id)
    player2_wins = sum(1 for m in matches if m.winner_id == player2_id)

    return HeadToHeadResponse(
        player1_id=player1_id,
        player2_id=player2_id,
        player1_wins=player1_wins,
        player2_wins=player2_wins,
        total_matches=len(matches),
        last_meeting_date=matches[0].match_date if matches else None,
        matches=[
            HeadToHeadMatchSummary(
                match_id=m.id, match_date=m.match_date, winner_id=m.winner_id, round=m.round
            )
            for m in matches
        ],
    )


@router.get("/{match_id}", response_model=MatchDetailResponse)
async def get_match(
    match_id: Annotated[UUID, Path()],
    match_repository: MatchRepo,
    player_repository: PlayerRepo,
    tournament_repository: TournamentRepo,
    lookup_repository: LookupRepo,
) -> MatchDetailResponse:
    match = await match_repository.get_with_details(match_id)
    if match is None:
        raise EntityNotFoundError("Match", match_id)

    player1 = await player_repository.get_by_id_or_raise(match.player1_id)
    player2 = await player_repository.get_by_id_or_raise(match.player2_id)

    edition = await tournament_repository.get_edition_by_id(match.tournament_edition_id)
    if edition is None:
        raise EntityNotFoundError("TournamentEdition", match.tournament_edition_id)
    tournament = await tournament_repository.get_by_id_or_raise(edition.tournament_id)
    surface = await lookup_repository.get_surface(edition.surface_id)
    surface_name = surface.name if surface is not None else "unknown"

    statistics = {
        str(stat.player_id): MatchStatisticsSchema(
            aces=stat.aces,
            double_faults=stat.double_faults,
            first_serve_pct=stat.first_serve_pct,
        )
        for stat in match.statistics
    }

    return MatchDetailResponse(
        id=match.id,
        tournament_edition=TournamentEditionRef(
            tournament_name=tournament.name, year=edition.year, surface=surface_name
        ),
        round=match.round,
        player1=PlayerRef(id=player1.id, name=f"{player1.first_name} {player1.last_name}"),
        player2=PlayerRef(id=player2.id, name=f"{player2.first_name} {player2.last_name}"),
        winner_id=match.winner_id,
        best_of=match.best_of,
        status=match.status,
        sets=[
            MatchSetSchema(
                set_number=s.set_number,
                player1_games=s.player1_games,
                player2_games=s.player2_games,
            )
            for s in match.sets
        ],
        statistics=statistics,
    )
