# Contas por pessoa + Ponto com um toque — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o Chronos (hoje uma conta única com senha no `.env`) em um app com contas por pessoa (Supabase Auth + convite) e uma tela inicial de ponto com botões Entrei / Pausa / Voltei / Saí.

**Architecture:** O servidor continua falando com o Supabase via REST com a chave `service_role`. Toda leitura/escrita de dados passa por um `Repo` amarrado ao `user_id` da sessão (nenhuma rota chama `db` direto). O login usa a API de Auth do Supabase; depois de validar, o servidor emite o próprio cookie assinado com `uid/email/nome`. A lógica do ponto (estados, pausa, turno noturno, esquecimento) é pura em `app/ponto.py`, testável sem banco.

**Tech Stack:** Python 3.12, FastAPI 0.162, Jinja2, httpx, Supabase (PostgREST + GoTrue), Tailwind 3 compilado (`npm run build:css`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-06-contas-e-ponto-rapido-design.md`

## Global Constraints

- "Agora" é sempre `America/Sao_Paulo` (`zoneinfo`); nunca `date.today()`/`datetime.now()` sem fuso. Adicionar `tzdata` ao `requirements.txt`.
- Horários continuam como texto `"HH:MM"`; turno pertence ao dia (`data`) do **Entrei**; saída < entrada = passou da meia-noite (regra já existente em `calculo.calcular_registro`).
- Turno aberto há **mais de 20h** = esquecido. Plantões ≥ 24h não são suportados.
- Um registro por pessoa por dia: unicidade `(user_id, data)`.
- Registros abertos (`saida` nula) **não entram** em nenhum cálculo (banco, dashboard, calendário).
- Cadastro só com `CODIGO_CONVITE` (comparação `hmac.compare_digest`); se a variável estiver vazia, o cadastro fica **desligado**.
- Nenhuma rota usa `db` diretamente — só via `Repo` (exceto Auth).
- Textos da interface em português, no tom atual do app. Seguir marca Chronos e modo claro/escuro existentes; mobile-first.
- **Desvio consciente do spec (simplificação, decisão do Claude):** o cadastro usa a API admin do Supabase (`POST /auth/v1/admin/users` com `email_confirm: true`) com a `service_role`, então **não** é preciso `SUPABASE_ANON_KEY` nem desligar a confirmação de e-mail. Variáveis finais: `SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `CODIGO_CONVITE`, `APP_URL` (opcional, base dos links de e-mail). Remove `ADMIN_PASSWORD` e `USER_NAME`.

## Review Focus

1. **Turno noturno:** Entrei 22:00 de 10/11, agora 00:30 de 11/11 → estado "trabalhando" (sem aviso de esquecimento); Saí 06:00 → registro com `data=2026-11-10`, 8h de duração. (teste na Task 5)
2. **Toque duplo / reenvio do formulário:** dois POST `/ponto/entrei` seguidos → um só registro, segunda vez redireciona com aviso, sem erro 500; mesmo para `/ponto/sai`. (teste na Task 6)
3. **Saí durante a pausa:** pausa aberta 12:00, Saí 12:30 → pausa fechada às 12:30 somada em `pausa_min`, `pausa_inicio` nulo. (teste na Task 5)
4. **ID de outra conta na URL:** pessoa B faz GET/POST em `/registros/{id da A}`, `/registros/{id}/excluir`, `/compensacoes/{id}/excluir`, `/feriados/{id}/excluir` → "não encontrado", nada da A muda. (teste na Task 3)
5. **Servidor em UTC:** relógio do servidor 01:00 UTC de 11/11 = 22:00 de 10/11 em SP → Entrei grava `data=2026-11-10`, `entrada="22:00"`. (teste na Task 6, injetando o relógio)

---

## File Structure

- Create `app/web.py` — `templates`, `render()`, `redir()`, `msg_de_erro()` saem de `main.py` (para os routers usarem sem import circular).
- Create `app/repo.py` — `Repo`: acesso a dados filtrado por `user_id`.
- Create `app/sessao.py` — cookie assinado (substitui `app/auth.py`, que é apagado).
- Create `app/supabase_auth.py` — chamadas à API de Auth do Supabase.
- Create `app/contas.py` — `FERIADOS_PADRAO`, `preparar_conta_nova(repo)`.
- Create `app/rotas_conta.py` — login, cadastro, esqueci, redefinir, logout.
- Create `app/ponto.py` — lógica pura do ponto + `agora()`.
- Create `app/rotas_ponto.py` — rotas `/ponto/*`.
- Create `app/templates/cadastro.html`, `esqueci.html`, `redefinir.html`, `ponto.html`.
- Modify `app/main.py` — middleware de sessão, rotas existentes usam `Repo`, inclui routers.
- Modify `app/calculo.py` — ignora registros abertos.
- Modify `app/supabase_client.py` — `update`/`delete` já aceitam filtro dict (ok); nada além do necessário.
- Modify `app/templates/base.html`, `login.html`, `static/brand/site.webmanifest`.
- Modify `sql/schema.sql`; Create `sql/migracao_contas.sql`.
- Modify `.env.example`, `render.yaml`, `README.md`, `requirements.txt`; Create `requirements-dev.txt`.
- Tests: `tests/conftest.py` (FakeDB, FakeAuth, client logado), `tests/test_repo.py`, `tests/test_sessao.py`, `tests/test_contas.py`, `tests/test_rotas_dados.py`, `tests/test_calculo.py`, `tests/test_ponto.py`, `tests/test_rotas_ponto.py`.

---

### Task 1: Infra de testes, `web.py` e `Repo`

**Files:**
- Create: `requirements-dev.txt` (`-r requirements.txt`, `pytest`), `tests/__init__.py`, `tests/conftest.py`, `tests/test_repo.py`, `app/web.py`, `app/repo.py`
- Modify: `app/main.py` (importa `render/redir/msg_de_erro/templates` de `app/web.py`; comportamento igual)

**Interfaces:**
- Produces:
  - `tests/conftest.py::FakeDB` — mesma interface pública de `SupabaseDB` (`select(tabela, params=None)`, `insert(tabela, dados, *, upsert=False)`, `update(tabela, filtro, dados)`, `delete(tabela, filtro)`), em memória; entende params PostgREST `eq.`, `gte.`, `lte.`, `is.null`, lista de condições no mesmo campo, `order=campo.asc|desc`, `limit`; gera `id` inteiro incremental; `upsert` respeita as chaves únicas `registros(user_id,data)`, `feriados(user_id,data)`, `configuracoes(user_id,chave)`; insert que viola unicidade sem upsert levanta `RuntimeError("Supabase respondeu 409 ...")`. `update`/`delete` retornam a lista de linhas afetadas.
  - fixture `fake_db` (monkeypatcha `app.repo.db`/onde o `Repo` pega o db).
  - `app/repo.py::Repo(user_id: str, banco=db)` com:
    - `config() -> dict[str, str]` (DEFAULT_CONFIG sobrescrito pelas linhas da pessoa)
    - `salvar_config(valores: dict[str, str]) -> None`
    - `feriados() -> list[dict]` (ordem `data.desc`), `salvar_feriado(data: str, nome: str) -> None`, `excluir_feriado(id: int) -> bool`
    - `registros(mes: str | None = None) -> list[dict]`, `registro(id: int) -> dict | None`, `registro_do_dia(data: str) -> dict | None`, `turno_aberto() -> dict | None` (registro com `saida` nula mais recente)
    - `inserir_registro(dados: dict) -> dict`, `atualizar_registro(id: int, dados: dict) -> bool`, `excluir_registro(id: int) -> bool`
    - `compensacoes(mes: str | None = None) -> list[dict]`, `inserir_compensacao(dados: dict) -> dict`, `excluir_compensacao(id: int) -> bool`
    - Todo insert grava `user_id`; todo select/update/delete filtra `user_id=eq.<uid>`; métodos `bool` retornam `False` quando nada foi afetado (id de outra pessoa).
  - `limites_do_mes(mes)` muda de `main.py` para `app/repo.py`.

- [ ] **Step 1: Instalar pytest** — `.venv/bin/pip install -r requirements-dev.txt`. Esperado: instala sem erro.
- [ ] **Step 2: Escrever testes em `tests/test_repo.py`**

```python
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
```

- [ ] **Step 3: Rodar** `.venv/bin/pytest tests/test_repo.py -v` → FAIL (`Repo` não existe).
- [ ] **Step 4: Implementar `app/web.py`, `app/repo.py`, fixture/FakeDB e ajustar imports de `main.py`.** O `main.py` ainda usa `db` direto nesta task (a troca é na Task 3).
- [ ] **Step 5: Rodar** `.venv/bin/pytest -v` → PASS; `.venv/bin/python -c "import app.main"` sem erro.
- [ ] **Step 6: Commit** — `git commit -m "feat: Repo com dados filtrados por pessoa + base de testes"`

---

### Task 2: Sessão, Supabase Auth, telas de conta e conta nova

**Files:**
- Create: `app/sessao.py`, `app/supabase_auth.py`, `app/contas.py`, `app/rotas_conta.py`, `app/templates/cadastro.html`, `esqueci.html`, `redefinir.html`, `tests/test_sessao.py`, `tests/test_contas.py`
- Modify: `app/main.py` (middleware, inclui router, remove rotas `/login` `/logout` antigas), `app/templates/login.html` (e-mail + senha, links "Criar conta" e "Esqueci minha senha"; remove aviso de senha padrão), `app/web.py` (`render` passa `usuario` = nome da sessão)
- Delete: `app/auth.py`

**Interfaces:**
- Consumes: `Repo` (Task 1), `render`, `redir` (`app/web.py`).
- Produces:
  - `app/sessao.py`: `COOKIE = "sessao"`, `criar(uid: str, email: str, nome: str) -> str` (JSON base64url + HMAC-SHA256 com `SECRET_KEY`, validade 30 dias), `ler(token: str | None) -> dict | None` (`{"uid","email","nome"}`, `None` se ausente/adulterado/expirado). Sem `SECRET_KEY` no ambiente: usa o padrão atual do projeto, mas `ler`/`criar` funcionam.
  - `app/supabase_auth.py`: `class AuthErro(Exception)` (mensagem já em português para a tela); `@dataclass Usuario(id: str, email: str, nome: str)`; `cadastrar(email, senha, nome) -> Usuario` (admin users, `email_confirm: True`, `user_metadata: {"nome": nome}`); `entrar(email, senha) -> Usuario` (`/auth/v1/token?grant_type=password`); `enviar_recuperacao(email, redirect_to) -> None` (`/auth/v1/recover`); `trocar_senha(access_token, nova) -> None` (`PUT /auth/v1/user` com `Authorization: Bearer <access_token>`). Headers `apikey`/`Authorization` com `SUPABASE_KEY` nas demais chamadas. Mensagens: e-mail já cadastrado → "Esse e-mail já tem conta. Tente entrar."; credenciais inválidas → "E-mail ou senha incorretos."; senha curta (< 6) → "A senha precisa ter pelo menos 6 caracteres."
  - `app/contas.py`: `FERIADOS_PADRAO: list[tuple[str, str]]` (exatamente as 17 datas do `sql/schema.sql` atual); `preparar_conta_nova(repo: Repo) -> None` grava `DEFAULT_CONFIG` e os feriados padrão.
  - Middleware: rotas públicas = `/static/*`, `/login`, `/cadastro`, `/esqueci`, `/redefinir-senha`, `/healthz`, `/favicon.ico`. Demais: sem sessão válida → 303 `/login`. Com sessão: `request.state.usuario = dict da sessão` e `request.state.repo = Repo(uid)`.
  - Helper `repo_de(request) -> Repo` em `app/web.py`.
  - Rotas: `GET/POST /login` (campos `email`, `senha`) → sucesso 303 `/ponto` com cookie (`httponly`, `samesite=lax`, `secure` quando `APP_URL` começar com https, 30 dias); `GET/POST /cadastro` (`nome`, `email`, `senha`, `convite`) → valida convite, `cadastrar`, `preparar_conta_nova`, loga e vai a `/ponto`; `GET/POST /esqueci` (`email`) → sempre responde "Se esse e-mail tiver conta, enviamos um link." (`redirect_to = (APP_URL or request.base_url) + "/redefinir-senha"`); `GET /redefinir-senha` → página com JS que lê `access_token` do fragmento `#...` da URL e o põe num campo oculto; `POST /redefinir-senha` (`access_token`, `senha`) → `trocar_senha`, 303 `/login?aviso=Senha trocada! Entre com a nova senha.`; `POST /logout`.
  - Até a Task 6 existir, `/ponto` não existe: nesta task o destino pós-login é `/dashboard`; a Task 6 troca para `/ponto`.

- [ ] **Step 1: Testes** (`tests/test_sessao.py`, `tests/test_contas.py`; FakeAuth no conftest monkeypatcha `app.supabase_auth.cadastrar/entrar`):

```python
def test_sessao_ida_e_volta():
    assert sessao.ler(sessao.criar("u1", "a@b.c", "Ana")) == {"uid": "u1", "email": "a@b.c", "nome": "Ana"}

def test_sessao_adulterada_ou_vazia():
    t = sessao.criar("u1", "a@b.c", "Ana")
    assert sessao.ler(t[:-2] + "xx") is None
    assert sessao.ler(None) is None and sessao.ler("lixo") is None

def test_sem_login_redireciona(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"

def test_cadastro_exige_convite(client, fake_auth, monkeypatch):
    monkeypatch.setenv("CODIGO_CONVITE", "julia2026")
    r = client.post("/cadastro", data={"nome": "Ana", "email": "a@b.c", "senha": "123456", "convite": "errado"}, follow_redirects=False)
    assert "Código de convite inválido" in unquote(r.headers["location"])
    assert fake_auth.usuarios == {}

def test_cadastro_desligado_sem_convite_configurado(client, fake_auth, monkeypatch):
    monkeypatch.delenv("CODIGO_CONVITE", raising=False)
    r = client.post("/cadastro", data={"nome": "Ana", "email": "a@b.c", "senha": "123456", "convite": ""}, follow_redirects=False)
    assert fake_auth.usuarios == {}

def test_cadastro_ok_prepara_conta_e_loga(client, fake_auth, fake_db, monkeypatch):
    monkeypatch.setenv("CODIGO_CONVITE", "julia2026")
    r = client.post("/cadastro", data={"nome": "Ana", "email": "a@b.c", "senha": "123456", "convite": "julia2026"}, follow_redirects=False)
    assert r.status_code == 303 and "sessao" in r.cookies
    uid = fake_auth.usuarios["a@b.c"].id
    assert len(Repo(uid).feriados()) == 17
    assert Repo(uid).config()["jornada_diaria"] == "10:00"

def test_login_errado(client, fake_auth):
    r = client.post("/login", data={"email": "x@y.z", "senha": "nada"}, follow_redirects=False)
    assert "E-mail ou senha incorretos" in unquote(r.headers["location"])
```

- [ ] **Step 2: Rodar** `.venv/bin/pytest tests/test_sessao.py tests/test_contas.py -v` → FAIL.
- [ ] **Step 3: Implementar** os arquivos acima e as 3 telas novas no mesmo visual de `login.html`.
- [ ] **Step 4: Rodar** `.venv/bin/pytest -v` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: cadastro com convite, login por e-mail e recuperação de senha (Supabase Auth)"`

---

### Task 3: Rotas existentes por pessoa + registros abertos no cálculo

**Files:**
- Modify: `app/main.py` (dashboard, registros, compensações, calendário, configurações, feriados usam `repo_de(request)`; remove `carregar_config/carregar_feriados/buscar_*` e todo uso de `db`), `app/calculo.py` (`resumo_banco` pula registro com `saida` vazia; nova `registro_fechado(reg: dict) -> bool`), `app/templates/registro_editar.html` (sem mudança de campos)
- Test: `tests/test_calculo.py`, `tests/test_rotas_dados.py`

**Interfaces:**
- Consumes: `Repo` (Task 1), `repo_de`, fixture de client logado (`client_logado(uid)` no conftest, cria cookie via `sessao.criar`).
- Produces: `calculo.registro_fechado(reg) -> bool`. Dashboard e calendário só calculam registros fechados; um registro aberto aparece na lista do dashboard como "em andamento" (sem total/extra). Rotas de editar/excluir com id que o `Repo` não acha → `redir(erro="Registro não encontrado.")` (idem compensação/feriado).
- `POST /registros` (formulário manual) continua exigindo entrada e saída. Se já existe registro no dia → erro "Já existe um registro em DD/MM/AAAA. Edite o existente." (em vez do 409 cru).

- [ ] **Step 1: Testes**

```python
# tests/test_calculo.py
def test_resumo_ignora_registro_aberto():
    regs = [{"data": "2026-11-04", "entrada": "08:00", "saida": "20:00", "pausa_min": 0},
            {"data": "2026-11-05", "entrada": "08:00", "saida": None, "pausa_min": 0}]
    saldo, _ = calculo.resumo_banco(regs, [], set(), calculo.DEFAULT_CONFIG)
    assert saldo == 120

# tests/test_rotas_dados.py
def test_dashboard_e_calendario_com_turno_aberto(client_logado, fake_db):
    c = client_logado("uid-a")
    Repo("uid-a").inserir_registro({"data": "2026-11-05", "entrada": "08:00", "saida": None, "pausa_min": 0})
    assert c.get("/dashboard?mes=2026-11").status_code == 200
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
```

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.** `date.today()` em `main.py` passa a usar `ponto.agora().date()` — se `app/ponto.py` ainda não existir, criar já aqui só `agora() -> datetime` (`datetime.now(ZoneInfo("America/Sao_Paulo"))`) e adicionar `tzdata` ao `requirements.txt`.
- [ ] **Step 4: Rodar** `.venv/bin/pytest -v` → PASS; `grep -n "db\." app/main.py` → nenhuma linha.
- [ ] **Step 5: Commit** — `git commit -m "feat: dashboard, calendário e configurações por pessoa"`

---

### Task 4: Banco — schema novo e migração da Julia + docs de deploy

**Files:**
- Modify: `sql/schema.sql`, `.env.example`, `render.yaml`, `README.md`
- Create: `sql/migracao_contas.sql`

**Interfaces:**
- Produces (schema final, igual nos dois arquivos):
  - `registros`, `compensacoes`, `feriados`, `configuracoes` com `user_id uuid not null references auth.users(id) on delete cascade`.
  - `registros.saida text null`, nova coluna `registros.pausa_inicio text null`.
  - Unicidades: `registros unique(user_id, data)`, `feriados unique(user_id, data)`, `configuracoes primary key(user_id, chave)`; remover as antigas (`registros.data unique`, `feriados.data unique`, PK `configuracoes(chave)`).
  - Índice `registros(user_id, data)` (vem da unique) e `compensacoes(user_id, data)`.
  - `schema.sql` (instalação nova) **não** semeia configurações/feriados (a app faz isso no cadastro). RLS segue ligado.
- `migracao_contas.sql` — um bloco `do $$ ... $$` idempotente, com uma única linha para editar no topo: `email_julia text := 'COLOQUE-O-EMAIL-DA-JULIA';`. Passos: aborta com `raise exception` se o e-mail não existir em `auth.users`; adiciona colunas nulas; **apaga** `configuracoes`/`feriados` que já tenham `user_id` da Julia (os padrões do cadastro dela); atribui `user_id` da Julia a todas as linhas com `user_id is null` nas 4 tabelas; põe `not null`; troca unicidades; `saida` nullable; `pausa_inicio`.
- README — seção "Atualizando para contas (uma vez)": 1) definir `CODIGO_CONVITE` e `APP_URL` no Render; 2) no Supabase → Authentication → URL Configuration, adicionar `<APP_URL>/redefinir-senha` em Redirect URLs; 3) deploy; 4) Julia cria conta em `/cadastro`; 5) rodar `sql/migracao_contas.sql` com o e-mail dela no SQL Editor; 6) conferir saldo. Avisar que o app fica alguns minutos sem os dados dela entre 3 e 5. Remover menções a senha única/`ADMIN_PASSWORD`/`USER_NAME`.

