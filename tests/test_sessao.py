import time

from app import sessao


def test_sessao_ida_e_volta():
    assert sessao.ler(sessao.criar("u1", "a@b.c", "Ana")) == {"uid": "u1", "email": "a@b.c", "nome": "Ana"}


def test_sessao_adulterada_ou_vazia():
    t = sessao.criar("u1", "a@b.c", "Ana")
    assert sessao.ler(t[:-2] + "xx") is None
    assert sessao.ler(None) is None and sessao.ler("lixo") is None


def test_sessao_expirada(monkeypatch):
    t = sessao.criar("u1", "a@b.c", "Ana")
    agora = time.time()
    monkeypatch.setattr(sessao.time, "time", lambda: agora + sessao.VALIDADE + 1)
    assert sessao.ler(t) is None


def test_sessao_com_outra_chave_nao_vale(monkeypatch):
    t = sessao.criar("u1", "a@b.c", "Ana")
    monkeypatch.setenv("SECRET_KEY", "outra")
    assert sessao.ler(t) is None
