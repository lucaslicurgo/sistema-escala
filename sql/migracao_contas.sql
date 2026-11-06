-- ============================================================
-- Migração para contas por pessoa (rodar UMA vez, no SQL Editor
-- do Supabase, DEPOIS que a Julia criar a conta em /cadastro).
--
-- Edite só a linha "email_julia" logo abaixo.
-- É seguro rodar de novo: a segunda execução não muda nada.
-- Tudo roda numa transação só: se algo falhar, nada é alterado.
-- ============================================================
do $$
declare
  email_julia text := 'COLOQUE-O-EMAIL-DA-JULIA';  -- <- ÚNICA linha para editar
  uid uuid;
  t text;
  r record;
  tem_orfas boolean;
begin
  select id into uid from auth.users where lower(email) = lower(trim(email_julia));
  if uid is null then
    raise exception 'E-mail % não encontrado em auth.users. A Julia já criou a conta em /cadastro? Nada foi alterado.', email_julia;
  end if;

  -- 1) colunas novas (nulas por enquanto)
  alter table registros     add column if not exists user_id uuid references auth.users(id) on delete cascade;
  alter table compensacoes  add column if not exists user_id uuid references auth.users(id) on delete cascade;
  alter table feriados      add column if not exists user_id uuid references auth.users(id) on delete cascade;
  alter table configuracoes add column if not exists user_id uuid references auth.users(id) on delete cascade;
  alter table registros     add column if not exists pausa_inicio text;

  -- 2) Padrões criados no cadastro da Julia: só são apagados se os dados
  --    antigos (sem dono) ainda existem, ou seja, na primeira execução.
  --    Depois de migrado, as linhas dela SÃO os dados reais e ficam intactas.
  foreach t in array array['configuracoes', 'feriados'] loop
    execute format('select exists (select 1 from %I where user_id is null)', t) into tem_orfas;
    if tem_orfas then
      execute format('delete from %I where user_id = $1', t) using uid;
    end if;
  end loop;

  -- 3) dono = Julia em tudo que ainda não tem dono
  update registros     set user_id = uid where user_id is null;
  update compensacoes  set user_id = uid where user_id is null;
  update feriados      set user_id = uid where user_id is null;
  update configuracoes set user_id = uid where user_id is null;

  -- 4) not null
  alter table registros     alter column user_id set not null;
  alter table compensacoes  alter column user_id set not null;
  alter table feriados      alter column user_id set not null;
  alter table configuracoes alter column user_id set not null;

  -- 5) unicidades: remove as antigas (só de "data" / só de "chave") e cria as novas
  for r in
    select c.conrelid::regclass::text as tabela, c.conname
    from pg_constraint c
    where c.contype in ('u', 'p')
      and c.conrelid in ('registros'::regclass, 'feriados'::regclass, 'configuracoes'::regclass)
      and array_length(c.conkey, 1) = 1
      and (select a.attname from pg_attribute a
           where a.attrelid = c.conrelid and a.attnum = c.conkey[1]) in ('data', 'chave')
  loop
    execute format('alter table %s drop constraint %I', r.tabela, r.conname);
  end loop;

  if not exists (select 1 from pg_constraint where conname = 'registros_user_data_key') then
    alter table registros add constraint registros_user_data_key unique (user_id, data);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'feriados_user_data_key') then
    alter table feriados add constraint feriados_user_data_key unique (user_id, data);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'configuracoes_pkey' and contype = 'p') then
    alter table configuracoes add constraint configuracoes_pkey primary key (user_id, chave);
  end if;

  create index if not exists compensacoes_user_data_idx on compensacoes (user_id, data);

  -- 6) a saída passa a ser opcional (ponto rápido: entrada agora, saída depois)
  alter table registros alter column saida drop not null;

  raise notice 'Migração concluída para % (%).', email_julia, uid;
end $$;
