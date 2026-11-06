"""Acesso ao banco de dados do Supabase via API REST (PostgREST).

Usa a chave service_role no servidor, por isso o RLS não bloqueia
as operações internas do sistema.
"""

import os
from typing import Any, Optional

import httpx


class ConfigError(Exception):
    """Supabase não configurado no .env."""


class SupabaseDB:
    def __init__(self) -> None:
        self._cliente: Optional[httpx.Client] = None

    @property
    def _url(self) -> str:
        return (os.getenv("SUPABASE_URL") or "").rstrip("/").strip()

    @property
    def _key(self) -> str:
        return (os.getenv("SUPABASE_KEY") or "").strip()

    @property
    def ok(self) -> bool:
        return bool(self._url and self._key)

    @property
    def _http(self) -> httpx.Client:
        if self._cliente is None:
            self._cliente = httpx.Client(timeout=15)
        return self._cliente

    def _pedir(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> Any:
        if not self.ok:
            raise ConfigError(
                "Supabase não configurado. Preencha SUPABASE_URL e SUPABASE_KEY no arquivo .env "
                "(veja as instruções no README)."
            )
        headers = {"apikey": self._key, "Authorization": f"Bearer {self._key}"}
        if prefer:
            headers["Prefer"] = prefer
        resposta = self._http.request(
            method, f"{self._url}{path}", params=params, json=json, headers=headers
        )
        if resposta.status_code >= 400:
            raise RuntimeError(
                f"Supabase respondeu {resposta.status_code}: {resposta.text[:300]}"
            )
        if not resposta.content:
            return None
        try:
            return resposta.json()
        except ValueError:
            return None

    def select(self, tabela: str, params: Optional[dict] = None) -> Any:
        return self._pedir("GET", f"/rest/v1/{tabela}", params=params)

    def insert(
        self,
        tabela: str,
        dados: dict,
        *,
        upsert: bool = False,
        on_conflict: Optional[str] = None,
    ) -> Any:
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        params = {"on_conflict": on_conflict} if on_conflict else None
        return self._pedir(
            "POST", f"/rest/v1/{tabela}", params=params, json=dados, prefer=prefer
        )

    def update(self, tabela: str, filtro: dict, dados: dict) -> Any:
        params = {f"{campo}": f"eq.{valor}" for campo, valor in filtro.items()}
        return self._pedir(
            "PATCH",
            f"/rest/v1/{tabela}",
            params=params,
            json=dados,
            prefer="return=representation",
        )

    def delete(self, tabela: str, filtro: dict) -> Any:
        params = {f"{campo}": f"eq.{valor}" for campo, valor in filtro.items()}
        return self._pedir("DELETE", f"/rest/v1/{tabela}", params=params)


db = SupabaseDB()
