"""Supabase Auth (GoTrue) via REST. Mensagens de erro já em português."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

MSG_GENERICA = "Não foi possível falar com o serviço de contas. Tente de novo."
MSG_LINK_EXPIRADO = "Esse link expirou. Peça um novo em \"Esqueci minha senha\"."
MSG_SENHA_CURTA = "A senha precisa ter pelo menos 6 caracteres."


class AuthErro(Exception):
    """Mensagem já pronta para mostrar na tela."""


@dataclass
class Usuario:
    id: str
    email: str
    nome: str


_cliente: httpx.Client | None = None


def _http() -> httpx.Client:
    global _cliente
    if _cliente is None:
        _cliente = httpx.Client(timeout=15)
    return _cliente


def _url(caminho: str) -> str:
    return (os.getenv("SUPABASE_URL") or "").rstrip("/").strip() + caminho


def _chave() -> str:
    return (os.getenv("SUPABASE_KEY") or "").strip()


def _headers(token: str | None = None) -> dict[str, str]:
    return {"apikey": _chave(), "Authorization": f"Bearer {token or _chave()}"}


def _pedir(metodo: str, caminho: str, *, json: dict, token: str | None = None,
           params: dict | None = None) -> httpx.Response:
    if not _chave() or not _url(""):
        raise AuthErro(MSG_GENERICA)
    try:
        return _http().request(
            metodo, _url(caminho), json=json, params=params, headers=_headers(token)
        )
    except httpx.HTTPError:
        raise AuthErro(MSG_GENERICA) from None


def _codigo(r: httpx.Response) -> str:
    try:
        corpo = r.json()
    except ValueError:
        return ""
    return " ".join(
        str(corpo.get(k, "")) for k in ("error_code", "msg", "message", "error_description")
    ).lower()


def _usuario(dados: dict) -> Usuario:
    meta = dados.get("user_metadata") or {}
    email = dados.get("email") or ""
    return Usuario(id=dados["id"], email=email, nome=meta.get("nome") or email.split("@")[0])


def _limpa(email: str) -> str:
    return email.strip().lower()


def cadastrar(email: str, senha: str, nome: str) -> Usuario:
    if len(senha) < 6:
        raise AuthErro(MSG_SENHA_CURTA)
    r = _pedir("POST", "/auth/v1/admin/users", json={
        "email": _limpa(email), "password": senha, "email_confirm": True,
        "user_metadata": {"nome": nome.strip()},
    })
    if r.status_code == 200:
        return _usuario(r.json())
    codigo = _codigo(r)
    if "email_exists" in codigo or "already" in codigo:
        raise AuthErro("Esse e-mail já tem conta. Tente entrar.")
    if "weak_password" in codigo or "password" in codigo:
        raise AuthErro(MSG_SENHA_CURTA)
    if "email" in codigo and "invalid" in codigo:
        raise AuthErro("Esse e-mail não parece válido.")
    raise AuthErro(MSG_GENERICA)


def entrar(email: str, senha: str) -> Usuario:
    r = _pedir("POST", "/auth/v1/token", params={"grant_type": "password"},
               json={"email": _limpa(email), "password": senha})
    if r.status_code == 200:
        return _usuario(r.json()["user"])
    if r.status_code in (400, 401, 422):
        raise AuthErro("E-mail ou senha incorretos.")
    raise AuthErro(MSG_GENERICA)


def enviar_recuperacao(email: str, redirect_to: str) -> None:
    r = _pedir("POST", "/auth/v1/recover", params={"redirect_to": redirect_to},
               json={"email": _limpa(email)})
    if r.status_code >= 500:
        raise AuthErro(MSG_GENERICA)


def trocar_senha(access_token: str, nova: str) -> None:
    if not (access_token or "").strip():
        raise AuthErro(MSG_LINK_EXPIRADO)
    if len(nova) < 6:
        raise AuthErro(MSG_SENHA_CURTA)
    r = _pedir("PUT", "/auth/v1/user", json={"password": nova}, token=access_token.strip())
    if r.status_code == 200:
        return
    if r.status_code in (401, 403):
        raise AuthErro(MSG_LINK_EXPIRADO)
    if "weak_password" in _codigo(r) or r.status_code == 422:
        raise AuthErro(MSG_SENHA_CURTA)
    raise AuthErro(MSG_GENERICA)
