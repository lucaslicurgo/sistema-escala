"""Acesso aos dados de UMA pessoa: todo select/update/delete filtra por user_id
e todo insert grava o user_id."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import calculo
from .supabase_client import SupabaseDB, db


def limites_do_mes(mes: str) -> tuple[str, str]:
    ref = datetime.strptime(mes, "%Y-%m")
    primeiro = ref.date().replace(day=1)
    if ref.month == 12:
        ultimo = date(ref.year, 12, 31)
    else:
        ultimo = date(ref.year, ref.month + 1, 1) - timedelta(days=1)
    return primeiro.isoformat(), ultimo.isoformat()


class Repo:
    def __init__(self, user_id: str, banco: SupabaseDB | None = None) -> None:
        self.user_id = user_id
        self._banco = banco

    @property
    def _db(self) -> SupabaseDB:
        # resolve o `db` do módulo só na hora do uso (permite trocar em testes)
        return self._banco if self._banco is not None else db

    # ---------------------------------------------------------------- base

    def _listar(self, tabela: str, params: dict[str, Any] | None = None) -> list[dict]:
        p: dict[str, Any] = {"user_id": f"eq.{self.user_id}"}
        p.update(params or {})
        return self._db.select(tabela, params=p) or []

    def _por_id(self, tabela: str, id: int) -> dict | None:
        linhas = self._listar(tabela, {"id": f"eq.{id}"})
        return linhas[0] if linhas else None

    def _inserir(self, tabela: str, dados: dict, *, upsert: bool = False) -> dict:
        linhas = self._db.insert(
            tabela, {**dados, "user_id": self.user_id}, upsert=upsert
        )
        if isinstance(linhas, list):
            return linhas[0] if linhas else {}
        return linhas or {}

    def _filtro(self, id: int) -> dict:
        return {"id": id, "user_id": self.user_id}

    def _atualizar(self, tabela: str, id: int, dados: dict) -> bool:
        return bool(self._db.update(tabela, self._filtro(id), dados))

    def _excluir(self, tabela: str, id: int) -> bool:
        # o DELETE do PostgREST não devolve as linhas; confere antes
        if self._por_id(tabela, id) is None:
            return False
        self._db.delete(tabela, self._filtro(id))
        return True

    def _do_mes(self, tabela: str, mes: str | None) -> list[dict]:
        params: dict[str, Any] = {"order": "data.desc", "limit": 5000}
        if mes:
            primeiro, ultimo = limites_do_mes(mes)
            params["data"] = [f"gte.{primeiro}", f"lte.{ultimo}"]
        return self._listar(tabela, params)

    # -------------------------------------------------------------- config

    def config(self) -> dict[str, str]:
        cfg = dict(calculo.DEFAULT_CONFIG)
        for linha in self._listar("configuracoes"):
            cfg[linha["chave"]] = linha["valor"]
        return cfg

    def salvar_config(self, valores: dict[str, str]) -> None:
        for chave, valor in valores.items():
            self._inserir(
                "configuracoes", {"chave": chave, "valor": valor}, upsert=True
            )

    # ------------------------------------------------------------ feriados

    def feriados(self) -> list[dict]:
        return self._listar("feriados", {"order": "data.desc"})

    def salvar_feriado(self, data: str, nome: str) -> None:
        self._inserir("feriados", {"data": data, "nome": nome}, upsert=True)

    def excluir_feriado(self, id: int) -> bool:
        return self._excluir("feriados", id)

    # ----------------------------------------------------------- registros

    def registros(self, mes: str | None = None) -> list[dict]:
        return self._do_mes("registros", mes)

    def registro(self, id: int) -> dict | None:
        return self._por_id("registros", id)

    def registro_do_dia(self, data: str) -> dict | None:
        linhas = self._listar("registros", {"data": f"eq.{data}", "limit": 1})
        return linhas[0] if linhas else None

    def turno_aberto(self) -> dict | None:
        linhas = self._listar(
            "registros", {"saida": "is.null", "order": "data.desc", "limit": 1}
        )
        return linhas[0] if linhas else None

    def inserir_registro(self, dados: dict) -> dict:
        return self._inserir("registros", dados)

    def atualizar_registro(self, id: int, dados: dict) -> bool:
        return self._atualizar("registros", id, dados)

    def excluir_registro(self, id: int) -> bool:
        return self._excluir("registros", id)

    # -------------------------------------------------------- compensações

    def compensacoes(self, mes: str | None = None) -> list[dict]:
        return self._do_mes("compensacoes", mes)

    def inserir_compensacao(self, dados: dict) -> dict:
        return self._inserir("compensacoes", dados)

    def excluir_compensacao(self, id: int) -> bool:
        return self._excluir("compensacoes", id)
