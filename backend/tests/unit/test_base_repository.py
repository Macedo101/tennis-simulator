"""Testes do repositório genérico `BaseRepository`."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player
from app.repositories.base import BaseRepository
from app.repositories.exceptions import DuplicateEntityError, EntityNotFoundError


@pytest.fixture
def player_repo(db_session: AsyncSession) -> BaseRepository[Player]:
    return BaseRepository(db_session, Player)


async def test_add_persists_entity_and_generates_id(
    player_repo: BaseRepository[Player], make_player
) -> None:
    player = make_player()
    saved = await player_repo.add(player)

    assert saved.id is not None
    assert isinstance(saved.id, uuid.UUID)


async def test_get_by_id_returns_none_when_missing(
    player_repo: BaseRepository[Player],
) -> None:
    result = await player_repo.get_by_id(uuid.uuid4())
    assert result is None


async def test_get_by_id_returns_entity_when_present(
    player_repo: BaseRepository[Player], make_player
) -> None:
    player = await player_repo.add(make_player())

    fetched = await player_repo.get_by_id(player.id)

    assert fetched is not None
    assert fetched.id == player.id
    assert fetched.first_name == "Novak"


async def test_get_by_id_or_raise_raises_entity_not_found(
    player_repo: BaseRepository[Player],
) -> None:
    missing_id = uuid.uuid4()
    with pytest.raises(EntityNotFoundError) as exc_info:
        await player_repo.get_by_id_or_raise(missing_id)

    assert exc_info.value.entity_name == "Player"
    assert exc_info.value.entity_id == missing_id


async def test_list_respects_limit_and_offset(
    player_repo: BaseRepository[Player], make_player
) -> None:
    for i in range(5):
        await player_repo.add(make_player(first_name=f"Player{i}", last_name="Test"))

    page1 = await player_repo.list(limit=2, offset=0)
    page2 = await player_repo.list(limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    assert {p.id for p in page1}.isdisjoint({p.id for p in page2})


async def test_count_reflects_number_of_rows(
    player_repo: BaseRepository[Player], make_player
) -> None:
    assert await player_repo.count() == 0

    await player_repo.add(make_player())
    await player_repo.add(make_player(first_name="Carlos", last_name="Alcaraz"))

    assert await player_repo.count() == 2


async def test_delete_removes_entity(
    player_repo: BaseRepository[Player], make_player
) -> None:
    player = await player_repo.add(make_player())

    await player_repo.delete(player)

    assert await player_repo.get_by_id(player.id) is None


async def test_exists_true_and_false(
    player_repo: BaseRepository[Player], make_player
) -> None:
    player = await player_repo.add(make_player())

    assert await player_repo.exists(player.id) is True
    assert await player_repo.exists(uuid.uuid4()) is False


async def test_add_duplicate_raises_duplicate_entity_error(
    player_repo: BaseRepository[Player], make_player
) -> None:
    await player_repo.add(make_player())

    with pytest.raises(DuplicateEntityError):
        # Mesma tripla (first_name, last_name, date_of_birth) -> viola
        # a constraint uq_players_identity.
        await player_repo.add(make_player())
