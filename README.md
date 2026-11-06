# 🕰️ Chronos
<p align="center">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white">
  <img alt="Supabase" src="https://img.shields.io/badge/Supabase-3FCF8E?style=flat&logo=supabase&logoColor=white">
  <img alt="Tailwind CSS" src="https://img.shields.io/badge/Tailwind-38BDF8?style=flat&logo=tailwindcss&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-blue">
</p>

Sistema web (FastAPI + Supabase) da marca **Chronos** para registrar a jornada de trabalho, contar
horas extras automaticamente e manter um **banco de horas** com folgas.

## Como funciona

- **Registro de ponto**: informa data, entrada, saída e pausa → o sistema calcula
  as horas extras na hora e joga no banco.
  - Dia útil: tudo acima da **jornada base** (padrão 10h, configurável) vira extra.
  - **Fim de semana / feriado**: *todas* as horas contam como extra em **dobro**,
    e o dia ainda gera **+1 folga** (opcional/configurável).
  - Saída depois da meia-noite é entendida automaticamente.
- **Banco de horas**: saldo = extras − compensações/abonos, mostrado ao vivo.
- **Compensação**: desconta a jornada base do saldo (dia compensado).
  **Abono**: desconta os minutos que você digitar.
  **Folga**: consome 1 crédito de folga.
- Tudo fica no **Supabase** (PostgreSQL) e cada pessoa tem a própria conta (e-mail e senha) e só vê os próprios dados.

## Deploy online (Render)

O projeto já tem a receita pronta (`render.yaml`):

1. Crie conta em [render.com](https://render.com) usando **Sign in with GitHub**
2. Painel → **New +** → **Blueprint** → autorize e escolha o repositório `sistema-escala`
3. O Render lê o `render.yaml` e pede as **variáveis** (logo abaixo) — preencha com os mesmos valores do seu `.env`:
   - `SECRET_KEY` · `SUPABASE_URL` · `SUPABASE_KEY` · `CODIGO_CONVITE` · `APP_URL` (opcional)
4. **Apply** e aguarde o build (~1–2 min). O app fica em `https://sistema-escala-xxxx.onrender.com`

> 💡 No plano grátis o app "dorme" após ~15 min sem uso; o primeiro acesso depois disso demora ~30–50 s para acordar.

## Sua escala em ciclo (ex.: 4x2)

Trabalha 4 dias seguidos e descansa 2, girando a semana toda? Em **Configurações
→ Minha escala (ciclo)**:

1. Marque **"Ciclo de escala ativo"**
2. **Dias trabalhando**: 4 · **Dias de descanso**: 2
3. **1º dia trabalhado de um ciclo**: escolha um dia em que você *começou* um
   bloco de trabalho (ex.: a última segunda em que voltou de folga)
4. Salve — o sistema repete o padrão para frente **e para trás** no tempo

O que muda no cálculo:

| Dia | Como conta |
|---|---|
| Dia de escala (comum) | Jornada base + extras acima dela |
| Fim de semana **dentro** do ciclo | Dia normal (por padrão há um interruptor "dobrar fds" se quiser) |
| **Feriado** (qualquer dia) | Dobro + 1 folga |
| Trabalhou no **dia de descanso** | Tudo vira extra (fator especial) |

No **Calendário** aparecem os dias de descanso e um aviso "sem ponto" em dias
de escala que faltem lançamento.

## Passo 1 — criar o projeto no Supabase

1. Acesse [supabase.com](https://supabase.com) e crie um projeto (é grátis).
2. Na esquerda: **SQL Editor** → **New query** → cole todo o conteúdo de
   `sql/schema.sql` → **Run**. Isso cria as 4 tabelas (configurações e feriados padrão são criados pelo app no cadastro de cada pessoa).
3. Vá em **Project Settings → API** e copie:
   - **Project URL** → será a `SUPABASE_URL`
   - **service_role** (secret) → será a `SUPABASE_KEY`
   > Use sempre a chave `service_role`, nunca a `anon key`.

## Passo 2 — configurar o sistema

```bash
# dentro da pasta do projeto
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # Windows: copy .env.example .env
```

Edite o `.env`:

```env
CODIGO_CONVITE=seu-codigo-de-convite
SECRET_KEY=um-texto-aleatorio-qualquer
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_KEY=SUA-CHAVE-SERVICE_ROLE
```

## Passo 3 — rodar

```bash
uvicorn app.main:app --reload --port 8000
```

Abra <http://localhost:8000>, crie sua conta em `/cadastro` (com o código de convite) e pronto. 🎉

## Atualizando para contas (uma vez)

Quem já usava a versão de senha única (a Julia) precisa migrar os dados para a
conta dela. Faça nesta ordem:

1. No Render, defina `CODIGO_CONVITE` e `APP_URL` (o endereço do app, ex.:
   `https://sistema-escala-xxxx.onrender.com`).
2. No Supabase → **Authentication → URL Configuration → Redirect URLs**, adicione
   `<APP_URL>/redefinir-senha`. Essa lista é o que protege o link de recuperar senha.
3. Faça o deploy da nova versão.
4. A Julia cria a conta em `/cadastro` (com o código de convite).
5. No Supabase → **SQL Editor**, cole `sql/migracao_contas.sql`, troque
   `COLOQUE-O-EMAIL-DA-JULIA` pelo e-mail dela e rode. Pode rodar de novo sem
   problema (nada muda na segunda vez). Se o e-mail não existir, aborta sem alterar nada.
6. Confira o saldo do banco de horas e o calendário: devem estar iguais aos de antes.

> ⚠️ Entre o passo 3 e o 5 o app fica **sem os dados dela** (a conta nova ainda
> está vazia e o banco ainda está no formato antigo); faça os dois passos em
> poucos minutos. Nesse intervalo o cadastro pode avisar que não conseguiu
> preparar a conta: é esperado, a migração do passo 5 resolve.

## Ajustando as regras (página "Configurações")

| Configuração | Padrão | O que faz |
|---|---|---|
| Jornada base/dia | 10:00 | O que passer disso é hora extra em dia útil |
| Fator dia útil | 1 | Multiplicador do excedente (2 = dobrado) |
| Fator fds/feriado | 2 | Multiplicador de TODAS as horas do dia (dobro) |
| Folga fds/feriado | sim | Trabalhar nesses dias gera +1 folga |

Cada conta nova já começa com o calendário nacional 2027 (e o fim de 2026) —
adicione/remova livremente na mesma página.

> ⏳ As regras de folga/feriado que você disse que ainda vai **confirmar**
> são justamente os "fatores" e o "gera folga" — é só ajustar ali, sem mexer em código.

## Estrutura

```
escala-julia/
├── app/
│   ├── main.py              # rotas (dashboard, registros, compensações, config)
│   ├── auth.py              # contas (Supabase Auth): cadastro, login, recuperar senha
│   ├── calculo.py           # regras de horas extras e banco de horas
│   ├── supabase_client.py   # acesso ao Supabase via REST
│   └── templates/           # páginas HTML
├── static/css/style.css
├── sql/schema.sql           # instalação nova: rode no SQL Editor do Supabase
├── sql/migracao_contas.sql  # só para quem já usava a versão de senha única
├── .env.example
└── requirements.txt
```
