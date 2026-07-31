"""Exceções de domínio da camada de repositórios.

Traduzem erros específicos de SQLAlchemy/Postgres (IntegrityError,
NoResultFound, etc.) em exceções próprias do domínio, para que a
camada de serviço nunca precise de importar `sqlalchemy.exc` —
mantém as camadas superiores desacopladas do ORM concreto.
"""
from __future__ import annotations


class RepositoryError(Exception):
    """Classe base para todos os erros da camada de repositórios."""


class EntityNotFoundError(RepositoryError):
    """Levantada quando uma entidade pedida por ID não existe."""

    def __init__(self, entity_name: str, entity_id: object) -> None:
        self.entity_name = entity_name
        self.entity_id = entity_id
        super().__init__(f"{entity_name} com id={entity_id!r} não encontrado(a)")


class DuplicateEntityError(RepositoryError):
    """Levantada quando uma operação viola uma constraint de unicidade."""

    def __init__(self, entity_name: str, detail: str) -> None:
        self.entity_name = entity_name
        self.detail = detail
        super().__init__(f"{entity_name} duplicado(a): {detail}")
