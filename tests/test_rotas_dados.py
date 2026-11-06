from urllib.parse import unquote

from app.repo import Repo


def test_dashboard_e_calendario_com_turno_aberto(client_logado, fake_db):
    c = client_logado("uid-a")
    Repo("uid-a").inserir_registro({"data": "2026-11-05", "entrada": "08:00", "saida": None, "pausa_min": 0})
    r = c.get("/dashboard?mes=2026-11")
    assert r.status_code == 200 and "em andamento" in r.text and "db_erro" not in r.text
    assert c.get("/calendario?mes=2026-11").status_code == 200


def test_nao_mexe_em_dado_de_outra_pessoa(client_logado, fake_db):
    a = Repo("uid-a")
    reg = a.inserir_registro({"data": "2026-11-05", "entrada": "08:00", "saida": "18:00", "pausa_min": 0})
    comp = a.inserir_compensacao({"data": "2026-11-06", "tipo": "folga", "horas_min": 0})
    a.salvar_feriado("2026-12-25", "Natal"); fer = a.feriados()[0]
    c = client_logado("uid-b")
    assert "não encontrado" in unquote(c.get(f"/registros/{reg['id']}", follow_redirects=False).headers["location"])
    c.post(f"/registros/{reg['id']}", data={"data": "2026-11-05", "entrada": "01:00", "saida": "02:00", "pausa_min": 0})
    c.post(f"/registros/{reg['id']}/excluir"); c.post(f"/compensacoes/{comp['id']}/excluir"); c.post(f"/feriados/{fer['id']}/excluir")
    assert a.registro(reg["id"])["entrada"] == "08:00"
    assert len(a.compensacoes()) == 1 and len(a.feriados()) == 1


def test_dashboard_mostra_so_meus_dados(client_logado, fake_db):
    Repo("uid-a").inserir_registro({"data": "2026-11-05", "entrada": "08:00", "saida": "18:00", "pausa_min": 0, "observacao": "SEGREDO-A"})
    assert "SEGREDO-A" not in client_logado("uid-b").get("/dashboard?mes=2026-11").text


def test_registro_manual_dia_repetido(client_logado, fake_db):
    c = client_logado("uid-a")
    dados = {"data": "2026-11-05", "entrada": "08:00", "saida": "18:00", "pausa_min": 0}
    c.post("/registros", data=dados)
    r = c.post("/registros", data=dados, follow_redirects=False)
    assert "Já existe um registro em 05/11/2026" in unquote(r.headers["location"])


def test_configuracoes_e_feriado_por_pessoa(client_logado, fake_db):
    c = client_logado("uid-a")
    c.post("/feriados", data={"data": "2026-12-25", "nome": "Natal"})
    assert [f["nome"] for f in Repo("uid-a").feriados()] == ["Natal"]
    assert Repo("uid-b").feriados() == []
    assert c.get("/configuracoes").status_code == 200