- [ ] **Step 1: Escrever os SQLs.** Verificação local: se houver `psql`/Postgres disponível, rodar `schema.sql` antigo + dados de exemplo + criar `auth.users` falso + `migracao_contas.sql` duas vezes e conferir contagens; se não houver, registrar no relatório que a verificação é manual no Supabase (passo 6 do README). Não rodar nada no Supabase de produção.
- [ ] **Step 2: Atualizar `.env.example`, `render.yaml` (envVars `CODIGO_CONVITE`, `APP_URL`; remover `ADMIN_PASSWORD`), README.**
- [ ] **Step 3: Rodar** `.venv/bin/pytest -v` → PASS (nada de Python mudou).
- [ ] **Step 4: Commit** — `git commit -m "feat: schema com dono por registro e migração dos dados existentes"`

---

### Task 5: Lógica do ponto (`app/ponto.py`)

**Files:**
- Create/Modify: `app/ponto.py`, `tests/test_ponto.py`

**Interfaces:**
- Consumes: `calculo.parse_hhmm`, `calculo.hhmm`.
- Produces (tudo puro; `agora` é sempre `datetime` com fuso SP; registros são dicts do `Repo`):
  - `FUSO = ZoneInfo("America/Sao_Paulo")`, `LIMITE_ESQUECIDO_MIN = 20 * 60`, `agora() -> datetime`.
  - `inicio_do_turno(reg) -> datetime` (data + entrada, fuso SP).
  - `estado(turno_aberto: dict | None, agora: datetime) -> Literal["livre", "trabalhando", "pausa", "esquecido"]` — esquecido quando `agora - inicio > 20h` (independe de pausa).
  - `minutos_trabalhados(turno: dict, agora: datetime) -> int` — de entrada até agora, menos `pausa_min` e menos a pausa em andamento.
  - Ações retornam o dict de **campos a gravar** (o chamador faz `inserir`/`atualizar`): `acao_entrei(agora) -> dict` (`data`, `entrada`, `saida: None`, `pausa_min: 0`, `pausa_inicio: None`); `acao_pausa(turno, agora) -> dict`; `acao_voltei(turno, agora) -> dict` (soma a diferença em `pausa_min`, +1440 se negativa, limpa `pausa_inicio`); `acao_sai(turno, hora: str) -> dict` (se `pausa_inicio`, fecha a pausa em `hora` antes); `acao_desfazer_saida() -> dict` (`{"saida": None}`).
  - `class PontoErro(ValueError)` para ação inválida no estado atual (ex.: pausa estando em pausa; saída esquecida que resulta em duração ≤ 0 após pausas).
  - Horas gravadas sempre `agora.strftime("%H:%M")`.

