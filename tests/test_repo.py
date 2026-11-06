from app.repo import Repo


def test_dados_isolados_por_pessoa(fake_db):
    a, b = Repo("uid-a"), Repo("uid-b")
    a.inserir_registro({"data": "2026-11-05", "entrada": "08:00", "saida": "18:00", "pausa_min": 0})
    assert len(a.registros()) == 1
    assert b.registros() == []


def test_nao_altera_nem_exclui_de_outra_pessoa(fake_db):
    a, b = Repo("uid-a"), Repo("uid-b")
    reg = a.inserir_registro({"data": "2026-11-05", "entrada": "08:00", "saida": "18:00", "pausa_min": 0})
    assert b.registro(reg["id"]) is None
    assert b.atualizar_registro(reg["id"], {"saida": "23:00"}) is False
    assert b.excluir_registro(reg["id"]) is False
    assert a.registro(reg["id"])["saida"] == "18:00"


def test_config_por_pessoa_com_padrao(fake_db):
    a, b = Repo("uid-a"), Repo("uid-b")
    a.salvar_config({"jornada_diaria": "08:00"})
    assert a.config()["jornada_diaria"] == "08:00"
    assert b.config()["jornada_diaria"] == "10:00"


def test_mesma_data_em_contas_diferentes(fake_db):
    for uid in ("uid-a", "uid-b"):
        Repo(uid).salvar_feriado("2026-12-25", "Natal")
    assert len(Repo("uid-a").feriados()) == 1


def test_turno_aberto(fake_db):
    a = Repo("uid-a")
    assert a.turno_aberto() is None
    a.inserir_registro({"data": "2026-11-05", "entrada": "08:00", "saida": None, "pausa_min": 0})
    assert a.turno_aberto()["data"] == "2026-11-05"
    assert Repo("uid-b").turno_aberto() is None


def test_registros_do_mes(fake_db):
    a = Repo("uid-a")
    for d in ("2026-10-31", "2026-11-01", "2026-11-30", "2026-12-01"):
        a.inserir_registro({"data": d, "entrada": "08:00", "saida": "18:00", "pausa_min": 0})
    assert [r["data"] for r in a.registros("2026-11")] == ["2026-11-30", "2026-11-01"]
