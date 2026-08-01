"""Tarefas assíncronas (Celery)."""
from app.tasks.celery_app import celery_app
from app.tasks.simulation_tasks import run_simulation_task

__all__ = ["celery_app", "run_simulation_task"]