- [ ] **Step 1: Testes** (`sp(…)` = helper que monta `datetime` em SP)

```python
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

def test_varias_pausas_somam():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_pausa(t, sp(2026, 11, 10, 10, 0)); t |= acao_voltei(t, sp(2026, 11, 10, 10, 15))
    t |= acao_pausa(t, sp(2026, 11, 10, 12, 0)); t |= acao_voltei(t, sp(2026, 11, 10, 13, 0))
    assert t["pausa_min"] == 75 and t["pausa_inicio"] is None
    assert minutos_trabalhados(t, sp(2026, 11, 10, 14, 0)) == 6 * 60 - 75

def test_sai_durante_pausa_fecha_pausa():
    t = acao_entrei(sp(2026, 11, 10, 8, 0))
    t |= acao_pausa(t, sp(2026, 11, 10, 12, 0))
    assert estado(t, sp(2026, 11, 10, 12, 10)) == "pausa"
    t |= acao_sai(t, "12:30")
    assert t["saida"] == "12:30" and t["pausa_min"] == 30 and t["pausa_inicio"] is None

def test_pausa_atravessando_meia_noite():
    t = acao_entrei(sp(2026, 11, 10, 22, 0))
    t |= acao_pausa(t, sp(2026, 11, 10, 23, 50)); t |= acao_voltei(t, sp(2026, 11, 11, 0, 20))
    assert t["pausa_min"] == 30

def test_sem_pausa_vira_extra():
    t = acao_entrei(sp(2026, 11, 4, 8, 0)); t |= acao_sai(t, "20:00")  # quarta, jornada 10h
    assert calculo.calcular_registro(t, set(), calculo.DEFAULT_CONFIG)["extras_min"] == 120

def test_acao_invalida():
    t = acao_entrei(sp(2026, 11, 10, 8, 0)); t |= acao_pausa(t, sp(2026, 11, 10, 9, 0))
    with pytest.raises(PontoErro): acao_pausa(t, sp(2026, 11, 10, 9, 5))
    t2 = acao_entrei(sp(2026, 11, 10, 8, 0))
    with pytest.raises(PontoErro): acao_voltei(t2, sp(2026, 11, 10, 9, 0))
```

