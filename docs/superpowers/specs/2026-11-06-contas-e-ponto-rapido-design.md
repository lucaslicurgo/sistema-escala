# Chronos — Contas por pessoa + Ponto com um toque (design)

Data: 2026-11-06 · Status: aguardando aprovação

## Intenção (o porquê)

O Chronos foi feito para a Julia controlar o próprio banco de horas. Dois incômodos/desejos:

1. **No celular é chato de usar.** Hoje ela preenche um formulário (data, entrada, saída,
   pausa em minutos). Ela quer **um botão para quando entra e outro para quando sai**.
2. **As amigas da Julia querem usar também.** O sistema hoje é de uma pessoa só (senha única
   no `.env`). Cada amiga precisa da própria conta, com os próprios dados.

É gratuito e para um grupo pequeno de amigas. "Vender" fica para o futuro — o modelo de
contas deve permitir isso depois, mas não fazemos cobrança agora.

## Objetivos

- Cadastro com e-mail + senha, login, logout e "esqueci minha senha".
- Cadastro só com **código de convite** (uma palavra definida no ambiente) para que um
  desconhecido com o link não crie conta.
- Cada conta tem **seus próprios** registros, compensações, configurações (jornada, fatores,
  ciclo) e feriados. Ninguém vê dados de outra pessoa.
- Os dados atuais da Julia passam a pertencer à conta dela.
- Tela inicial no celular = **bater ponto com botões**:
  - **Entrei** → grava o horário atual; aparecem **Pausa** e **Saí**.
  - **Pausa** → **Voltei**: pode repetir no dia; as pausas são somadas.
  - **Saí** → fecha o dia e mostra o resultado na hora ("hoje: +1h20 de extra", saldo novo).
  - Topo mostra sempre o saldo do banco e o tempo trabalhado hoje (contador ao vivo).
- A pausa é a **real**: se ela não tocar em Pausa (pulou o almoço), a pausa é 0 e esse tempo
  vira extra pelas regras atuais.
- **Esquecimento:** ao abrir o app com um dia anterior ainda sem saída, aparece
  "Você não marcou a saída de <dia>. Que horas saiu?" antes de liberar os botões.
  Se havia pausa aberta nesse dia, ela é fechada junto (pergunta-se a hora da volta ou
  considera-se encerrada na saída — decisão do builder, desde que fique visível).
- **Turno que vira a meia-noite** (decisão do Claude — o cálculo já suporta): o turno pertence
  ao dia do **Entrei**. A tela de ponto mostra o turno aberto mais recente, não "o registro de
  hoje". O aviso de saída esquecida só aparece quando um turno está aberto há **mais de 20h**
  (ou se ela tentar tocar Entrei com outro turno aberto). Plantões de 24h ou mais **não** são
  suportados (o formato HH:MM sem data continua).
- **Reabrir** um dia fechado = apenas desfazer um "Saí" tocado por engano (limpa a saída).
  Saiu e voltou de verdade → usa Pausa/Voltei.
- O formulário completo continua existindo numa tela secundária, para corrigir/lançar
  dias passados e editar qualquer registro.

## Não-objetivos

- Cobrança/pagamento, planos.
- Papel de gestor/equipe, ver dados de outras pessoas.
- Notificações push / lembretes.
- Funcionar offline.
- Login com Google/redes sociais.

## Anti-objetivos (seria fracasso mesmo funcionando)

- Bater ponto exigir mais que um toque + abrir o app no caso normal.
- Qualquer vazamento de dados entre contas (uma consulta sem filtro de dono).
- A Julia perder ou ter alterado algum dado/cálculo histórico na migração.
- Horário gravado errado por fuso (servidor no Render roda em UTC).

## Restrições

- Stack atual se mantém: FastAPI + Jinja + Tailwind compilado localmente + Supabase via REST
  com chave `service_role` (`app/supabase_client.py`). Deploy no Render free (`render.yaml`).
- Regras de cálculo em `app/calculo.py` não mudam; passam a receber config/feriados da pessoa.
- **Fuso:** "agora" é sempre `America/Sao_Paulo` (por ora fixo para todas as contas).
- Supabase free: o envio de e-mail padrão do Supabase Auth tem limite baixo (poucos e-mails
  por hora). Por isso: **desligar a confirmação de e-mail** no cadastro (o convite já filtra);
  e-mail só é usado no "esqueci minha senha".
