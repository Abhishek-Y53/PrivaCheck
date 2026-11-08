"""Celery messaging infrastructure for PrivaCheck."""

from backend.infrastructure.messaging.celery_app import celery_app

__all__ = ["celery_app"]