- [ ] **Step 2: Rodar** `.venv/bin/pytest tests/test_ponto.py -v` → FAIL.
- [ ] **Step 3: Implementar** `app/ponto.py`.
- [ ] **Step 4: Rodar** `.venv/bin/pytest -v` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: lógica do ponto com pausas, turno noturno e esquecimento"`

---

### Task 6: Tela de ponto, rotas e navegação

**Files:**
- Create: `app/rotas_ponto.py`, `app/templates/ponto.html`, `tests/test_rotas_ponto.py`
- Modify: `app/main.py` (inclui router; `GET /` → `/ponto`; pós-login/cadastro → `/ponto`), `app/rotas_conta.py` (destino `/ponto`), `app/templates/base.html` (Ponto como 1º item na barra inferior mobile e no menu desktop), `static/brand/site.webmanifest` (`"start_url": "/ponto"`, `"scope": "/"`), `static/css/app.css` (rebuild via `npm run build:css`)

**Interfaces:**
- Consumes: `Repo` (`turno_aberto`, `registro_do_dia`, `inserir_registro`, `atualizar_registro`, `registros`, `compensacoes`, `feriados`, `config`), `ponto.*` (Task 5), `calculo.resumo_banco`, `calculo.calcular_registro`.
- Relógio injetável: `rotas_ponto` chama `ponto.agora()` via módulo (testes fazem `monkeypatch.setattr(ponto, "agora", lambda: ...)`). Nova fixture em `tests/conftest.py`: `relogio(ano, mes, dia, hora, minuto)` — fixa `ponto.agora()` nesse instante em SP.
- Rotas (todas POST redirecionam 303 para `/ponto`, com `aviso`/`erro`):
  - `GET /ponto` — mostra saldo do banco (`resumo_banco` com tudo) e, conforme `estado`:
    - `livre` sem registro hoje → botão **Entrei**;
    - `livre` com registro fechado hoje → resumo do dia (horário, pausa, total, extra) + "Desfazer saída" (form discreto, com `confirm`);
    - `trabalhando` → "Trabalhando há Xh YY (entrou às HH:MM)" com contador ao vivo em JS + **Pausa** + **Saí**;
    - `pausa` → "Em pausa desde HH:MM" + **Voltei** (+ **Saí** menor);
    - `esquecido` → "Você não marcou a saída de DD/MM. Que horas saiu?" campo `time` + Salvar; nenhum outro botão.
    - Link "lançar/corrigir manualmente" → `/dashboard`.
  - `POST /ponto/entrei` — se há turno aberto ou registro hoje: não faz nada, `aviso` "Você já marcou a entrada." Senão insere `acao_entrei`.
  - `POST /ponto/pausa`, `/ponto/voltei` — aplica a ação no turno aberto; estado errado (`PontoErro` ou sem turno) → redireciona com aviso amigável, sem 500.
  - `POST /ponto/sai` — fecha com hora atual; sem turno aberto → aviso "Nenhum turno aberto."; sucesso → `aviso` = `"Dia fechado: +HH:MM de extra · saldo +HH:MM"` (sinal conforme valor; `hhmm` do cálculo).
  - `POST /ponto/esquecido` (`saida: "HH:MM"`) — só vale se o estado for `esquecido`; fecha com `acao_sai(turno, saida)`; duração ≤ 0 → erro "Esse horário de saída não fecha com a entrada.".
  - `POST /ponto/desfazer` — só para o registro fechado de hoje (data = hoje SP) **ou** o último registro fechado se ele foi o último turno; aplica `acao_desfazer_saida`.
