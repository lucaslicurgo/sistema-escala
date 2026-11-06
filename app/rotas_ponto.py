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


@router.get("/ponto")
def tela_ponto(request: Request):
    ctx: dict = {"estado": "livre", "saldo_min": 0}
    try:
        repo = repo_de(request)
        agora = ponto.agora()
        hoje = agora.date()
        regs = repo.registros()
        comps = repo.compensacoes()
        feriados = _feriados(repo)
        cfg = repo.config()
        turno = _turno_aberto_de(regs)
        est = ponto.estado(turno, agora)
        ctx["estado"] = est
        ctx["saldo_min"] = calculo.resumo_banco(regs, comps, feriados, cfg)[0]
        ctx["turno"] = turno
        if turno:
            ini = ponto.inicio_do_turno(turno)
            ctx["entrada"] = turno["entrada"]
            ctx["inicio_iso"] = ini.isoformat()
            ctx["pausa_min"] = int(turno.get("pausa_min") or 0)
            ctx["pausa_desde"] = turno.get("pausa_inicio")
            ctx["data_turno"] = ini.strftime("%d/%m")
            mins = ponto.minutos_trabalhados(turno, agora)
            ctx["trabalhado"] = f"{mins // 60}h {mins % 60:02d}"
        else:
            reg_hoje = next((r for r in regs if r["data"] == hoje.isoformat()), None)
            ctx["fechado_hoje"] = reg_hoje if reg_hoje and calculo.registro_fechado(reg_hoje) else None
            if ctx["fechado_hoje"]:
                calc = calculo.calcular_registro(ctx["fechado_hoje"], feriados, cfg)
                ctx["resumo"] = {
                    "pausa": calculo.hhmm(int(ctx["fechado_hoje"].get("pausa_min") or 0)),
                    "total": calculo.hhmm(calc["duracao_min"]),
                    "extra": _com_sinal(calc["extras_min"]),
                }
            ctx["desfazivel"] = _desfazivel(regs, hoje)
    except Exception as e:
        ctx["db_erro"] = msg_de_erro(e)
    return render(request, "ponto.html", **ctx)


@router.post("/ponto/entrei")
def entrei(request: Request):
    try:
        repo = repo_de(request)
        agora = ponto.agora()
        if repo.turno_aberto() or repo.registro_do_dia(agora.strftime("%Y-%m-%d")):
            return redir(DESTINO, aviso="Você já marcou a entrada.")
        repo.inserir_registro(ponto.acao_entrei(agora))
        return redir(DESTINO, aviso=f"Entrada marcada às {agora.strftime('%H:%M')}.")
    except Exception as e:
        return redir(DESTINO, erro=f"Não consegui marcar: {msg_de_erro(e)}")


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
