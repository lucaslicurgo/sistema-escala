"""Cálculo de horas, banco de horas, folgas e ciclos de escala.

Regras (configuráveis na tabela `configuracoes`):
- Jornada base por dia útil (padrão 10h). O que passar disso vira hora extra.
- Fins de semana e feriados: TODAS as horas contam como extra, multiplicadas
  pelo fator especial (padrão 2 = dobro), e o dia gera 1 folga (se habilitado).
- Ciclo de escala (ex.: 4x2): informa 4 dias trabalhados + 2 de descanso e uma
  data de referência (o 1º dia trabalhado de um ciclo conhecido). A partir daí:
  * Dia DE ESCALA: jornada normal (excedente = extra). Fim de semana dentro do
    ciclo NÃO dobra por padrão (opção "fds_no_ciclo_dobra" muda isso), mas
    feriado SEMPRE dobra e gera folga.
  * Descanso do ciclo: se mesmo assim você trabalhar SEM PODER MARCAR, todas as
    horas são extras (fator especial); folga só é credita se o dia for feriado.
- Compensação de dia inteiro: desconta a jornada base do saldo.
- Abono de horas: desconta a quantidade informada do saldo.
- Folga: consome 1 crédito de folga (não mexe no saldo de horas).
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Configurações padrão (usadas se a tabela `configuracoes` estiver vazia)
DEFAULT_CONFIG: dict[str, str] = {
    "jornada_diaria": "10:00",   # jornada base por dia (trabalhado)
    "fator_util": "1",           # multiplicador do excedente em dia comum
    "fator_especial": "2",       # multiplicador em fds/feriados/descanso trabalho (dobro)
    "folga_fds_feriado": "sim",  # trabalhar em fds/feriado gera 1 folga? ("sim"/"não")
    "ciclo_ativo": "nao",        # tem ciclo de escala (4x2, 12x36...)? ("sim"/"não")
    "ciclo_trabalha": "4",       # dias seguidos trabalhando no ciclo
    "ciclo_folga": "2",          # dias seguidos de descanso no ciclo
    "ciclo_referencia": "",      # data (YYYY-MM-DD) do 1º dia trabalhado de um ciclo
    "fds_no_ciclo_dobra": "nao", # fim de semana dentro da escala dobra? ("sim"/"não")
}

TIPOS_COMPENSACAO = ("compensacao", "abono", "folga")


def _sim(valor: Any) -> bool:
    return str(valor if valor is not None else "").strip().lower() in ("sim", "s", "1", "true", "on")


def hhmm(minutos: float) -> str:
    """Formata minutos como HH:MM (aceita negativo, ex.: -03:30)."""
    total = int(round(minutos))
    sinal = "-" if total < 0 else ""
    m = abs(total)
    return f"{sinal}{m // 60:02d}:{m % 60:02d}"


def parse_hhmm(texto: str | None) -> int | None:
    """Converte 'HH:MM' em minutos. Aceita '10', '10:30', '10,5' (decimal)."""
    if not texto or not texto.strip():
        return None
    t = texto.strip().replace(",", ".")
    if ":" in t:
        h, _, m = t.partition(":")
        try:
            return int(h) * 60 + int(m or 0)
        except ValueError:
            return None
    try:
        return int(round(float(t) * 60))
    except ValueError:
        return None


def jornada_minutos(cfg: dict[str, str]) -> int:
    valor = parse_hhmm(cfg.get("jornada_diaria")) or 600
    return max(0, valor)


def _fator(cfg: dict[str, str], chave: str, padrao: float) -> float:
    try:
        f = float(str(cfg.get(chave, padrao)).replace(",", "."))
        return max(1.0, f)
    except (TypeError, ValueError):
        return padrao


def _inteiro(valor: Any, padrao: int = 0) -> int:
    try:
        return max(0, int(float(str(valor).replace(",", "."))))
    except (TypeError, ValueError):
        return padrao


# ------------------------------------------------------- ciclo de escala

def ciclo_dados(cfg: dict[str, str]) -> tuple[int, int, date] | None:
    """Retorna (dias_trabalha, dias_folga, data_referencia) se o ciclo estiver bem configurado."""
    if not _sim(cfg.get("ciclo_ativo", "nao")):
        return None
    t = _inteiro(cfg.get("ciclo_trabalha"), 0)
    f = _inteiro(cfg.get("ciclo_folga"), 0)
    ref = str(cfg.get("ciclo_referencia", "")).strip()
    try:
        dref = date.fromisoformat(ref) if ref else None
    except ValueError:
        dref = None
    if t <= 0 or (t + f) <= 0 or dref is None:
        return None
    return (t, f, dref)


def ciclo_status(cfg: dict[str, str], d: date) -> str | None:
    """'trabalho' | 'descanso' para o dia do ciclo, ou None sem ciclo ativo."""
    ciclo = ciclo_dados(cfg)
    if not ciclo:
        return None
    t, f, dref = ciclo
    pos = (d - dref).days % (t + f)  # módulo positivo mesmo com datas antes da referência
    return "trabalho" if pos < t else "descanso"


# ------------------------------------------------------ cálculo do ponto

def calcular_registro(registro: dict[str, Any], feriados: set[str], cfg: dict[str, str]) -> dict[str, Any]:
    """Calcula um registro de ponto.

    - Saída menor que entrada = turn que passou da meia-noite.
    - Codifica o tipo_dia: util | escala | descanso | fds | feriado.
    """
    data_iso = registro["data"]
    dia = date.fromisoformat(data_iso)

    entrada = parse_hhmm(registro["entrada"])
    saida = parse_hhmm(registro["saida"])
    if entrada is None or saida is None:
        raise ValueError("Entrada e saída devem estar no formato HH:MM.")

    pausa = int(registro.get("pausa_min") or 0)
    duracao = saida - entrada
    if duracao <= 0:
        duracao += 24 * 60  # saiu depois da meia-noite
    duracao = max(0, duracao - pausa)

    eh_feriado = data_iso in feriados
    eh_fds = dia.weekday() >= 5

    tipo_ciclo = ciclo_status(cfg, dia)
    dobra_fds_ciclo = _sim(cfg.get("fds_no_ciclo_dobra", "nao"))
    concede_folga = _sim(cfg.get("folga_fds_feriado", "sim"))
    fator_esp = _fator(cfg, "fator_especial", 2.0)
    fator_ut = _fator(cfg, "fator_util", 1.0)
    j = jornada_minutos(cfg)

    # Dia "especial" = tudo trabalado vira extra:
    #  - sem ciclo: fds ou feriado
    #  - com ciclo: descanso trabalhado, ou fds/feriado (conforme regras)
    if tipo_ciclo == "trabalho":
        especial = eh_feriado or (eh_fds and dobra_fds_ciclo)
    elif tipo_ciclo == "descanso":
        especial = True
    else:
        especial = eh_feriado or eh_fds

    if especial:
        normal = 0
        extras = int(round(duracao * fator_esp))
        if eh_feriado:
            tipo_dia = "feriado"
        elif eh_fds:
            tipo_dia = "fds"
        elif tipo_ciclo == "descanso":
            tipo_dia = "descanso"
        else:
            tipo_dia = "escala"
        # Folga só é credita ao se trabalhar em dia que JÁ é feriado/fds
        folga = concede_folga and (eh_feriado or eh_fds)
    else:
        normal = min(duracao, j)
        extras = int(round(max(0, duracao - j) * fator_ut))
        tipo_dia = "escala" if tipo_ciclo == "trabalho" else "util"
        folga = False

    return {
        "tipo_dia": tipo_dia,
        "duracao_min": duracao,
        "normal_min": normal,
        "extras_min": extras,
        "folga": folga,
    }


def registro_fechado(reg: dict) -> bool:
    """Registro com saída preenchida (turno aberto não entra em cálculo)."""
    return bool(reg.get("saida"))


def resumo_banco(
    registros: list[dict],
    compensacoes: list[dict],
    feriados: set[str],
    cfg: dict[str, str],
) -> tuple[int, int]:
    """Retorna (saldo_min, folgas) considerando TODO o histórico."""
    saldo = 0
    folgas = 0

    for reg in registros:
        if not registro_fechado(reg):
            continue
        calc = calcular_registro(reg, feriados, cfg)
        saldo += calc["extras_min"]
        if calc["folga"]:
            folgas += 1

    j = jornada_minutos(cfg)
    for comp in compensacoes:
        tipo = comp.get("tipo")
        if tipo == "abono":
            saldo -= int(comp.get("horas_min") or 0)
        elif tipo == "compensacao":
            saldo -= j
        elif tipo == "folga":
            folgas -= 1

    return saldo, folgas
