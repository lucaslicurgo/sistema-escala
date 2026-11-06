"""Ponto rápido: relógio e regras de turno (sempre no fuso de São Paulo)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    return datetime.now(FUSO)
