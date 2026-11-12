-- VF Emissor: Auth autentica; estas funções autorizam. Nunca confiar em user_metadata.
begin;
create table public.vf_admins (user_id uuid primary key references auth.users(id));
create table public.vf_accounts (
 id uuid primary key references auth.users(id), name text not null default '',
 status text not null default 'pending' check(status in ('pending','approved','rejected','suspended')),
 revision integer not null default 1, created_at timestamptz not null default now()
);
create table public.vf_licenses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null references public.vf_accounts(id),
 cnpj text not null check(cnpj ~ '^[0-9]{14}$'), name text not null check(length(name) between 2 and 200),
 status text not null default 'pending' check(status in ('pending','approved','rejected','suspended')),
 valid_until date, max_devices integer not null default 2 check(max_devices between 1 and 50),
 ever_approved boolean not null default false, revision integer not null default 1,
 created_at timestamptz not null default now(), unique(owner_id,cnpj)
);
create index vf_licenses_owner on public.vf_licenses(owner_id);
create table public.vf_devices (
 id uuid primary key default gen_random_uuid(), license_id uuid not null references public.vf_licenses(id),
 installation_id uuid not null, label text not null, revoked boolean not null default false,
 last_seen timestamptz not null default now(), unique(license_id,installation_id)
);
create table public.vf_audit (
 id bigint generated always as identity primary key, actor uuid not null references auth.users(id),
 operation_id uuid not null, action text not null, target uuid not null,
 result jsonb not null, memo text not null default '', created_at timestamptz not null default now(),
 unique(actor,operation_id)
);
alter table public.vf_admins enable row level security;
alter table public.vf_accounts enable row level security;
alter table public.vf_licenses enable row level security;
alter table public.vf_devices enable row level security;
alter table public.vf_audit enable row level security;
-- Sem acesso direto: toda leitura/escrita passa pelas RPCs com autorização explícita.
revoke all on public.vf_admins,public.vf_accounts,public.vf_licenses,public.vf_devices,public.vf_audit from anon,authenticated;

create function public.vf_is_admin() returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.vf_admins where user_id=auth.uid());
$$;
create function public.vf_on_signup() returns trigger language plpgsql security definer set search_path='' as $$
begin
 insert into public.vf_accounts(id,name) values(new.id,left(coalesce(new.raw_user_meta_data->>'name',''),200));
 return new;
end; $$;
create trigger vf_signup after insert on auth.users for each row execute function public.vf_on_signup();
-- Contas existentes começam pendentes; a primeira administradora é definida fora da aplicação.
insert into public.vf_accounts(id,name) select id,left(coalesce(raw_user_meta_data->>'name',''),200) from auth.users on conflict do nothing;

create function public.vf_client_state() returns jsonb language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
 if auth.uid() is null then raise exception 'Entre na sua conta.'; end if;
 select jsonb_build_object('id',a.id,'name',a.name,'status',a.status,'email',u.email,
  'is_admin',public.vf_is_admin(),'companies',coalesce((select jsonb_agg(to_jsonb(l) order by l.created_at desc)
   from public.vf_licenses l where l.owner_id=a.id),'[]'::jsonb)) into result
 from public.vf_accounts a join auth.users u on u.id=a.id where a.id=auth.uid();
 if result is null then raise exception 'Conta sem cadastro de acesso. Contate o suporte.'; end if;
 return result;
end; $$;

create function public.vf_valid_cnpj(value text) returns boolean language plpgsql immutable set search_path='' as $$
declare digits int[]; s int; d int; j int; i int; w int[];
begin
 if value !~ '^[0-9]{14}$' or value=repeat(substr(value,1,1),14) then return false; end if;
 digits:=array(select substr(value,n,1)::int from generate_series(1,14) n);
 for j in 1..2 loop
  w:=case when j=1 then array[5,4,3,2,9,8,7,6,5,4,3,2] else array[6,5,4,3,2,9,8,7,6,5,4,3,2] end;
  s:=0; for i in 1..array_length(w,1) loop s:=s+digits[i]*w[i]; end loop;
  d:=case when s%11<2 then 0 else 11-s%11 end;
  if digits[12+j]<>d then return false; end if;
 end loop;
 return true;
