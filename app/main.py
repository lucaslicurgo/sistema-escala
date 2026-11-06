"""Chronos — Sistema de Escala & Banco de Horas — FastAPI + Supabase."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import calculo, ponto, sessao
from .rotas_conta import router as rotas_conta
from .rotas_ponto import router as rotas_ponto
from .repo import Repo
from .web import msg_de_erro, redir, render, repo_de

load_dotenv()

PROJETO_DIR = Path(__file__).resolve().parent.parent

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

app = FastAPI(title="Chronos", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(rotas_conta)
app.include_router(rotas_ponto)
app.mount("/static", StaticFiles(directory=str(PROJETO_DIR / "static")), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(PROJETO_DIR / "static" / "brand" / "favicon.ico")


# ------------------------------------------------------------------- dados

def infos_mes(request: Request, mes: str | None) -> tuple[date, str, str, str]:
    """Retorna (ref, mes_atual, mes_anterior, mes_seguinte) como 'YYYY-MM'."""
    hoje = ponto.agora().date()
    if mes:
        try:
            hoje = datetime.strptime(mes, "%Y-%m").date()
        except ValueError:
            pass
    ano, num = hoje.year, hoje.month
    atual = f"{ano}-{num:02d}"
    anterior = f"{ano - 1}-12" if num == 1 else f"{ano}-{num - 1:02d}"
    seguinte = f"{ano + 1}-01" if num == 12 else f"{ano}-{num + 1:02d}"
    return hoje, atual, anterior, seguinte


# ----------------------------------------------------------------- sessão

PUBLICAS = ("/login", "/cadastro", "/esqueci", "/redefinir-senha", "/healthz", "/favicon.ico")


@app.middleware("http")
async def verifica_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in PUBLICAS:
        return await call_next(request)
    usuario = sessao.ler(request.cookies.get(sessao.COOKIE))
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    request.state.usuario = usuario
    request.state.repo = Repo(usuario["uid"])
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def raiz():
    return RedirectResponse("/ponto", status_code=303)


# ------------------------------------------------------------------ dashboard

@app.get("/dashboard")
def dashboard(request: Request, mes: str | None = None):
    ref, mes_atual, mes_anterior, mes_seguinte = infos_mes(request, mes)
    ctx = {
        "mes": mes_atual,
        "mes_label": f"{MESES[ref.month - 1]} {ref.year}",
        "mes_anterior": mes_anterior,
        "mes_seguinte": mes_seguinte,
        "hoje": ponto.agora().date().isoformat(),
        "saldo_min": 0,
        "folgas": 0,
        "extras_mes": 0,
        "jornada_min": calculo.jornada_minutos(calculo.DEFAULT_CONFIG),
        "registros": [],
        "compensacoes": [],
        "saldo_positivo": True,
    }

    try:
        repo = repo_de(request)
        cfg = repo.config()
        feriados = {f["data"] for f in repo.feriados()}
        registros = repo.registros(mes_atual)
        compensacoes = repo.compensacoes(mes_atual)

        # Resumo com histórico completo
        saldo, folgas = calculo.resumo_banco(
            repo.registros(), repo.compensacoes(), feriados, cfg
        )

        calculados = []
        extras_mes = 0
        total_horas_trab = 0
        linhas = []
        for reg in registros:
            dia_d = date.fromisoformat(reg["data"])
            pausa = int(reg.get("pausa_min") or 0)
            if not calculo.registro_fechado(reg):
                linhas.append({
                    "tipo": "ponto",
                    "id": reg["id"],
                    "data_iso": reg["data"],
                    "data": dia_d.strftime("%d/%m/%Y"),
                    "dia": DIAS_SEMANA[dia_d.weekday()],
                    "etiqueta": None,
                    "entrada": reg["entrada"],
                    "pausa": f"{calculo.hhmm(pausa)} ({pausa}m)" if pausa else "--:--",
                    "saida": None,
                    "aberto": True,
                    "total": "--:--",
                    "mov": "em andamento",
                    "tem_extra": False,
                    "folga": False,
                    "obs": reg.get("observacao"),
                })
                continue
            calc = calculo.calcular_registro(reg, feriados, cfg)
            calc["dia_semana"] = DIAS_SEMANA[dia_d.weekday()]
            calculados.append(calc)
            extras_mes += calc["extras_min"]
            total_horas_trab += calc["duracao_min"]

            linhas.append({
                "tipo": "ponto",
                "id": reg["id"],
                "data_iso": reg["data"],
                "data": dia_d.strftime("%d/%m/%Y"),
                "dia": calc["dia_semana"],
                "etiqueta": None if calc["tipo_dia"] == "util" else calc["tipo_dia"],
                "entrada": reg["entrada"],
                "pausa": f"{calculo.hhmm(pausa)} ({pausa}m)" if pausa else "--:--",
                "saida": reg["saida"],
                "total": calculo.hhmm(calc["duracao_min"]),
                "mov": calculo.hhmm(calc["extras_min"]),
                "tem_extra": calc["extras_min"] > 0,
                "folga": calc["folga"],
                "obs": reg.get("observacao"),
            })
        dias_count = len(linhas)
        jmin = calculo.jornada_minutos(cfg)

        for comp in compensacoes:
            tipo = comp["tipo"]
            if tipo == "abono":
                mov, status = "-" + calculo.hhmm(comp.get("horas_min") or 0), "Abonado"
            elif tipo == "compensacao":
                mov, status = "-" + calculo.hhmm(jmin), "Compensado"
            else:
                mov, status = "1 folga", "Folga"
            dia_d = date.fromisoformat(comp["data"])
            linhas.append({
                "tipo": "compensacao",
                "id": comp["id"],
                "data_iso": comp["data"],
                "data": dia_d.strftime("%d/%m/%Y"),
                "dia": DIAS_SEMANA[dia_d.weekday()],
                "rotulo": {"compensacao": "Folga / Comp.", "abono": "Abono", "folga": "Folga"}[tipo],
                "mov": mov,
                "status": status,
                "obs": comp.get("observacao"),
            })
        linhas.sort(key=lambda l: l["data_iso"], reverse=True)
        n_extras = sum(1 for l in linhas if l["tipo"] == "ponto" and l["tem_extra"])

        ctx.update({
            "saldo_min": saldo,
            "saldo_positivo": saldo >= 0,
            "folgas": folgas,
            "extras_mes": extras_mes,
            "jornada_min": jmin,
            "fator_util": float(cfg.get("fator_util", "1")),
            "fator_especial": float(cfg.get("fator_especial", "2")),
            "linhas": linhas,
            "dias_count": dias_count,
            "n_extras": n_extras,
            "n_comp": len(compensacoes),
            "total_horas_trab": calculo.hhmm(total_horas_trab),
        })
    except Exception as e:  # ConfigError, conexão etc.
        ctx["db_erro"] = msg_de_erro(e)

    return render(request, "dashboard.html", **ctx)


@app.post("/registros")
async def criar_registro(
    request: Request,
    data: str = Form(...),
    entrada: str = Form(...),
    saida: str = Form(...),
    pausa_min: int = Form(0),
    observacao: str = Form(""),
):
    try:
        registro = {
            "data": data,
            "entrada": entrada,
            "saida": saida,
            "pausa_min": max(0, pausa_min),
            "observacao": observacao.strip() or None,
        }
        # valida cálculo antes de salvar
        calculo.calcular_registro(registro, set(), calculo.DEFAULT_CONFIG)
        repo = repo_de(request)
        if repo.registro_do_dia(data):
            dia = date.fromisoformat(data).strftime("%d/%m/%Y")
            return redir(erro=f"Já existe um registro em {dia}. Edite o existente.")
        repo.inserir_registro(registro)
        return redir(aviso=f"Registro de {data} salvo com sucesso!")
    except Exception as e:
        return redir(erro=f"Não consegui salvar: {msg_de_erro(e)}")


@app.get("/registros/{registro_id}")
def editar_registro_pagina(request: Request, registro_id: int):
    try:
        reg = repo_de(request).registro(registro_id)
        if not reg:
            return redir(erro="Registro não encontrado.")
        return render(request, "registro_editar.html", registro=reg)
    except Exception as e:
        return redir(erro=msg_de_erro(e))


@app.post("/registros/{registro_id}")
async def salvar_registro(
    request: Request,
    registro_id: int,
    data: str = Form(...),
    entrada: str = Form(...),
    saida: str = Form(...),
    pausa_min: int = Form(0),
    observacao: str = Form(""),
):
    try:
        registro = {
            "data": data,
            "entrada": entrada,
            "saida": saida,
            "pausa_min": max(0, pausa_min),
            "observacao": observacao.strip() or None,
            "pausa_inicio": None,
        }
        calculo.calcular_registro(registro, set(), calculo.DEFAULT_CONFIG)
        if not repo_de(request).atualizar_registro(registro_id, registro):
            return redir(erro="Registro não encontrado.")
        return redir(aviso="Registro atualizado!")
    except Exception as e:
        return redir(erro=f"Não consegui atualizar: {msg_de_erro(e)}")


@app.post("/registros/{registro_id}/excluir")
async def excluir_registro(request: Request, registro_id: int):
    try:
        if not repo_de(request).excluir_registro(registro_id):
            return redir(erro="Registro não encontrado.")
        return redir(aviso="Registro excluído.")
    except Exception as e:
        return redir(erro=f"Não consegui excluir: {msg_de_erro(e)}")


@app.post("/compensacoes")
async def criar_compensacao(
    request: Request,
    data: str = Form(...),
    tipo: str = Form(...),
    horas_min: int = Form(0),
    observacao: str = Form(""),
):
    if tipo not in calculo.TIPOS_COMPENSACAO:
        return redir(erro="Tipo de compensação inválido.")
    if tipo == "abono" and horas_min <= 0:
        return redir(erro="Para abono, informe os minutos (ex.: 120 = 2h).")
    if tipo != "abono":
        horas_min = 0
    try:
        repo_de(request).inserir_compensacao({
            "data": data,
            "tipo": tipo,
            "horas_min": max(0, horas_min),
            "observacao": observacao.strip() or None,
        })
        rotulo = {"compensacao": "Compensação", "abono": "Abono", "folga": "Folga"}[tipo]
        return redir(aviso=f"{rotulo} lançada em {data}!")
    except Exception as e:
        return redir(erro=f"Não consegui lançar: {msg_de_erro(e)}")


@app.post("/compensacoes/{comp_id}/excluir")
async def excluir_compensacao(request: Request, comp_id: int):
    try:
        if not repo_de(request).excluir_compensacao(comp_id):
            return redir(erro="Lançamento não encontrado.")
        return redir(aviso="Lançamento excluído.")
    except Exception as e:
        return redir(erro=f"Não consegui excluir: {msg_de_erro(e)}")


# ------------------------------------------------------------- calendário

@app.get("/calendario")
def pagina_calendario(request: Request, mes: str | None = None):
    ref, mes_atual, mes_anterior, mes_seguinte = infos_mes(request, mes)
    ano, num = ref.year, ref.month
    primeiro = date(ano, num, 1)
    if num == 12:
        ultimo = date(ano, 12, 31)
    else:
        ultimo = date(ano, num + 1, 1) - timedelta(days=1)

    offset = (primeiro.weekday() + 1) % 7  # semana começa no domingo
    dias_no_mes = ultimo.day
    celulas: list[dict] = [{"vazio": True} for _ in range(offset)]

    ctx: dict[str, Any] = {
        "mes": mes_atual,
        "mes_label": f"{MESES[num - 1]} {ano}",
        "mes_anterior": mes_anterior,
        "mes_seguinte": mes_seguinte,
        "hoje_iso": ponto.agora().date().isoformat(),
        "celulas": celulas,
        "ciclo_ativo": False,
        "stats": {"pontos": 0, "comps": 0, "extras": 0, "folgas": 0, "sem_ponto": 0},
    }

    try:
        repo = repo_de(request)
        cfg = repo.config()
        ctx["ciclo_ativo"] = calculo.ciclo_dados(cfg) is not None
        feriado_rows = repo.feriados()
        nomes_feriados = {f["data"]: f["nome"] for f in feriado_rows}

        dias: dict[str, dict] = {}
        for reg in repo.registros(mes_atual):
            if not calculo.registro_fechado(reg):
                d = dias.setdefault(reg["data"], {"pontos": [], "comps": []})
                d["pontos"].append({
                    "id": reg["id"], "entrada": reg["entrada"], "saida": None,
                    "total": "--:--", "extras": None, "folga": False, "fds": False,
                })
                continue
            calc = calculo.calcular_registro(reg, nomes_feriados, cfg)
            d = dias.setdefault(reg["data"], {"pontos": [], "comps": []})
            d["pontos"].append({
                "id": reg["id"],
                "entrada": reg["entrada"],
                "saida": reg["saida"],
                "total": calculo.hhmm(calc["duracao_min"]),
                "extras": calculo.hhmm(calc["extras_min"]) if calc["extras_min"] else None,
                "folga": calc["folga"],
                "fds": calc["tipo_dia"] == "fds",
            })
            ctx["stats"]["extras"] += calc["extras_min"]
            if calc["folga"]:
                ctx["stats"]["folgas"] += 1

        jmin = calculo.jornada_minutos(cfg)
        for comp in repo.compensacoes(mes_atual):
            tipo = comp["tipo"]
            if tipo == "abono":
                mov = "-" + calculo.hhmm(comp.get("horas_min") or 0)
            elif tipo == "compensacao":
                mov = "-" + calculo.hhmm(jmin)
            else:
                mov = "1 folga"
            d = dias.setdefault(comp["data"], {"pontos": [], "comps": []})
            d["comps"].append({
                "status": {"compensacao": "Compensada", "abono": "Abonada", "folga": "Folga usada"}[tipo],
                "mov": mov,
            })
            ctx["stats"]["comps"] += 1

        ctx["stats"]["pontos"] = sum(1 for info in dias.values() if info["pontos"])

        for dia_num in range(1, dias_no_mes + 1):
            iso = f"{ano:04d}-{num:02d}-{dia_num:02d}"
            info = dias.get(iso)
            dia_d = date(ano, num, dia_num)
            escala_info = calculo.ciclo_status(cfg, dia_d)
            if escala_info == "trabalho" and not (info and info["pontos"]):
                ctx["stats"]["sem_ponto"] += 1
            celulas.append({
                "vazio": False,
                "dia": dia_num,
                "iso": iso,
                "fds": dia_d.weekday() >= 5,
                "feriado": nomes_feriados.get(iso),
                "escala": escala_info,
                "pontos": info["pontos"] if info else [],
                "comps": info["comps"] if info else [],
                "tem": bool(info),
            })
        while len(celulas) % 7 != 0:
            celulas.append({"vazio": True})

        ctx["celulas"] = celulas
    except Exception as e:
        ctx["db_erro"] = msg_de_erro(e)

    return render(request, "calendario.html", **ctx)


# ------------------------------------------------------------- configurações

DIAS_CORTO = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


@app.get("/configuracoes")
def pagina_configuracoes(request: Request):
    ctx: dict[str, Any] = {
        "config": calculo.DEFAULT_CONFIG,
        "feriados": [],
        "ciclo_ativo": False,
        "ciclo_exemplo": [],
    }
    try:
        repo = repo_de(request)
        cfg = repo.config()
        ctx["config"] = cfg
        ctx["ciclo_ativo"] = calculo.ciclo_dados(cfg) is not None
        if ctx["ciclo_ativo"]:
            exemplo = []
            hoje = ponto.agora().date()
            for i in range(15):
                d = hoje + timedelta(days=i)
                exemplo.append({
                    "data": d.strftime("%d/%m"),
                    "sigla": DIAS_CORTO[d.weekday()],
                    "status": calculo.ciclo_status(cfg, d),
                })
            ctx["ciclo_exemplo"] = exemplo
        ctx["feriados"] = repo.feriados()
    except Exception as e:
        ctx["db_erro"] = msg_de_erro(e)
    return render(request, "configuracoes.html", **ctx)


@app.post("/configuracoes")
async def salvar_configuracoes(
    request: Request,
    jornada_diaria: str = Form(...),
    fator_util: str = Form(...),
    fator_especial: str = Form(...),
    folga_fds_feriado: str = Form("nao"),
    ciclo_ativo: str = Form("nao"),
    ciclo_trabalha: str = Form("4"),
    ciclo_folga: str = Form("2"),
    ciclo_referencia: str = Form(""),
    fds_no_ciclo_dobra: str = Form("nao"),
):
    try:
        if calculo.parse_hhmm(jornada_diaria) is None:
            return redir("/configuracoes", erro="Jornada inválida. Use HH:MM (ex.: 10:00).")
        try:
            float(fator_util.replace(",", "."))
            float(fator_especial.replace(",", "."))
        except ValueError:
            return redir("/configuracoes", erro="Fatores devem ser números (ex.: 1.5 ou 2).")

        ativo = ciclo_ativo == "sim"
        try:
            t = int(float(ciclo_trabalha.replace(",", ".")))
            f = int(float(ciclo_folga.replace(",", ".")))
        except ValueError:
            return redir("/configuracoes", erro="Dias do ciclo devem ser números inteiros (ex.: 4 e 2).")
        referencia = ciclo_referencia.strip()
        if ativo:
            if t <= 0:
                return redir("/configuracoes", erro="Dias trabalhados no ciclo devem ser pelo menos 1.")
            if not referencia:
                return redir("/configuracoes", erro="Informe a data de referência (1º dia trabalhado de um ciclo).")
            try:
                date.fromisoformat(referencia)
            except ValueError:
                return redir("/configuracoes", erro="Data de referência inválida.")

        valores = {
            "jornada_diaria": jornada_diaria.strip(),
            "fator_util": fator_util.strip().replace(",", "."),
            "fator_especial": fator_especial.strip().replace(",", "."),
            "folga_fds_feriado": "sim" if folga_fds_feriado == "sim" else "nao",
            "ciclo_ativo": "sim" if ativo else "nao",
            "ciclo_trabalha": str(max(0, t)),
            "ciclo_folga": str(max(0, f)),
            "ciclo_referencia": referencia,
            "fds_no_ciclo_dobra": "sim" if fds_no_ciclo_dobra == "sim" else "nao",
        }
        repo_de(request).salvar_config(valores)
        return redir("/configuracoes", aviso="Configurações salvas!")
    except Exception as e:
        return redir("/configuracoes", erro=msg_de_erro(e))


@app.post("/feriados")
async def criar_feriado(request: Request, data: str = Form(...), nome: str = Form(...)):
    try:
        repo_de(request).salvar_feriado(data, nome.strip())
        return redir("/configuracoes", aviso=f"Feriado {data} salvo!")
    except Exception as e:
        return redir("/configuracoes", erro=msg_de_erro(e))


@app.post("/feriados/{feriado_id}/excluir")
async def excluir_feriado(request: Request, feriado_id: int):
    try:
        if not repo_de(request).excluir_feriado(feriado_id):
            return redir("/configuracoes", erro="Feriado não encontrado.")
        return redir("/configuracoes", aviso="Feriado excluído.")
    except Exception as e:
        return redir("/configuracoes", erro=msg_de_erro(e))
