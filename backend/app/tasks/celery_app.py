"""Instância Celery da aplicação.

Broker e result backend: Redis (mesma instância já usada para cache no
Módulo 9) — evita introduzir uma terceira peça de infraestrutura
(ex.: RabbitMQ) só para a fila de tarefas, quando Redis já é suficiente
e mais simples de operar à escala de portfólio.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "tennis_simulator",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Ver docstring do módulo de settings: `True` só em testes, para
    # correr tarefas de forma síncrona sem um broker Redis real.
    task_always_eager=_settings.celery_task_always_eager,
    # Sempre `False`, independentemente do modo eager: uma falha dentro
    # da tarefa nunca deve propagar para o pedido HTTP que a despachou
    # (`.delay()`) — nem em produção real (onde corre num worker
    # separado) nem em modo eager de teste. A tarefa já trata as suas
    # próprias falhas marcando a simulação como `failed` (ver
    # `app/tasks/simulation_tasks.py`); voltar a levantar a exceção
    # serve para o registo interno do Celery, não para o chamador.
    task_eager_propagates=False,
)
