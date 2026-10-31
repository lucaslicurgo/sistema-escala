"""Login simples de senha única (cookie assinado)."""

import hashlib
import hmac
import os

COOKIE_SESSAO = "sessao"

_DEFAULT_SECRET = "escala-julia-muda-isto-em-producao"


def _secret() -> str:
    return os.getenv("SECRET_KEY", "") or _DEFAULT_SECRET


def senha_admin() -> str:
    return os.getenv("ADMIN_PASSWORD", "") or "admin123"


def _hash(texto: str) -> str:
    return hashlib.sha256(hmac.new(_secret().encode(), texto.encode(), hashlib.sha256).digest()).hexdigest()


def token_da_senha() -> str:
    """Um 'token' determinístico e secreto baseado na senha + SECRET_KEY."""
    hash_senha = hashlib.sha256(senha_admin().encode()).digest()
    return hmac.new(_secret().encode(), hash_senha, hashlib.sha256).hexdigest()


def senha_valida(senha: str) -> bool:
    return hmac.compare_digest(_hash(senha), _hash(senha_admin()))
