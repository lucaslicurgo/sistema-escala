"""Sessão por cookie assinado (JSON base64url + HMAC-SHA256)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

COOKIE = "sessao"
VALIDADE = 60 * 60 * 24 * 30  # 30 dias

_PADRAO = "escala-julia-muda-isto-em-producao"


def _segredo() -> bytes:
    return (os.getenv("SECRET_KEY", "") or _PADRAO).encode()


def _assinar(corpo: str) -> str:
    mac = hmac.new(_segredo(), corpo.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def criar(uid: str, email: str, nome: str) -> str:
    dados = {"uid": uid, "email": email, "nome": nome, "exp": int(time.time()) + VALIDADE}
    corpo = base64.urlsafe_b64encode(json.dumps(dados).encode()).decode().rstrip("=")
    return f"{corpo}.{_assinar(corpo)}"


def ler(token: str | None) -> dict | None:
    if not token or token.count(".") != 1:
        return None
    corpo, assinatura = token.split(".")
    if not hmac.compare_digest(assinatura, _assinar(corpo)):
        return None
    try:
        dados = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
        if dados["exp"] < time.time():
            return None
        return {"uid": dados["uid"], "email": dados["email"], "nome": dados["nome"]}
    except (ValueError, KeyError, TypeError):
        return None
