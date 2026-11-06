"""Utilidades de resposta web: templates, render, redirecionamento e mensagens de erro."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import calculo
from .repo import Repo

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["hhmm"] = calculo.hhmm


def render(request: Request, template: str, **ctx: Any):
    ctx.setdefault("db_erro", None)
    ctx.setdefault("aviso", request.query_params.get("aviso"))
    ctx.setdefault("erro", request.query_params.get("erro"))
    ctx.setdefault("usuario", (getattr(request.state, "usuario", None) or {}).get("nome", ""))
    return templates.TemplateResponse(request, template, ctx)


def repo_de(request: Request) -> Repo:
    return request.state.repo


def redir(destino: str = "/dashboard", aviso: str | None = None, erro: str | None = None):
    sep = "&" if "?" in destino else "?"
    if aviso:
        destino += f"{sep}aviso={quote(str(aviso))}"
    elif erro:
        destino += f"{sep}erro={quote(str(erro))}"
    return RedirectResponse(destino, status_code=303)


def msg_de_erro(e: Exception) -> str:
    texto = str(e).strip() or type(e).__name__
    return texto[:300]
