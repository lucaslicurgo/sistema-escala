from app import calculo


def test_resumo_ignora_registro_aberto():
    regs = [{"data": "2026-11-04", "entrada": "08:00", "saida": "20:00", "pausa_min": 0},
            {"data": "2026-11-05", "entrada": "08:00", "saida": None, "pausa_min": 0}]
    saldo, _ = calculo.resumo_banco(regs, [], set(), calculo.DEFAULT_CONFIG)
    assert saldo == 120


def test_registro_fechado():
    assert calculo.registro_fechado({"saida": "18:00"})
    assert not calculo.registro_fechado({"saida": None})
    assert not calculo.registro_fechado({"saida": ""})
