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
    relogio(2026, 11, 4, 12, 0); c.post("/ponto/almoco")
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


def test_almoco_sem_turno_nao_quebra(client_logado, fake_db, relogio):
    relogio(2026, 11, 4, 8, 0)
    r = client_logado("uid-a").post("/ponto/almoco", follow_redirects=False)
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
    assert "2h00" in t and "trabalhadas hoje" in t and "/ponto/almoco" in t and "/ponto/sai" in t
    assert "/ponto/entrei" not in t
    c.post("/ponto/almoco")
    relogio(2026, 11, 4, 9, 10)
    t = c.get("/ponto").text
    assert "Almoço 09:00 – 10:00" in t and "volta sozinho às 10:00" in t and "/ponto/voltei" in t and "/ponto/almoco" not in t
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


def test_esquecido_com_pausa_aberta_avisa_e_mostra_dia_fechado(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 12, 0); c.post("/ponto/almoco")
    relogio(2026, 11, 5, 9, 0)
    t = c.get("/ponto").text
    assert "O almoço iniciado às 12:00 conta no máximo 1h." in t
    r = c.post("/ponto/esquecido", data={"saida": "18:00"}, follow_redirects=False)
    assert "Dia fechado" in unquote(r.headers["location"])


def test_esquecido_sem_pausa_nao_mostra_aviso_de_pausa(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 5, 9, 0)
    assert "O almoço iniciado" not in c.get("/ponto").text


def test_pausa_mostra_tempo_trabalhado(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 10, 0); c.post("/ponto/almoco")
    relogio(2026, 11, 4, 10, 10)
    t = c.get("/ponto").text
    assert "2h00" in t and "50 min" in t and "Voltei antes" in t


def test_almoco_volta_sozinho_depois_de_1h(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 12, 0); c.post("/ponto/almoco")
    relogio(2026, 11, 4, 14, 0)
    t = c.get("/ponto").text
    assert "trabalhadas hoje" in t and "5h00" in t and "/ponto/almoco" in t
    r = c.post("/ponto/voltei", follow_redirects=False)
    assert "não está no almoço" in unquote(r.headers["location"])
    relogio(2026, 11, 4, 19, 0); r = c.post("/ponto/sai", follow_redirects=False)
    assert Repo("uid-a").registros()[0]["pausa_min"] == 60


def test_trabalhando_mostra_quanto_falta_e_ate_quando_sem_extra(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 12, 0); c.post("/ponto/almoco")
    relogio(2026, 11, 4, 12, 30); c.post("/ponto/voltei")
    relogio(2026, 11, 4, 14, 0)  # 5h30 trabalhadas, jornada 10h
    t = c.get("/ponto").text
    assert "5h30" in t and "faltam 4h30 da jornada" in t
    assert "18:30" in t  # sem extra até: agora + 4h30
    assert "0h30" in t  # pausas


def test_trabalhando_alem_da_jornada(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 19, 15)
    t = c.get("/ponto").text
    assert "+1h15 além da jornada" in t and "já passou" in t


def test_dia_fechado_mostra_extra_e_resumo(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 8, 0); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 19, 0); c.post("/ponto/sai")
    t = c.get("/ponto").text
    assert "Dia fechado. Até amanhã!" in t and "+1h00" in t and "08:00 – 19:00" in t


def test_livre_saudacao_e_jornada(client_logado, fake_db, relogio):
    relogio(2026, 11, 4, 7, 0)
    t = client_logado("uid-a", nome="Julia Souza").get("/ponto").text
    assert "Bom dia, Julia" in t and "de 10h00 de jornada" in t and "Quarta, 4 de novembro" in t


def test_esqueci_de_marcar_entrada(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 9, 30)
    assert "Esqueci de marcar" in c.get("/ponto").text
    r = c.post("/ponto/entrei", data={"hora": "08:00"}, follow_redirects=False)
    assert "Entrada marcada às 08:00" in unquote(r.headers["location"])
    reg = Repo("uid-a").registros()[0]
    assert (reg["data"], reg["entrada"]) == ("2026-11-04", "08:00")


def test_esqueci_de_marcar_entrada_no_futuro(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 9, 30)
    r = c.post("/ponto/entrei", data={"hora": "10:00"}, follow_redirects=False)
    assert "ainda não chegou" in unquote(r.headers["location"])
    assert Repo("uid-a").registros() == []


def test_corrigir_entrada_trabalhando(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 9, 30); c.post("/ponto/entrei")
    relogio(2026, 11, 4, 10, 0)
    assert "Corrigir horário de entrada" in c.get("/ponto").text
    r = c.post("/ponto/entrada", data={"hora": "08:00"}, follow_redirects=False)
    assert "Entrada corrigida para 08:00" in unquote(r.headers["location"])
    assert Repo("uid-a").registros()[0]["entrada"] == "08:00"


def test_corrigir_entrada_sem_turno_nao_faz_nada(client_logado, fake_db, relogio):
    c = client_logado("uid-a")
    relogio(2026, 11, 4, 9, 30)
    r = c.post("/ponto/entrada", data={"hora": "08:00"}, follow_redirects=False)
    assert r.status_code == 303 and Repo("uid-a").registros() == []
