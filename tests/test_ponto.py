from datetime import datetime

import pytest

from app import calculo
from app.ponto import (
    FUSO, PontoErro, acao_desfazer_saida, acao_entrei, acao_almoco, acao_sai,
    acao_voltei, estado, minutos_trabalhados,
)


def sp(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=FUSO)


def test_turno_noturno_nao_e_esquecido():
    t = {**acao_entrei(sp(2026, 11, 10, 22, 0))}
    assert t["data"] == "2026-11-10" and t["entrada"] == "22:00"
    assert estado(t, sp(2026, 11, 11, 0, 30)) == "trabalhando"
    fechado = {**t, **acao_sai(t, "06:00")}
    assert calculo.calcular_registro(fechado, set(), calculo.DEFAULT_CONFIG)["duracao_min"] == 480


def test_esquecido_depois_de_20h():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    assert estado(t, sp(2026, 11, 11, 4, 0)) == "trabalhando"
    assert estado(t, sp(2026, 11, 11, 4, 1)) == "esquecido"


def test_livre_sem_turno():
    assert estado(None, sp(2026, 11, 10, 8, 0)) == "livre"


def test_varias_pausas_somam():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 10, 0)); t |= acao_voltei(t, sp(2026, 11, 10, 10, 15))
    t |= acao_almoco(t, sp(2026, 11, 10, 12, 0)); t |= acao_voltei(t, sp(2026, 11, 10, 12, 45))
    assert t["pausa_min"] == 60 and t["pausa_inicio"] is None
    assert minutos_trabalhados(t, sp(2026, 11, 10, 14, 0)) == 6 * 60 - 60


def test_minutos_trabalhados_com_pausa_em_andamento():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 10, 0))
    assert minutos_trabalhados(t, sp(2026, 11, 10, 10, 30)) == 120


def test_sai_durante_pausa_fecha_pausa():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 12, 0))
    assert estado(t, sp(2026, 11, 10, 12, 10)) == "pausa"
    t |= acao_sai(t, "12:30")
    assert t["saida"] == "12:30" and t["pausa_min"] == 30 and t["pausa_inicio"] is None


def test_pausa_atravessando_meia_noite():
    t = acao_entrei(sp(2026, 11, 10, 22, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 23, 50)); t |= acao_voltei(t, sp(2026, 11, 11, 0, 20))
    assert t["pausa_min"] == 30


def test_sem_pausa_vira_extra():
    t = acao_entrei(sp(2026, 11, 4, 8, 0)); t |= acao_sai(t, "20:00")
    assert calculo.calcular_registro(t, set(), calculo.DEFAULT_CONFIG)["extras_min"] == 120


def test_acao_invalida():
    t = acao_entrei(sp(2026, 11, 10, 8, 0)); t |= acao_almoco(t, sp(2026, 11, 10, 9, 0))
    with pytest.raises(PontoErro): acao_almoco(t, sp(2026, 11, 10, 9, 5))
    t2 = acao_entrei(sp(2026, 11, 10, 8, 0))
    with pytest.raises(PontoErro): acao_voltei(t2, sp(2026, 11, 10, 9, 0))


def test_sai_com_duracao_nao_positiva():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 8, 0))
    with pytest.raises(PontoErro): acao_sai(t, "08:00")


def test_almoco_termina_sozinho_em_1h():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 12, 0))
    assert estado(t, sp(2026, 11, 10, 12, 59)) == "pausa"
    assert estado(t, sp(2026, 11, 10, 13, 0)) == "trabalhando"
    assert minutos_trabalhados(t, sp(2026, 11, 10, 15, 0)) == 6 * 60
    with pytest.raises(PontoErro): acao_voltei(t, sp(2026, 11, 10, 13, 30))


def test_sai_depois_do_almoco_esquecido_desconta_so_1h():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 12, 0))
    t |= acao_sai(t, "18:00")
    assert t["pausa_min"] == 60 and t["pausa_inicio"] is None


def test_novo_almoco_guarda_o_anterior_encerrado_sozinho():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 12, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 16, 0))
    assert t["pausa_min"] == 60 and t["pausa_inicio"] == "16:00"


def test_esquecido_com_almoco_aberto_conta_no_maximo_1h():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 12, 0))
    assert estado(t, sp(2026, 11, 11, 9, 0)) == "esquecido"
    t |= acao_sai(t, "17:00")
    assert t["pausa_min"] == 60


def test_desfazer_saida():
    assert acao_desfazer_saida() == {"saida": None}


# --- entrada esquecida / corrigida -------------------------------------------
from app.ponto import acao_corrigir_entrada, acao_entrei_as


def test_entrei_as_horario_passado():
    t = acao_entrei_as("08:00", sp(2026, 11, 10, 9, 30))
    assert (t["data"], t["entrada"], t["saida"]) == ("2026-11-10", "08:00", None)


def test_entrei_as_futuro_recusa():
    with pytest.raises(PontoErro, match="ainda não chegou"):
        acao_entrei_as("10:00", sp(2026, 11, 10, 9, 30))


def test_entrei_as_formato_invalido():
    with pytest.raises(PontoErro):
        acao_entrei_as("xx", sp(2026, 11, 10, 9, 30))


def test_corrigir_entrada_para_mais_cedo():
    t = acao_entrei(sp(2026, 11, 10, 9, 30))
    t |= acao_corrigir_entrada(t, "08:00", sp(2026, 11, 10, 10, 0))
    assert t["entrada"] == "08:00"
    assert minutos_trabalhados(t, sp(2026, 11, 10, 10, 0)) == 120


def test_corrigir_entrada_futuro_recusa():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    with pytest.raises(PontoErro, match="ainda não chegou"):
        acao_corrigir_entrada(t, "11:00", sp(2026, 11, 10, 10, 0))


def test_corrigir_entrada_depois_da_pausa_recusa():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_almoco(t, sp(2026, 11, 10, 9, 0))
    with pytest.raises(PontoErro, match="antes do almoço"):
        acao_corrigir_entrada(t, "09:30", sp(2026, 11, 10, 10, 0))


def test_corrigir_entrada_turno_noturno():
    t = acao_entrei(sp(2026, 11, 10, 22, 30))
    t |= acao_corrigir_entrada(t, "22:00", sp(2026, 11, 11, 1, 0))
    assert t["entrada"] == "22:00"
    assert minutos_trabalhados(t, sp(2026, 11, 11, 1, 0)) == 180
