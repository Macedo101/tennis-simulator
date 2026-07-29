"""Repositório genérico com operações CRUD comuns.

Todos os repositórios concretos herdam de `BaseRepository[ModelType]`,
que implementa uma única vez (e totalmente tipada, via `Generic`) as
operações que são idênticas para qualquer entidade: obter por ID,
listar com paginação simples, adicionar, apagar, verificar existência.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.repositories.exceptions import DuplicateEntityError, EntityNotFoundError

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Repositório genérico sobre um único modelo ORM.

    Parameters
    ----------
    session:
        Sessão assíncrona SQLAlchemy, injetada pelo chamador (nunca
        criada aqui) — ver justificação arquitetural na secção 1.
    model:
        A classe do modelo ORM (ex.: `Player`) sobre a qual este
        repositório concreto opera.
    """

    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, entity_id: UUID | int) -> ModelType | None:
        """Devolve a entidade pelo ID, ou `None` se não existir.

        Usa `Session.get()` em vez de `select().where()` — beneficia
        automaticamente do *identity map* da sessão (evita um round-trip
        à BD se a entidade já foi carregada nesta mesma sessão/transação).
        """
        return await self._session.get(self._model, entity_id)

    async def get_by_id_or_raise(self, entity_id: UUID | int) -> ModelType:
        """Como `get_by_id`, mas levanta `EntityNotFoundError` se ausente.

        Preferível em handlers de API onde a ausência da entidade deve
        resultar sempre num erro explícito (404), nunca num `None`
        silencioso propagado adiante.
        """
        entity = await self.get_by_id(entity_id)
        if entity is None:
            raise EntityNotFoundError(self._model.__name__, entity_id)
        return entity

    async def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        order_by: Any | None = None,
    ) -> list[ModelType]:
        """Lista entidades com paginação simples (offset-based).

        Nota: a API pública usa paginação cursor-based (ver especificação
        da API REST) — este método offset-based é um utilitário de baixo
        nível para uso interno/testes, não o mecanismo exposto aos
        clientes da API.
        """
        stmt = select(self._model)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Conta o número total de entidades na tabela."""
        stmt = select(func.count()).select_from(self._model)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def add(self, entity: ModelType) -> ModelType:
        """Adiciona uma nova entidade e faz flush (obtém o ID gerado).

        Faz apenas `flush`, não `commit` — a fronteira transacional
        (quando confirmar a transação) é responsabilidade da camada de
        serviço/unit-of-work, não do repositório. Isto permite compor
        várias operações de repositório numa única transação atómica.
        """
        self._session.add(entity)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateEntityError(
                self._model.__name__, str(exc.orig)
            ) from exc
        return entity

    async def delete(self, entity: ModelType) -> None:
        """Remove a entidade e faz flush."""
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, entity_id: UUID | int) -> bool:
        """Verifica se uma entidade com o ID dado existe, sem a carregar."""
        stmt = select(func.count()).select_from(self._model).where(
            self._model.id == entity_id  # type: ignore[attr-defined]
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0
