"""Ponto de entrada da aplicação FastAPI.

Metadados, tags e versionamento por path (`/api/v1`) conforme a
especificação da API REST, secção 1 e 10.
"""
from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.errors import register_exception_handlers
from app.api.routers import auth, matches, players, predictions, simulations
from app.cache.middleware import RateLimitMiddleware
from app.cache.rate_limiter import RateLimiter
from app.cache.redis_client import get_redis_client
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.request_logging import RequestLoggingMiddleware

configure_logging(json_logs=get_settings().environment != "development")

app = FastAPI(
    title="Simulador Profissional de Previsão de Jogos de Ténis",
    description=(
        "API de simulação Monte Carlo e previsão ML para resultados de "
        "ténis profissional."
    ),
    version="1.0.0",
    contact={"name": "João Macedo"},
    openapi_tags=[
        {"name": "auth", "description": "Registo, login e gestão de sessão"},
        {"name": "players", "description": "Consulta de jogadores e estatísticas"},
        {"name": "matches", "description": "Jogos, torneios e head-to-head"},
        {"name": "predictions", "description": "Previsões geradas por modelo ML"},
        {"name": "simulations", "description": "Simulações Monte Carlo"},
    ],
)

register_exception_handlers(app)

# Ordem importa: o middleware adicionado por último é o mais externo
# (corre primeiro no pedido, por último na resposta). Queremos o
# `request_id` já ligado ao contexto de logging antes de qualquer
# verificação de rate limit, para que mesmo um `429` apareça associado
# ao `request_id` correto nos logs.
app.add_middleware(RateLimitMiddleware, rate_limiter=RateLimiter(get_redis_client()))
app.add_middleware(RequestLoggingMiddleware)

# Métricas HTTP genéricas (latência/contagem/em-curso por rota+método+
# status), expostas em `/metrics` — consumível diretamente por
# Prometheus/Grafana Cloud, conforme a stack tecnológica.
Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["observability"])

API_V1_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(players.router, prefix=API_V1_PREFIX)
app.include_router(matches.router, prefix=API_V1_PREFIX)
app.include_router(predictions.router, prefix=API_V1_PREFIX)
app.include_router(simulations.router, prefix=API_V1_PREFIX)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Endpoint de health check — usado por orquestradores/load balancers."""
    return {"status": "ok"}
