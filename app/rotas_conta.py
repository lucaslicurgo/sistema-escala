"""Rotas de conta: login, cadastro, recuperação de senha e logout."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from . import sessao, supabase_auth
from .contas import preparar_conta_nova
from .repo import Repo
from .supabase_auth import AuthErro
from .web import redir, render

router = APIRouter()

DESTINO_POS_LOGIN = "/ponto"


def _iniciar_sessao(usuario, aviso: str | None = None) -> RedirectResponse:
    resposta = redir(DESTINO_POS_LOGIN, aviso=aviso)
    resposta.set_cookie(
        sessao.COOKIE, sessao.criar(usuario.id, usuario.email, usuario.nome),
        max_age=sessao.VALIDADE, httponly=True, samesite="lax",
        secure=(os.getenv("APP_URL") or "").startswith("https"),
    )
    return resposta


def _convite_valido(informado: str) -> bool:
    esperado = os.getenv("CODIGO_CONVITE", "")
    return bool(esperado) and hmac.compare_digest(informado.encode(), esperado.encode())


@router.get("/login")
def pagina_login(request: Request):
    return render(request, "login.html")


@router.post("/login")
def fazer_login(email: str = Form(...), senha: str = Form(...)):
    try:
        return _iniciar_sessao(supabase_auth.entrar(email, senha))
    except AuthErro as e:
        return redir("/login", erro=str(e))


@router.get("/cadastro")
def pagina_cadastro(request: Request):
    return render(request, "cadastro.html")


@router.post("/cadastro")
def fazer_cadastro(
    nome: str = Form(...), email: str = Form(...),
    senha: str = Form(...), convite: str = Form(""),
):
    if not _convite_valido(convite.strip()):
        return redir("/cadastro", erro="Código de convite inválido.")
    try:
        usuario = supabase_auth.cadastrar(email, senha, nome)
    except AuthErro as e:
        return redir("/cadastro", erro=str(e))
    try:
        preparar_conta_nova(Repo(usuario.id))
    except Exception:
        return _iniciar_sessao(usuario, aviso=(
            "Conta criada! Não consegui carregar os feriados padrão — "
            "você pode adicioná-los em Configurações."))
    return _iniciar_sessao(usuario)


@router.get("/esqueci")
def pagina_esqueci(request: Request):
    return render(request, "esqueci.html")


@router.post("/esqueci")
def fazer_esqueci(request: Request, email: str = Form(...)):
    base = (os.getenv("APP_URL") or str(request.base_url)).rstrip("/")
    try:
        supabase_auth.enviar_recuperacao(email, base + "/redefinir-senha")
    except AuthErro:
        pass  # não revela se o e-mail existe nem falhas do serviço
    return redir("/esqueci", aviso="Se esse e-mail tiver conta, enviamos um link.")


@router.get("/redefinir-senha")
def pagina_redefinir(request: Request):
    return render(request, "redefinir.html")


@router.post("/redefinir-senha")
def fazer_redefinir(access_token: str = Form(""), senha: str = Form(...)):
    try:
        supabase_auth.trocar_senha(access_token, senha)
    except AuthErro as e:
        return redir("/esqueci", erro=str(e))
    return redir("/login", aviso="Senha trocada! Entre com a nova senha.")


@router.post("/logout")
def sair():
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(sessao.COOKIE)
    return resposta
