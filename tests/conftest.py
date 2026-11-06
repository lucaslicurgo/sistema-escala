"""Fixtures compartilhadas. Novas fixtures (client, fake_auth...) entram aqui."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

UNICAS = {
    "registros": ("user_id", "data"),
    "feriados": ("user_id", "data"),
    "configuracoes": ("user_id", "chave"),
}


class FakeDB:
    """SupabaseDB em memória, com o subconjunto de PostgREST que o sistema usa."""

    def __init__(self) -> None:
        self.tabelas: dict[str, list[dict]] = {}
        self._ids = itertools.count(1)

    # -- filtros
    @staticmethod
    def _cond(valor: Any, expr: str) -> bool:
        op, _, ref = expr.partition(".")
        if op == "is":
            return valor is None if ref == "null" else valor is not None
        if valor is None:
            return False
        if op == "eq":
            return str(valor) == ref
        if op == "gte":
            return str(valor) >= ref
        if op == "lte":
            return str(valor) <= ref
        raise NotImplementedError(expr)

    def _casa(self, linha: dict, params: dict) -> bool:
        for campo, conds in params.items():
            if campo in ("order", "limit", "select"):
                continue
            for expr in conds if isinstance(conds, list) else [conds]:
                if not self._cond(linha.get(campo), expr):
                    return False
        return True

    def _achar(self, tabela: str, params: dict) -> list[dict]:
        return [l for l in self.tabelas.get(tabela, []) if self._casa(l, params)]

    # -- interface pública
    def select(self, tabela: str, params: dict | None = None) -> list[dict]:
        params = params or {}
        linhas = self._achar(tabela, params)
        if "order" in params:
            campo, _, sentido = params["order"].partition(".")
            linhas.sort(key=lambda l: str(l.get(campo)), reverse=sentido == "desc")
        if "limit" in params:
            linhas = linhas[: int(params["limit"])]
        return [dict(l) for l in linhas]

    def insert(
        self,
        tabela: str,
        dados: dict,
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict]:
        if on_conflict is not None and tuple(on_conflict.split(",")) != UNICAS.get(tabela):
            raise RuntimeError(f"Supabase respondeu 400: on_conflict invalido {on_conflict}")
        linhas = self.tabelas.setdefault(tabela, [])
        chave = UNICAS.get(tabela)
        if chave:
            igual = next(
                (l for l in linhas if all(l.get(c) == dados.get(c) for c in chave)),
                None,
            )
            if igual is not None:
                if not upsert:
                    raise RuntimeError(
                        "Supabase respondeu 409: duplicate key value violates "
                        f"unique constraint on {tabela}{chave}"
                    )
                igual.update(dados)
                return [dict(igual)]
        nova = {"id": next(self._ids), **dados}
        linhas.append(nova)
        return [dict(nova)]

    def update(self, tabela: str, filtro: dict, dados: dict) -> list[dict]:
        afetadas = self._achar(tabela, {k: f"eq.{v}" for k, v in filtro.items()})
        for linha in afetadas:
            linha.update(dados)
        return [dict(l) for l in afetadas]

    def delete(self, tabela: str, filtro: dict) -> list[dict]:
        afetadas = self._achar(tabela, {k: f"eq.{v}" for k, v in filtro.items()})
        self.tabelas[tabela] = [
            l for l in self.tabelas.get(tabela, []) if l not in afetadas
        ]
        return [dict(l) for l in afetadas]


@pytest.fixture
def fake_db(monkeypatch):
    banco = FakeDB()
    monkeypatch.setattr("app.repo.db", banco)
    return banco


class FakeAuth:
    """Supabase Auth em memória (substitui cadastrar/entrar/... do módulo)."""

    def __init__(self) -> None:
        self.usuarios: dict[str, Any] = {}
        self.senhas: dict[str, str] = {}
        self.recuperacoes: list[tuple[str, str]] = []
        self.trocas: list[tuple[str, str]] = []

    def cadastrar(self, email, senha, nome):
        from app.supabase_auth import AuthErro, Usuario

        email = email.strip().lower()
        if email in self.usuarios:
            raise AuthErro("Esse e-mail já tem conta. Tente entrar.")
        usuario = Usuario(id=f"uid-{len(self.usuarios) + 1}", email=email, nome=nome)
        self.usuarios[email] = usuario
        self.senhas[email] = senha
        return usuario

    def entrar(self, email, senha):
        from app.supabase_auth import AuthErro

        email = email.strip().lower()
        if self.senhas.get(email) != senha or email not in self.usuarios:
            raise AuthErro("E-mail ou senha incorretos.")
        return self.usuarios[email]

    def enviar_recuperacao(self, email, redirect_to):
        self.recuperacoes.append((email, redirect_to))

    def trocar_senha(self, access_token, nova):
        self.trocas.append((access_token, nova))


@pytest.fixture
def fake_auth(monkeypatch):
    auth = FakeAuth()
    for nome in ("cadastrar", "entrar", "enviar_recuperacao", "trocar_senha"):
        monkeypatch.setattr(f"app.supabase_auth.{nome}", getattr(auth, nome))
    return auth


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def client_logado(client):
    """Fábrica: client_logado(uid) devolve o client com cookie de sessão válido."""
    from app import sessao

    def _logar(uid: str, email: str = "a@b.c", nome: str = "Ana"):
        client.cookies.set(sessao.COOKIE, sessao.criar(uid, email, nome))
        return client

    return _logar


@pytest.fixture
def relogio(monkeypatch):
    """relogio(ano, mes, dia, hora, minuto) fixa ponto.agora() nesse instante em SP."""
    from datetime import datetime

    from app import ponto

    def _fixar(ano, mes, dia, hora=0, minuto=0):
        instante = datetime(ano, mes, dia, hora, minuto, tzinfo=ponto.FUSO)
        monkeypatch.setattr(ponto, "agora", lambda: instante)
        return instante

    return _fixar
