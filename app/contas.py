"""Preparo de conta nova: configuração e feriados padrão."""

from __future__ import annotations

from . import calculo
from .repo import Repo

FERIADOS_PADRAO: list[tuple[str, str]] = [
    ("2026-11-02", "Finados"),
    ("2026-11-15", "Proclamação da República"),
    ("2026-11-20", "Consciência Negra"),
    ("2026-12-25", "Natal"),
    ("2027-01-01", "Ano Novo"),
    ("2027-02-08", "Carnaval"),
    ("2027-02-09", "Carnaval"),
    ("2027-03-26", "Sexta-feira Santa"),
    ("2027-04-21", "Tiradentes"),
    ("2027-05-01", "Dia do Trabalho"),
    ("2027-05-27", "Corpus Christi"),
    ("2027-09-07", "Independência"),
    ("2027-10-12", "N. Sra. Aparecida"),
    ("2027-11-02", "Finados"),
    ("2027-11-15", "Proclamação da República"),
    ("2027-11-20", "Consciência Negra"),
    ("2027-12-25", "Natal"),
]


def preparar_conta_nova(repo: Repo) -> None:
    repo.salvar_config(dict(calculo.DEFAULT_CONFIG))
    for data, nome in FERIADOS_PADRAO:
        repo.salvar_feriado(data, nome)
