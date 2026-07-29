"""Configuração centralizada da aplicação.

Usa pydantic-settings para validar variáveis de ambiente no arranque
(fail-fast): se faltar uma variável crítica ou tiver o tipo errado,
a aplicação falha imediatamente ao arrancar, em vez de falhar
silenciosamente a meio de um pedido em produção.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação, carregada de variáveis de ambiente / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Aplicação --
    app_name: str = "Simulador de Ténis"
    environment: str = "development"
    debug: bool = False

    # -- Base de dados --
    # Em produção: postgresql+asyncpg://... | Em testes: sqlite+aiosqlite:///:memory:
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    database_echo: bool = False

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Corrige o URL de BD que serviços de alojamento (ex.: Render,
        Heroku) costumam fornecer.

        Esses serviços dão tipicamente `postgres://...` ou
        `postgresql://...` — ambos síncronos por omissão. O nosso
        engine é assíncrono (`asyncpg`), pelo que reescrevemos sempre
        para `postgresql+asyncpg://...`, sem exigir que quem faz o
        deploy se lembre de editar o URL manualmente.
        """
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # -- Modelo preditivo ML --
    ml_model_path: str = "model_artifacts/match_outcome_model.joblib"

    # -- Autenticação (JWT) --
    # Em produção, `jwt_secret_key` DEVE vir de uma variável de ambiente
    # gerida por um secrets manager — o valor por omissão aqui só serve
    # para desenvolvimento/testes locais (falhar-fast num valor óbvio
    # facilita detetar um deployment mal configurado).
    jwt_secret_key: str = "dev-only-insecure-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # -- Filas assíncronas (Celery + Redis) --
    redis_url: str = "redis://localhost:6379/0"
    # `True` só em testes (ver `app/tasks/celery_app.py`) — corre as
    # tarefas de forma síncrona, no mesmo processo, sem broker real.
    celery_task_always_eager: bool = False

    # -- Cache e rate limiting (Redis) --
    # DB Redis separada da usada pelo Celery (db 0) — evita qualquer
    # colisão de chaves com as filas/resultados internos do Celery.
    redis_cache_url: str = "redis://localhost:6379/2"
    rate_limit_authenticated_per_minute: int = 100
    rate_limit_unauthenticated_per_minute: int = 20
    rate_limit_simulations_per_hour: int = 10
    simulation_cache_ttl_seconds: int = 3600

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "testing", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment deve ser um de {allowed}, recebeu '{v}'")
        return v


@lru_cache
def get_settings() -> Settings:
    """Devolve a instância de configuração, em cache (singleton por processo)."""
    return Settings()