- Mobile-first; o app já tem manifesto PWA (`display: standalone`) — deve continuar abrindo
  como app pelo ícone da tela inicial e cair direto na tela de ponto se logada.

## Abordagens consideradas (para login)

1. **Supabase Auth (escolhida — decisão do Claude).** Já está no projeto Supabase; dá
   cadastro, senha com hash seguro e recuperação por e-mail sem código extra. O servidor
   chama a API de Auth (`/auth/v1/signup`, `/auth/v1/token?grant_type=password`,
   `/auth/v1/recover`) e, após validar, emite o próprio cookie de sessão assinado contendo o
   `user_id` (mesmo padrão do cookie atual, 30 dias).
2. Login próprio (tabela de usuários + bcrypt). Descartada: teria que montar envio de e-mail
   para recuperar senha.
3. Entrar com Google. Descartada: mais configuração (OAuth) sem ganho real para um grupo de
   amigas.

Isolamento dos dados: o servidor continua usando a `service_role` e **toda** leitura/escrita
filtra por `user_id` da sessão (camada única no `supabase_client`/helpers, para não depender
de lembrar em cada rota). RLS continua ligado bloqueando acesso anônimo.

## Modelo de dados (mudanças)

- `registros`, `compensacoes`, `feriados`, `configuracoes` ganham `user_id uuid not null`
  (referência a `auth.users`).
- Unicidades passam a ser por pessoa: `registros (user_id, data)`, `feriados (user_id, data)`,
  `configuracoes (user_id, chave)` (vira a PK).
- `registros.saida` passa a aceitar nulo (dia "aberto"). Novo campo `pausa_inicio` (texto
  "HH:MM", nulo) para a pausa em andamento; ao tocar **Voltei** soma-se a diferença em
  `pausa_min` e limpa `pausa_inicio`.
- Registros abertos (sem saída) **não entram** no cálculo do banco até serem fechados.
- Ao criar conta: grava as configurações padrão (`DEFAULT_CONFIG`) e copia o calendário de
  feriados nacionais padrão (os do `sql/schema.sql`) para a pessoa — cada uma ajusta os seus.
- Script de migração (SQL) para quem já tem banco: adiciona colunas/índices e atribui todas as
  linhas existentes ao `user_id` da Julia (passo manual: ela se cadastra primeiro, depois roda
  o script com o id dela). Sem perder nada. **Os dados atuais dela prevalecem:** as
  configurações/feriados padrão criados no cadastro dela são apagados antes da atribuição.
  A troca é feita de uma vez, com alguns minutos fora do ar (aceitável para o grupo).

## Telas

- **Login / Cadastro / Esqueci a senha** (cadastro pede nome, e-mail, senha, código de convite).
- **Ponto (nova tela inicial)** — botões grandes conforme estado do dia:
  sem registro → [Entrei]; trabalhando → [Pausa] [Saí]; em pausa → [Voltei]; fechado →
  resumo do dia (e possibilidade de reabrir/editar). Link "lançar/corrigir manualmente".
- Dashboard, Calendário e Configurações continuam, filtrados pela conta.
- Navegação inferior mobile: Ponto vira o primeiro item.

```
┌─────────────────────────┐
│  Chronos      Saldo +12h│
│   Trabalhando há 3h42   │
│   (entrou às 08:03)     │
│   ┌─────────────────┐   │
│   │      PAUSA      │   │
│   └─────────────────┘   │
│   ┌─────────────────┐   │
│   │       SAÍ       │   │
│   └─────────────────┘   │
│  lançar/corrigir ›      │
└─────────────────────────┘
```

## Variáveis de ambiente

- Remove `ADMIN_PASSWORD`. Adiciona `CODIGO_CONVITE` e `SUPABASE_ANON_KEY` (chamadas de Auth).
- Mantém `SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` (service_role). Atualizar `.env.example`,
  `render.yaml` e README.

## Deixado para o builder

- Detalhes visuais da tela de ponto (seguir a marca Chronos e o modo claro/escuro existentes).
- Proteção contra toque duplo (ex.: dois "Entrei" seguidos) e mensagens de erro.
- Como tratar pausa aberta ao fechar um dia esquecido.
- Como o link de "esqueci minha senha" volta para o app; onde guardar o nome da pessoa.
- Ordem de entrega (sugestão: contas + isolamento + migração primeiro, depois a tela de ponto).
- Testes: o cálculo (`calculo.py`) e o isolamento por `user_id` merecem testes automatizados.