end; $$;

create function public.vf_request_company(cnpj_value text, company_name text) returns jsonb language plpgsql security definer set search_path='' as $$
declare result uuid; acc text;
begin
 select status into acc from public.vf_accounts where id=auth.uid();
 if acc is null or acc not in ('pending','approved') then raise exception 'Conta não liberada para novas solicitações.'; end if;
 if not public.vf_valid_cnpj(cnpj_value) or length(trim(company_name)) not between 2 and 200 then raise exception 'Confira o CNPJ e a razão social.'; end if;
 if (select count(*) from public.vf_licenses where owner_id=auth.uid())>=100 then raise exception 'Limite de solicitações desta conta. Contate o suporte.'; end if;
 insert into public.vf_licenses(owner_id,cnpj,name) values(auth.uid(),cnpj_value,trim(company_name))
 on conflict(owner_id,cnpj) do nothing returning id into result;
 if result is null then select id into result from public.vf_licenses where owner_id=auth.uid() and cnpj=cnpj_value; end if;
 return jsonb_build_object('id',result,'message','Solicitação registrada. Aguarde a aprovação.');
end; $$;

create function public.vf_admin_list() returns jsonb language plpgsql security definer set search_path='' as $$
begin
 if not public.vf_is_admin() then raise exception 'Acesso exclusivo da administração.'; end if;
 return jsonb_build_object('today',(now() at time zone 'America/Sao_Paulo')::date,
 'accounts',coalesce((select jsonb_agg(to_jsonb(a)||jsonb_build_object('email',u.email) order by a.created_at desc)
  from public.vf_accounts a join auth.users u on a.id=u.id),'[]'::jsonb),
 'companies',coalesce((select jsonb_agg(to_jsonb(l)||jsonb_build_object('email',u.email,'account_name',a.name,'account_status',a.status)
  order by l.created_at desc) from public.vf_licenses l join public.vf_accounts a on a.id=l.owner_id join auth.users u on u.id=a.id),'[]'::jsonb),
 'devices',coalesce((select jsonb_agg(to_jsonb(d) order by d.last_seen desc) from public.vf_devices d),'[]'::jsonb),
 'history',coalesce((select jsonb_agg(to_jsonb(t)) from (select * from public.vf_audit order by id desc limit 200) t),'[]'::jsonb));
end; $$;

create function public.vf_next_expiry(current_date_value date,previous_value date,months_value int) returns date language plpgsql immutable set search_path='' as $$
begin
 if months_value not in (1,3,6,12) then raise exception 'Escolha 1, 3, 6 ou 12 meses.'; end if;
 return (greatest(current_date_value,coalesce(previous_value,current_date_value))+make_interval(months=>months_value))::date;
end; $$;
create function public.vf_admin_change(p jsonb) returns jsonb language plpgsql security definer set search_path='' as $$
declare l public.vf_licenses; a public.vf_accounts; result jsonb; old_result jsonb;
 action_name text:=p->>'action'; target_id uuid:=(p->>'id')::uuid; op uuid:=(p->>'operation_id')::uuid;
 months int:=coalesce((p->>'months')::int,1); new_date date; today_date date:=(now() at time zone 'America/Sao_Paulo')::date;
 preview boolean:=coalesce((p->>'preview')::boolean,false); old_date date; limit_value int;
