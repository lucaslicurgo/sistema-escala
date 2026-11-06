"""Ponto rápido: relógio e regras de turno (sempre no fuso de São Paulo)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from . import calculo

FUSO = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    return datetime.now(FUSO)


LIMITE_ESQUECIDO_MIN = 20 * 60


class PontoErro(ValueError):
    """Ação inválida para o estado atual do turno."""


def inicio_do_turno(reg: dict) -> datetime:
    h, m = divmod(calculo.parse_hhmm(reg["entrada"]), 60)
    d = datetime.strptime(reg["data"], "%Y-%m-%d")
    return datetime(d.year, d.month, d.day, h, m, tzinfo=FUSO)


def _ancorar(turno: dict, hora: str) -> datetime:
    """Hora 'HH:MM' como datetime; anterior à entrada = dia seguinte."""
    ini = inicio_do_turno(turno)
    h, m = divmod(calculo.parse_hhmm(hora), 60)
    dt = ini.replace(hour=h, minute=m)
    return dt + timedelta(days=1) if dt < ini else dt


def _min(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def estado(
    turno_aberto: dict | None, agora: datetime
) -> Literal["livre", "trabalhando", "pausa", "esquecido"]:
    if not turno_aberto:
        return "livre"
    if agora - inicio_do_turno(turno_aberto) > timedelta(minutes=LIMITE_ESQUECIDO_MIN):
        return "esquecido"
    return "pausa" if turno_aberto.get("pausa_inicio") else "trabalhando"


def minutos_trabalhados(turno: dict, agora: datetime) -> int:
    total = _min(agora - inicio_do_turno(turno)) - int(turno.get("pausa_min") or 0)
    if turno.get("pausa_inicio"):
        total -= _min(agora - _ancorar(turno, turno["pausa_inicio"]))
    return max(total, 0)


def acao_entrei(agora: datetime) -> dict:
    return {
        "data": agora.strftime("%Y-%m-%d"),
        "entrada": agora.strftime("%H:%M"),
        "saida": None,
        "pausa_min": 0,
        "pausa_inicio": None,
    }


def acao_pausa(turno: dict, agora: datetime) -> dict:
    if turno.get("pausa_inicio"):
        raise PontoErro("Já está em pausa.")
    return {"pausa_inicio": agora.strftime("%H:%M")}


def _fechar_pausa(turno: dict, hora: str) -> int:
    ini = _ancorar(turno, turno["pausa_inicio"])
    fim = _ancorar(turno, hora)
    if fim < ini:
        fim += timedelta(days=1)
    return int(turno.get("pausa_min") or 0) + _min(fim - ini)


def acao_voltei(turno: dict, agora: datetime) -> dict:
    if not turno.get("pausa_inicio"):
        raise PontoErro("Não está em pausa.")
    return {"pausa_min": _fechar_pausa(turno, agora.strftime("%H:%M")), "pausa_inicio": None}


def acao_sai(turno: dict, hora: str) -> dict:
    pausa_min = int(turno.get("pausa_min") or 0)
    if turno.get("pausa_inicio"):
        pausa_min = _fechar_pausa(turno, hora)
    if _min(_ancorar(turno, hora) - inicio_do_turno(turno)) - pausa_min <= 0:
        raise PontoErro("A duração do turno ficaria zerada ou negativa.")
    return {"saida": hora, "pausa_min": pausa_min, "pausa_inicio": None}


def acao_desfazer_saida() -> dict:
    return {"saida": None}
