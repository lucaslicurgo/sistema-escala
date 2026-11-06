import json

import httpx
import pytest

from app import supabase_auth as sa


@pytest.fixture
def servidor(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://sb.test")
    monkeypatch.setenv("SUPABASE_KEY", "chave")
    estado = {"vistos": [], "resposta": httpx.Response(200, json={})}

    def handler(req):
        estado["vistos"].append(req)
        return estado["resposta"]

    monkeypatch.setattr(sa, "_cliente", httpx.Client(transport=httpx.MockTransport(handler)))
    return estado


def _usuario_json():
    return {"id": "u1", "email": "a@b.c", "user_metadata": {"nome": "Ana"}}


def test_cadastrar_envia_admin_users(servidor):
    servidor["resposta"] = httpx.Response(200, json=_usuario_json())
    u = sa.cadastrar(" A@B.c ", "123456", " Ana ")
    assert u == sa.Usuario("u1", "a@b.c", "Ana")
    req = servidor["vistos"][0]
    assert req.url.path == "/auth/v1/admin/users"
    assert req.headers["apikey"] == "chave" and req.headers["Authorization"] == "Bearer chave"
    assert json.loads(req.content) == {
        "email": "a@b.c", "password": "123456", "email_confirm": True,
        "user_metadata": {"nome": "Ana"},
    }


def test_cadastrar_email_repetido(servidor):
    servidor["resposta"] = httpx.Response(422, json={"error_code": "email_exists", "msg": "already been registered"})
    with pytest.raises(sa.AuthErro, match="Esse e-mail já tem conta. Tente entrar."):
        sa.cadastrar("a@b.c", "123456", "Ana")


def test_cadastrar_senha_curta_nem_chama(servidor):
    with pytest.raises(sa.AuthErro, match="pelo menos 6 caracteres"):
        sa.cadastrar("a@b.c", "123", "Ana")
    assert servidor["vistos"] == []


def test_cadastrar_senha_fraca_do_servidor(servidor):
    servidor["resposta"] = httpx.Response(422, json={"error_code": "weak_password", "msg": "Password should be at least 6"})
    with pytest.raises(sa.AuthErro, match="pelo menos 6 caracteres"):
        sa.cadastrar("a@b.c", "123456", "Ana")


def test_entrar_ok(servidor):
    servidor["resposta"] = httpx.Response(200, json={"access_token": "t", "user": _usuario_json()})
    assert sa.entrar("a@b.c", "123456").id == "u1"
    req = servidor["vistos"][0]
    assert req.url.path == "/auth/v1/token" and req.url.params["grant_type"] == "password"


def test_entrar_credenciais_invalidas(servidor):
    servidor["resposta"] = httpx.Response(400, json={"error_code": "invalid_credentials"})
    with pytest.raises(sa.AuthErro, match="E-mail ou senha incorretos."):
        sa.entrar("a@b.c", "errada")


def test_recuperacao(servidor):
    sa.enviar_recuperacao("a@b.c", "http://app/redefinir-senha")
    req = servidor["vistos"][0]
    assert req.url.path == "/auth/v1/recover"
    assert req.url.params["redirect_to"] == "http://app/redefinir-senha"
    assert json.loads(req.content) == {"email": "a@b.c"}


def test_trocar_senha_usa_token_do_usuario(servidor):
    sa.trocar_senha("tok-usuario", "novasenha")
    req = servidor["vistos"][0]
    assert req.method == "PUT" and req.url.path == "/auth/v1/user"
    assert req.headers["Authorization"] == "Bearer tok-usuario"
    assert json.loads(req.content) == {"password": "novasenha"}


def test_trocar_senha_link_expirado(servidor):
    servidor["resposta"] = httpx.Response(401, json={"msg": "invalid JWT"})
    with pytest.raises(sa.AuthErro, match="expirou"):
        sa.trocar_senha("velho", "novasenha")


def test_erro_de_rede_vira_mensagem_generica(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://sb.test")
    monkeypatch.setenv("SUPABASE_KEY", "chave")

    def quebra(req):
        raise httpx.ConnectError("boom chave")

    monkeypatch.setattr(sa, "_cliente", httpx.Client(transport=httpx.MockTransport(quebra)))
    with pytest.raises(sa.AuthErro) as e:
        sa.entrar("a@b.c", "123456")
    assert "chave" not in str(e.value) and str(e.value) == sa.MSG_GENERICA


@pytest.mark.parametrize("token", ["", "   ", None])
def test_trocar_senha_sem_token_nao_chama_nem_usa_service_role(monkeypatch, token):
    monkeypatch.setenv("SUPABASE_URL", "http://sb.test")
    monkeypatch.setenv("SUPABASE_KEY", "chave")

    def proibido(req):
        raise AssertionError("não deveria chamar o Supabase")

    monkeypatch.setattr(sa, "_cliente", httpx.Client(transport=httpx.MockTransport(proibido)))
    with pytest.raises(sa.AuthErro, match="expirou"):
        sa.trocar_senha(token, "novasenha")