begin
 if not public.vf_is_admin() then raise exception 'Acesso exclusivo da administração.'; end if;
 if op is null then raise exception 'Identificador da operação ausente.'; end if;
 -- Serializa também tentativas concorrentes da mesma operação: renovação não se repete.
 perform pg_advisory_xact_lock(hashtext(auth.uid()::text||op::text));
 select audit.result into old_result from public.vf_audit audit where audit.actor=auth.uid() and audit.operation_id=op;
 if found then return old_result; end if;
 if length(coalesce(p->>'memo',''))>500 then raise exception 'Observação muito longa.'; end if;
 if action_name like 'account_%' then
  select * into a from public.vf_accounts where id=target_id for update;
  if not found or a.revision<>coalesce((p->>'revision')::int,0) then raise exception 'Cadastro alterado. Atualize a lista.'; end if;
  if exists(select 1 from public.vf_admins where user_id=a.id) then raise exception 'Conta administradora é gerenciada fora deste painel.'; end if;
  if action_name not in ('account_approve','account_reject','account_suspend') then raise exception 'Ação inválida.'; end if;
  result:=jsonb_build_object('account_id',a.id,'status',case action_name when 'account_approve' then 'approved' when 'account_reject' then 'rejected' else 'suspended' end);
  if preview then return result; end if;
  update public.vf_accounts set status=result->>'status',revision=revision+1 where id=a.id;
 else
  select * into l from public.vf_licenses where id=target_id for update;
  if not found or l.revision<>coalesce((p->>'revision')::int,0) then raise exception 'Empresa alterada. Atualize a lista.'; end if;
  select * into a from public.vf_accounts where id=l.owner_id for update;
  old_date:=l.valid_until; new_date:=l.valid_until;
  limit_value:=coalesce((p->>'max_devices')::int,l.max_devices);
  if limit_value not between 1 and 50 then raise exception 'Escolha de 1 a 50 computadores.'; end if;
  if action_name in ('approve','approve_both','renew') then
   if months not in (1,3,6,12) then raise exception 'Escolha 1, 3, 6 ou 12 meses.'; end if;
   if action_name='renew' and not l.ever_approved then raise exception 'Aprove a empresa antes de renovar.'; end if;
   if action_name='renew' and (l.status<>'approved' or a.status<>'approved') then raise exception 'Reative a conta e a empresa antes de renovar.'; end if;
   if action_name='approve_both' and a.status='suspended' then raise exception 'Reative a conta suspensa antes de aprovar.'; end if;
   if action_name='approve' and a.status<>'approved' then raise exception 'Aprove também a conta responsável.'; end if;
   if action_name in ('approve','approve_both') and l.status='approved' then raise exception 'Empresa já aprovada. Use Renovar.'; end if;
   new_date:=public.vf_next_expiry(today_date,l.valid_until,months);
   l.status:='approved'; l.ever_approved:=true;
  elsif action_name='suspend' then l.status:='suspended';
  elsif action_name='reject' then
   if l.ever_approved then raise exception 'Empresa já liberada anteriormente. Use Suspender.'; end if;
   l.status:='rejected';
  elsif action_name='reactivate' then
   if not l.ever_approved or l.valid_until is null or l.valid_until<today_date then raise exception 'Aprove ou renove a validade antes de reativar.'; end if;
   l.status:='approved';
  elsif action_name='devices' then
   if limit_value<(select count(*) from public.vf_devices where license_id=l.id and not revoked) then raise exception 'Desative os computadores excedentes antes de reduzir o limite.'; end if;
  elsif action_name='revoke_device' then
   if not exists(select 1 from public.vf_devices where id=(p->>'device_id')::uuid and license_id=l.id) then raise exception 'Computador não pertence a esta licença.'; end if;
  else raise exception 'Ação inválida.';
  end if;
  result:=jsonb_build_object('id',l.id,'cnpj',l.cnpj,'name',l.name,'previous_until',old_date,'valid_until',new_date,
    'status',l.status,'max_devices',limit_value,'account_status',case when action_name='approve_both' then 'approved' else a.status end);
  if preview then return result; end if;
  if action_name='approve_both' then update public.vf_accounts set status='approved',revision=revision+1 where id=a.id; end if;
  if action_name='revoke_device' then update public.vf_devices set revoked=true where id=(p->>'device_id')::uuid; end if;
  update public.vf_licenses set status=l.status,ever_approved=l.ever_approved,valid_until=new_date,max_devices=limit_value,revision=revision+1 where id=l.id;
 end if;
 insert into public.vf_audit(actor,operation_id,action,target,result,memo) values(auth.uid(),op,action_name,target_id,result,coalesce(p->>'memo',''));
 return result;
