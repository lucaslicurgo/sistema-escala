from urllib.parse import unquote

from app.repo import Repo


def _cadastro(client, convite="julia2026", **extra):
    dados = {"nome": "Ana", "email": "a@b.c", "senha": "123456", "convite": convite, **extra}
    return client.post("/cadastro", data=dados, follow_redirects=False)


def test_sem_login_redireciona(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_paginas_publicas_abrem(client):
    for rota in ("/login", "/cadastro", "/esqueci", "/redefinir-senha", "/healthz"):
        assert client.get(rota).status_code == 200


def test_cadastro_exige_convite(client, fake_auth, monkeypatch):
    monkeypatch.setenv("CODIGO_CONVITE", "julia2026")
    r = _cadastro(client, convite="errado")
    assert "Código de convite inválido" in unquote(r.headers["location"])
    assert fake_auth.usuarios == {}


def test_cadastro_desligado_sem_convite_configurado(client, fake_auth, monkeypatch):
    monkeypatch.delenv("CODIGO_CONVITE", raising=False)
    _cadastro(client, convite="")
    assert fake_auth.usuarios == {}


def test_cadastro_ok_prepara_conta_e_loga(client, fake_auth, fake_db, monkeypatch):
    monkeypatch.setenv("CODIGO_CONVITE", "julia2026")
    r = _cadastro(client)
    assert r.status_code == 303 and "sessao" in r.cookies
    uid = fake_auth.usuarios["a@b.c"].id
    assert len(Repo(uid).feriados()) == 17
    assert Repo(uid).config()["jornada_diaria"] == "10:00"


def test_cadastro_email_repetido(client, fake_auth, fake_db, monkeypatch):
    monkeypatch.setenv("CODIGO_CONVITE", "julia2026")
    _cadastro(client)
    r = _cadastro(client)
    assert "já tem conta" in unquote(r.headers["location"]) and "sessao" not in r.headers.get("set-cookie", "")


def test_login_errado(client, fake_auth):
    r = client.post("/login", data={"email": "x@y.z", "senha": "nada"}, follow_redirects=False)
    assert "E-mail ou senha incorretos" in unquote(r.headers["location"])


def test_login_ok_e_acesso_ao_sistema(client, fake_auth, fake_db, monkeypatch):
    monkeypatch.setenv("CODIGO_CONVITE", "c")
    _cadastro(client, convite="c")
    client.cookies.clear()
    r = client.post("/login", data={"email": " A@B.C ", "senha": "123456"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ponto"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/healthz").status_code == 200
    assert client.get("/dashboard", follow_redirects=False).status_code != 303


def test_logout_limpa_cookie(client_logado):
    c = client_logado("u1")
    r = c.post("/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert 'sessao=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]


def test_esqueci_sempre_responde_igual_e_usa_app_url(client, fake_auth, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://chronos.test/")
    r = client.post("/esqueci", data={"email": "alguem@x.y"}, follow_redirects=False)
    assert "Se esse e-mail tiver conta" in unquote(r.headers["location"])
    assert fake_auth.recuperacoes == [("alguem@x.y", "https://chronos.test/redefinir-senha")]


def test_redefinir_senha(client, fake_auth):
    r = client.post("/redefinir-senha", data={"access_token": "tok", "senha": "novasenha"}, follow_redirects=False)
    assert fake_auth.trocas == [("tok", "novasenha")]
    assert r.headers["location"].startswith("/login?aviso=")
    assert "Senha trocada" in unquote(r.headers["location"])


def test_cadastro_com_falha_ao_preparar_conta_ainda_loga(client, fake_auth, fake_db, monkeypatch):
    monkeypatch.setenv("CODIGO_CONVITE", "julia2026")

    def quebra(*a, **k):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(fake_db, "insert", quebra)
    r = _cadastro(client)
    assert r.status_code == 303 and "sessao" in r.cookies
    assert "Conta criada! Não consegui carregar os feriados padrão" in unquote(r.headers["location"])
    assert "fake" not in r.headers["location"] and "banco fora" not in unquote(r.headers["location"])
