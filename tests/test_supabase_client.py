import httpx

from app.supabase_client import SupabaseDB


def _db(monkeypatch, vistos):
    monkeypatch.setenv("SUPABASE_URL", "http://sb.test")
    monkeypatch.setenv("SUPABASE_KEY", "k")

    def handler(req: httpx.Request) -> httpx.Response:
        vistos.append(req)
        return httpx.Response(201, json=[{"id": 1}])

    banco = SupabaseDB()
    banco._cliente = httpx.Client(transport=httpx.MockTransport(handler))
    return banco


def test_insert_upsert_envia_on_conflict(monkeypatch):
    vistos = []
    _db(monkeypatch, vistos).insert(
        "feriados", {"data": "2026-12-25"}, upsert=True, on_conflict="user_id,data"
    )
    req = vistos[0]
    assert req.url.params["on_conflict"] == "user_id,data"
    assert "resolution=merge-duplicates" in req.headers["Prefer"]


def test_insert_sem_on_conflict_nao_envia_param(monkeypatch):
    vistos = []
    _db(monkeypatch, vistos).insert("registros", {"data": "2026-12-25"})
    assert "on_conflict" not in vistos[0].url.params