end; $$;

create function public.vf_admin_recovery_audit(user_value uuid,operation_value uuid) returns jsonb language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
 if not public.vf_is_admin() then raise exception 'Acesso exclusivo da administração.'; end if;
 if not exists(select 1 from public.vf_accounts where id=user_value) or exists(select 1 from public.vf_admins where user_id=user_value) then raise exception 'Conta não elegível para recuperação assistida.'; end if;
 result:=jsonb_build_object('account_id',user_value,'name',(select name from public.vf_accounts where id=user_value));
 insert into public.vf_audit(actor,operation_id,action,target,result) values(auth.uid(),operation_value,'password_recovery',user_value,result) on conflict(actor,operation_id) do nothing;
 return result;
end; $$;
create function public.vf_license_snapshot(license_value uuid, installation_value uuid, computer_label text) returns jsonb language plpgsql security definer set search_path='' as $$
declare l public.vf_licenses; a public.vf_accounts; d public.vf_devices; can_emit boolean; until_time timestamptz;
begin
 select * into l from public.vf_licenses where id=license_value and owner_id=auth.uid() for update;
 if not found then raise exception 'Empresa não autorizada nesta conta.'; end if;
 select * into a from public.vf_accounts where id=l.owner_id;
 if not l.ever_approved then raise exception 'Empresa aguardando aprovação ou reprovada.'; end if;
 select * into d from public.vf_devices where license_id=l.id and installation_id=installation_value;
 if found and d.revoked then raise exception 'Este computador foi desativado. Contate o suporte.'; end if;
 if d.id is null then
  if (select count(*) from public.vf_devices where license_id=l.id and not revoked)>=l.max_devices then raise exception 'Limite de computadores atingido. Solicite a troca ao suporte.'; end if;
  insert into public.vf_devices(license_id,installation_id,label) values(l.id,installation_value,left(computer_label,100)) returning * into d;
 end if;
 update public.vf_devices set last_seen=now() where id=d.id;
 can_emit:=a.status='approved' and l.status='approved' and l.valid_until>=(now() at time zone 'America/Sao_Paulo')::date;
 until_time:=least(now()+interval '72 hours',coalesce((l.valid_until+1)::timestamp at time zone 'America/Sao_Paulo',now()));
 return jsonb_build_object('version',1,'sub',a.id,'email',(select email from auth.users where id=a.id),
 'license_id',l.id,'cnpj',l.cnpj,'name',l.name,'installation_id',installation_value,'read',true,
 'emit',coalesce(can_emit,false),'status',l.status,'account_status',a.status,'valid_until',l.valid_until,
 'issued_at',extract(epoch from now())::bigint,'emit_until',extract(epoch from greatest(now(),until_time))::bigint);
end; $$;

revoke all on function public.vf_is_admin(),public.vf_on_signup(),public.vf_client_state(),public.vf_valid_cnpj(text),public.vf_next_expiry(date,date,int),public.vf_request_company(text,text),public.vf_admin_list(),public.vf_admin_change(jsonb),public.vf_admin_recovery_audit(uuid,uuid),public.vf_license_snapshot(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.vf_is_admin(),public.vf_client_state(),public.vf_request_company(text,text),public.vf_admin_list(),public.vf_admin_change(jsonb),public.vf_admin_recovery_audit(uuid,uuid),public.vf_license_snapshot(uuid,uuid,text) to authenticated;
commit;
