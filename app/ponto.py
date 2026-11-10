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
ALMOCO_MIN = 60  # o almoço desconta no máximo 1h e termina sozinho


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


def fim_do_almoco(turno: dict) -> datetime:
    return _ancorar(turno, turno["pausa_inicio"]) + timedelta(minutes=ALMOCO_MIN)


def normalizar(turno: dict, agora: datetime) -> dict:
    """Almoço que já passou de 1h conta como encerrado (1h descontada)."""
    if turno.get("pausa_inicio") and agora >= fim_do_almoco(turno):
        return {**turno, "pausa_min": int(turno.get("pausa_min") or 0) + ALMOCO_MIN,
                "pausa_inicio": None}
    return turno


def estado(
    turno_aberto: dict | None, agora: datetime
) -> Literal["livre", "trabalhando", "pausa", "esquecido"]:
    if not turno_aberto:
        return "livre"
    if agora - inicio_do_turno(turno_aberto) > timedelta(minutes=LIMITE_ESQUECIDO_MIN):
        return "esquecido"
    return "pausa" if normalizar(turno_aberto, agora).get("pausa_inicio") else "trabalhando"


def minutos_trabalhados(turno: dict, agora: datetime) -> int:
    turno = normalizar(turno, agora)
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


def _hora_valida(hora: str) -> str:
    minutos = calculo.parse_hhmm((hora or "").strip())
    if minutos is None or not (0 <= minutos < 24 * 60) or ":" not in hora:
        raise PontoErro("Informe a hora no formato HH:MM.")
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def acao_entrei_as(hora: str, agora: datetime) -> dict:
    """Entrada esquecida: abre o turno de hoje num horário que já passou."""
    hora = _hora_valida(hora)
    h, m = divmod(calculo.parse_hhmm(hora), 60)
    if agora.replace(hour=h, minute=m, second=0, microsecond=0) > agora:
        raise PontoErro("Esse horário ainda não chegou.")
    return {**acao_entrei(agora), "entrada": hora}


def acao_corrigir_entrada(turno: dict, hora: str, agora: datetime) -> dict:
    """Troca a hora de entrada do turno aberto (mesmo dia do turno)."""
    novo = {**turno, "entrada": _hora_valida(hora)}
    ini = inicio_do_turno(novo)
    if ini > agora:
        raise PontoErro("Esse horário ainda não chegou.")
    if agora - ini > timedelta(minutes=LIMITE_ESQUECIDO_MIN):
        raise PontoErro("Esse horário é muito antigo para um turno aberto.")
    if novo.get("pausa_inicio"):
        pausa = inicio_do_turno({**novo, "entrada": novo["pausa_inicio"]})
        if pausa < ini:
            pausa += timedelta(days=1)
        if pausa > agora:
            raise PontoErro("A entrada precisa ser antes do almoço.")
    return {"entrada": novo["entrada"]}


def acao_almoco(turno: dict, agora: datetime) -> dict:
    turno = normalizar(turno, agora)
    if turno.get("pausa_inicio"):
        raise PontoErro("Já está no almoço.")
    return {"pausa_min": int(turno.get("pausa_min") or 0), "pausa_inicio": agora.strftime("%H:%M")}


def _fechar_pausa(turno: dict, hora: str) -> int:
    """Soma o almoço aberto às pausas, contando no máximo ALMOCO_MIN."""
    ini = _ancorar(turno, turno["pausa_inicio"])
    fim = _ancorar(turno, hora)
    if fim < ini:
        fim += timedelta(days=1)
    return int(turno.get("pausa_min") or 0) + min(_min(fim - ini), ALMOCO_MIN)


def acao_voltei(turno: dict, agora: datetime) -> dict:
    turno = normalizar(turno, agora)
    if not turno.get("pausa_inicio"):
        raise PontoErro("Não está no almoço.")
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
