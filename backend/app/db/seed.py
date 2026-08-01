"""Seed idempotente de dados de referência (`countries`, `surfaces`).

Corre no arranque da aplicação (ver `app/main.py`) — sem isto, um
deployment novo com uma base de dados vazia não teria superfícies
válidas para associar a jogadores/simulações, e não há (ainda)
nenhuma ferramenta de seed manual disponível num ambiente de produção.

Idempotente: verifica o que já existe antes de inserir, para poder
correr em todos os arranques sem duplicar nem apagar dados.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select

from app.db.base import AsyncSessionFactory
from app.models.lookup import Country, Surface

logger = structlog.get_logger(__name__)

_SURFACES: list[tuple[int, str]] = [(1, "hard"), (2, "clay"), (3, "grass")]

_COUNTRIES: list[tuple[str, str]] = [
    ("RS", "Serbia"),
    ("ES", "Spain"),
    ("PT", "Portugal"),
    ("US", "United States"),
    ("FR", "France"),
    ("GB", "United Kingdom"),
    ("IT", "Italy"),
    ("DE", "Germany"),
    ("AR", "Argentina"),
    ("AU", "Australia"),
    ("RU", "Russia"),
    ("GR", "Greece"),
    ("SR", "Switzerland"),
    ("BR", "Brazil"),
    ("CA", "Canada"),
    ("JP", "Japan"),
]


async def seed_reference_data() -> None:
    """Insere `countries`/`surfaces` em falta. Seguro para correr repetidamente.

    Nunca deixa uma exceção propagar — isto corre no arranque da app
    (`app/main.py`), e uma falha aqui (BD ainda sem migrações aplicadas,
    indisponível num arranque de teste, etc.) não deve impedir a app de
    arrancar. Falha "em aberto": regista um aviso e segue em frente.
    """
    try:
        async with AsyncSessionFactory() as session:
            existing_surface_ids = set(
                (await session.execute(select(Surface.id))).scalars().all()
            )
            for surface_id, name in _SURFACES:
                if surface_id not in existing_surface_ids:
                    session.add(Surface(id=surface_id, name=name))

            existing_country_codes = set(
                (await session.execute(select(Country.iso_code))).scalars().all()
            )
            for iso_code, name in _COUNTRIES:
                if iso_code not in existing_country_codes:
                    session.add(Country(iso_code=iso_code, name=name))

            await session.commit()
    except Exception:  # noqa: BLE001 - ver docstring: nunca deve derrubar o arranque
        logger.warning("seed_reference_data_failed", exc_info=True)
