"""Ponto rápido: tela única com botões de um toque (Entrei, Pausa, Voltei, Saí)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Form, Request

from . import calculo, ponto
from .web import msg_de_erro, redir, render, repo_de

router = APIRouter()

DESTINO = "/ponto"


def _feriados(repo) -> set[str]:
    return {f["data"] for f in repo.feriados()}


def _saldo(repo) -> int:
    saldo, _ = calculo.resumo_banco(
        repo.registros(), repo.compensacoes(), _feriados(repo), repo.config()
    )
    return saldo


def _com_sinal(minutos: int) -> str:
    texto = calculo.hhmm(minutos)
    return texto if texto.startswith("-") else "+" + texto


def _desfazivel(regs: list[dict], hoje: date) -> dict | None:
    """Último registro, se fechado e encerrado hoje (turno de hoje ou noturno que acabou hoje).

    `regs` vem ordenado do mais recente para o mais antigo.
    """
    if not regs or _turno_aberto_de(regs):
        return None
    reg = regs[0]
    if not calculo.registro_fechado(reg):
        return None
    data = date.fromisoformat(reg["data"])
    if data == hoje:
        return reg
    noturno = calculo.parse_hhmm(reg["saida"]) < calculo.parse_hhmm(reg["entrada"])
    if noturno and data == hoje - timedelta(days=1):
        return reg
    return None


def _turno_aberto_de(regs: list[dict]) -> dict | None:
    """Registro mais recente sem saída (mesma regra de `repo.turno_aberto()`)."""
    return next((r for r in regs if r.get("saida") is None), None)


DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
CIRCUNFERENCIA = 654  # anel da tela (r=104): 2·π·104 ≈ 653,5


def _hm(minutos: int) -> str:
    """Minutos como '3h42' (sem sinal)."""
    m = abs(int(minutos))
    return f"{m // 60}h{m % 60:02d}"


def _hm_sinal(minutos: int) -> str:
    return ("-" if minutos < 0 else "+") + _hm(minutos)


def _por_extenso(d: date) -> str:
    return f"{DIAS[d.weekday()].capitalize()}, {d.day} de {MESES[d.month - 1]}"


def _saudacao(hora: int) -> str:
    return "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"


def _anel(minutos: int, jornada: int) -> int:
    """Comprimento do traço do anel, proporcional à jornada (cheio ao completar)."""
    if jornada <= 0:
        return CIRCUNFERENCIA if minutos > 0 else 0
    return round(CIRCUNFERENCIA * min(1.0, max(0, minutos) / jornada))


def _recentes(regs: list[dict], feriados: set[str], cfg: dict, hoje: date) -> list[dict]:
    """Até 5 dias fechados antes de hoje, com a extra de cada um (lateral no computador)."""
    linhas = []
    for reg in regs:
        if reg["data"] >= hoje.isoformat() or not calculo.registro_fechado(reg):
            continue
        d = date.fromisoformat(reg["data"])
        extra = calculo.calcular_registro(reg, feriados, cfg)["extras_min"]
        linhas.append({
            "rotulo": f"{DIAS[d.weekday()][:3].capitalize()}, {d.strftime('%d/%m')}",
            "extra": _hm_sinal(extra) if extra else "0h00",
            "tem_extra": extra > 0,
        })
        if len(linhas) == 5:
            break
    return linhas


@router.get("/ponto")
def tela_ponto(request: Request):
    ctx: dict = {"estado": "livre", "saldo_min": 0, "folgas": 0, "jornada": "10h00",
                 "anel": 0, "circunferencia": CIRCUNFERENCIA, "recentes": []}
    try:
        repo = repo_de(request)
        agora = ponto.agora()
        hoje = agora.date()
        regs = repo.registros()
        comps = repo.compensacoes()
        feriados = _feriados(repo)
        cfg = repo.config()
        jornada = calculo.jornada_minutos(cfg)
        turno = _turno_aberto_de(regs)
        est = ponto.estado(turno, agora)
        ctx["estado"] = est
        ctx["saldo_min"], ctx["folgas"] = calculo.resumo_banco(regs, comps, feriados, cfg)
        ctx["turno"] = turno
        ctx["hoje_extenso"] = _por_extenso(hoje)
        ctx["saudacao"] = _saudacao(agora.hour)
        ctx["jornada"] = _hm(jornada)
        ctx["recentes"] = _recentes(regs, feriados, cfg, hoje)
        if turno:
            ini = ponto.inicio_do_turno(turno)
            mins = ponto.minutos_trabalhados(turno, agora)
            pausas = int(turno.get("pausa_min") or 0)
            decorrido = int((agora - ini).total_seconds() // 60)
            ctx["entrada"] = turno["entrada"]
            ctx["inicio_iso"] = ini.isoformat()
            ctx["pausa_min"] = pausas
            ctx["pausa_desde"] = turno.get("pausa_inicio")
            ctx["data_turno"] = ini.strftime("%d/%m")
            ctx["dia_turno"] = DIAS[ini.weekday()]
            ctx["trabalhado"] = _hm(mins)
            ctx["pausas"] = _hm(pausas)
            ctx["pausa_atual"] = max(0, decorrido - mins - pausas)
            ctx["anel"] = _anel(mins, jornada)
            ctx["faltam"] = _hm(jornada - mins) if mins < jornada else None
            ctx["extra_agora"] = _hm(mins - jornada) if mins > jornada else None
            ctx["sem_extra_ate"] = (
                (agora + timedelta(minutes=jornada - mins)).strftime("%H:%M") if mins < jornada else None
            )
        else:
            reg_hoje = next((r for r in regs if r["data"] == hoje.isoformat()), None)
            ctx["fechado_hoje"] = reg_hoje if reg_hoje and calculo.registro_fechado(reg_hoje) else None
            if ctx["fechado_hoje"]:
                calc = calculo.calcular_registro(ctx["fechado_hoje"], feriados, cfg)
                ctx["resumo"] = {
                    "pausa": _hm(int(ctx["fechado_hoje"].get("pausa_min") or 0)),
                    "total": _hm(calc["duracao_min"]),
                    "extra": _hm_sinal(calc["extras_min"]) if calc["extras_min"] else "0h00",
                    "tem_extra": calc["extras_min"] > 0,
                }
                ctx["anel"] = CIRCUNFERENCIA
            ctx["desfazivel"] = _desfazivel(regs, hoje)
    except Exception as e:
        ctx["db_erro"] = msg_de_erro(e)
    return render(request, "ponto.html", **ctx)


@router.post("/ponto/entrei")
def entrei(request: Request, hora: str = Form("")):
    """Entrei agora — ou, com `hora`, a entrada esquecida de hoje."""
    try:
        repo = repo_de(request)
        agora = ponto.agora()
        if repo.turno_aberto() or repo.registro_do_dia(agora.strftime("%Y-%m-%d")):
            return redir(DESTINO, aviso="Você já marcou a entrada.")
        dados = ponto.acao_entrei_as(hora, agora) if hora.strip() else ponto.acao_entrei(agora)
        repo.inserir_registro(dados)
        return redir(DESTINO, aviso=f"Entrada marcada às {dados['entrada']}.")
    except ponto.PontoErro as e:
        return redir(DESTINO, erro=str(e))
    except Exception as e:
        return redir(DESTINO, erro=f"Não consegui marcar: {msg_de_erro(e)}")


@router.post("/ponto/entrada")
def corrigir_entrada(request: Request, hora: str = Form("")):
    try:
        repo = repo_de(request)
        agora = ponto.agora()
        turno = repo.turno_aberto()
        if not turno or ponto.estado(turno, agora) not in ("trabalhando", "pausa"):
            return redir(DESTINO, aviso="Nenhum turno aberto para corrigir.")
        dados = ponto.acao_corrigir_entrada(turno, hora, agora)
        repo.atualizar_registro(turno["id"], dados)
        return redir(DESTINO, aviso=f"Entrada corrigida para {dados['entrada']}.")
    except ponto.PontoErro as e:
        return redir(DESTINO, erro=str(e))
    except Exception as e:
        return redir(DESTINO, erro=f"Não consegui corrigir: {msg_de_erro(e)}")


def _aplicar_no_turno(request: Request, acao, estados_ok: tuple[str, ...], ok: str, recusa: str):
    try:
        repo = repo_de(request)
        agora = ponto.agora()
        turno = repo.turno_aberto()
        if not turno or ponto.estado(turno, agora) not in estados_ok:
            return redir(DESTINO, aviso=recusa)
        repo.atualizar_registro(turno["id"], acao(turno, agora))
        return redir(DESTINO, aviso=ok)
    except ponto.PontoErro as e:
        return redir(DESTINO, aviso=str(e))
    except Exception as e:
        return redir(DESTINO, erro=f"Não consegui marcar: {msg_de_erro(e)}")


@router.post("/ponto/pausa")
def pausa(request: Request):
    return _aplicar_no_turno(
        request, ponto.acao_pausa, ("trabalhando",),
        "Pausa iniciada.", "Não dá para pausar agora.",
    )


@router.post("/ponto/voltei")
def voltei(request: Request):
    return _aplicar_no_turno(
        request, ponto.acao_voltei, ("pausa",),
        "Bem-vinda de volta!", "Você não está em pausa.",
    )


def _fechar(repo, turno: dict, hora: str):
    dados = ponto.acao_sai(turno, hora)
    repo.atualizar_registro(turno["id"], dados)
    return {**turno, **dados}


def _msg_dia_fechado(repo, fechado: dict) -> str:
    calc = calculo.calcular_registro(fechado, _feriados(repo), repo.config())
    return f"Dia fechado: {_com_sinal(calc['extras_min'])} de extra · saldo {_com_sinal(_saldo(repo))}"


@router.post("/ponto/sai")
def sai(request: Request):
    try:
        repo = repo_de(request)
        agora = ponto.agora()
        turno = repo.turno_aberto()
        if not turno:
            return redir(DESTINO, aviso="Nenhum turno aberto.")
        if ponto.estado(turno, agora) == "esquecido":
            return redir(DESTINO, aviso="Informe primeiro a hora da saída esquecida.")
        fechado = _fechar(repo, turno, agora.strftime("%H:%M"))
        return redir(DESTINO, aviso=_msg_dia_fechado(repo, fechado))
    except ponto.PontoErro:
        return redir(DESTINO, erro="Esse horário de saída não fecha com a entrada.")
    except Exception as e:
        return redir(DESTINO, erro=f"Não consegui marcar: {msg_de_erro(e)}")


@router.post("/ponto/esquecido")
def esquecido(request: Request, saida: str = Form("")):
    try:
        repo = repo_de(request)
        turno = repo.turno_aberto()
        if not turno or ponto.estado(turno, ponto.agora()) != "esquecido":
            return redir(DESTINO, aviso="Nenhuma saída esquecida.")
        if calculo.parse_hhmm(saida.strip()) is None:
            return redir(DESTINO, erro="Informe a hora no formato HH:MM.")
        try:
            fechado = _fechar(repo, turno, saida.strip())
        except ponto.PontoErro:
            return redir(DESTINO, erro="Esse horário de saída não fecha com a entrada.")
        return redir(DESTINO, aviso=_msg_dia_fechado(repo, fechado))
    except Exception as e:
        return redir(DESTINO, erro=f"Não consegui salvar: {msg_de_erro(e)}")


@router.post("/ponto/desfazer")
def desfazer(request: Request):
    try:
        repo = repo_de(request)
        reg = _desfazivel(repo.registros(), ponto.agora().date())
        if not reg:
            return redir(DESTINO, aviso="Não há saída para desfazer.")
        repo.atualizar_registro(reg["id"], ponto.acao_desfazer_saida())
        return redir(DESTINO, aviso="Saída desfeita. Você voltou a trabalhar.")
    except Exception as e:
        return redir(DESTINO, erro=f"Não consegui desfazer: {msg_de_erro(e)}")
