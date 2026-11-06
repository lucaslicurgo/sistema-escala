from datetime import datetime, timezone
from urllib.parse import unquote

from app import ponto
from app.repo import Repo


def test_entrei_duas_vezes_um_registro(client_logado, fake_db, relogio):
    relogio(2026, 11, 10, 8, 0)
    c = client_logado("uid-a")
    c.post("/ponto/entrei")
    r = c.post("/ponto/entrei", follow_redirects=False)
    assert r.status_code == 303 and "já marcou a entrada" in unquote(r.headers["location"])
    assert len(Repo("uid-a").registros()) == 1


def test_servidor_utc_grava_data_de_sp(client_logado, fake_db, monkeypatch):
    utc = datetime(2026, 11, 11, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(ponto, "agora", lambda: utc.astimezone(ponto.FUSO))
    client_logado("uid-a").post("/ponto/entrei")
    reg = Repo("uid-a").registros()[0]
    assert (reg["data"], reg["entrada"]) == ("2026-11-10", "22:00")


def test_fluxo_completo_mostra_extra(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 12, 0); c.post("/ponto/pausa")
    relogio(2026, 11, 4, 12, 30); c.post("/ponto/voltei")
    relogio(2026, 11, 4, 20, 30); r = c.post("/ponto/sai", follow_redirects=False)
    assert "Dia fechado: +02:00 de extra" in unquote(r.headers["location"])
    assert c.post("/ponto/sai", follow_redirects=False).status_code == 303


def test_esquecido_pede_saida_e_bloqueia_entrei(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 5, 9, 0)
    assert "Que horas saiu" in c.get("/ponto").text
    c.post("/ponto/entrei"); assert len(Repo("uid-a").registros()) == 1
    c.post("/ponto/esquecido", data={"saida": "18:00"})
    assert Repo("uid-a").registros()[0]["saida"] == "18:00"
    assert "Entrei" in c.get("/ponto").text


def test_pausa_sem_turno_nao_quebra(client_logado, fake_db, relogio):
    relogio(2026, 11, 4, 8, 0)
    r = client_logado("uid-a").post("/ponto/pausa", follow_redirects=False)
    assert r.status_code == 303


def test_raiz_vai_para_ponto(client_logado):
    assert client_logado("uid-a").get("/", follow_redirects=False).headers["location"] == "/ponto"


def test_esquecido_saida_invalida(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 5, 9, 0)
    r = c.post("/ponto/esquecido", data={"saida": "08:00"}, follow_redirects=False)
    assert "não fecha com a entrada" in unquote(r.headers["location"])
    assert Repo("uid-a").registros()[0]["saida"] is None


def test_esquecido_fora_do_estado_nao_faz_nada(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 9, 0)
    c.post("/ponto/esquecido", data={"saida": "10:00"})
    assert Repo("uid-a").registros()[0]["saida"] is None


def test_estados_da_tela(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 7, 0)
    t = c.get("/ponto").text
    assert "/ponto/entrei" in t and "/ponto/sai" not in t
    c.post("/ponto/entrei")
    relogio(2026, 11, 4, 9, 0)
    t = c.get("/ponto").text
    assert "Trabalhando há 2h 00" in t and "/ponto/pausa" in t and "/ponto/sai" in t
    assert "/ponto/entrei" not in t
    c.post("/ponto/pausa")
    relogio(2026, 11, 4, 9, 10)
    t = c.get("/ponto").text
    assert "Em pausa desde 09:00" in t and "/ponto/voltei" in t and "/ponto/pausa" not in t
    c.post("/ponto/voltei")
    relogio(2026, 11, 4, 17, 0)
    c.post("/ponto/sai")
    t = c.get("/ponto").text
    assert "/ponto/entrei" not in t and "Desfazer saída" in t


def test_desfazer_saida_reabre(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 17, 0); c.post("/ponto/sai")
    c.post("/ponto/desfazer")
    assert Repo("uid-a").registros()[0]["saida"] is None


def test_desfazer_dia_antigo_recusa(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 17, 0); c.post("/ponto/sai")
    relogio(2026, 11, 6, 9, 0)
    r = c.post("/ponto/desfazer", follow_redirects=False)
    assert "Não há saída para desfazer" in unquote(r.headers["location"])
    assert Repo("uid-a").registros()[0]["saida"] == "17:00"


def test_desfazer_turno_noturno_encerrado_hoje(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 22, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 5, 6, 0); c.post("/ponto/sai")
    c.post("/ponto/desfazer")
    assert Repo("uid-a").registros()[0]["saida"] is None