- Botões: grandes (área de toque ≥ 64px de altura), largura total no mobile; JS desabilita o botão ao enviar (anti toque duplo).

- [ ] **Step 1: Testes**

```python
def test_entrei_duas_vezes_um_registro(client_logado, fake_db, relogio):
    relogio(2026, 11, 10, 8, 0)
    c = client_logado("uid-a")
    c.post("/ponto/entrei"); r = c.post("/ponto/entrei", follow_redirects=False)
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
    assert c.post("/ponto/sai", follow_redirects=False).status_code == 303  # reenvio não quebra

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
```

- [ ] **Step 2: Rodar** `.venv/bin/pytest tests/test_rotas_ponto.py -v` → FAIL.
- [ ] **Step 3: Implementar** rotas, template, navegação e manifesto; `npm run build:css` (classes novas do Tailwind).
- [ ] **Step 4: Rodar** `.venv/bin/pytest -v` → PASS.
- [ ] **Step 5: Verificação visual** — subir `uvicorn app.main:app` com FakeDB/variáveis de teste ou com o Supabase de desenvolvimento, se o usuário fornecer; abrir `/ponto` em largura de 390px nos modos claro e escuro e percorrer Entrei → Pausa → Voltei → Saí. Registrar screenshots/observações no relatório.
- [ ] **Step 6: Commit** — `git commit -m "feat: tela de ponto com um toque como inicial do app"`

---

## Fora deste plano (fazer com o usuário)

Deploy e migração em produção (README, Task 4): configurar variáveis no Render, Redirect URL no Supabase, cadastro da Julia, rodar `sql/migracao_contas.sql`. São ações em serviços externos com os dados reais dela — o executor **não** faz isso sozinho; entrega o passo a passo e acompanha.
