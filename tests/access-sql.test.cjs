// PostgreSQL real em WASM; Auth/roles simulados, regras e permissões da migração reais.
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {PGlite}=require(process.env.VF_PGLITE_PATH||'@electric-sql/pglite');
const {randomUUID}=require('node:crypto');
test('Aprovação, isolamento, renovação e dispositivos no PostgreSQL',async t=>{
 const db=new PGlite();
 try{
 await db.exec(`create role service_role;create role anon; create role authenticated; create schema auth;
 create table auth.users(id uuid primary key,email text,raw_user_meta_data jsonb default '{}'::jsonb);
 create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
 grant usage on schema public,auth to anon,authenticated;
 grant execute on function auth.uid() to anon,authenticated;`);
 await db.exec(fs.readFileSync(path.join(__dirname,'../supabase/migrations/202611120001_access.sql'),'utf8'));
 const admin=randomUUID(),a=randomUUID(),b=randomUUID(),device=randomUUID();
 await db.query(`insert into auth.users(id,email,raw_user_meta_data) values($1,'admin@example.invalid','{"name":"Admin"}'),($2,'a@example.invalid','{"name":"Cliente A","admin":true,"status":"approved"}'),($3,'b@example.invalid','{"name":"Cliente B"}')`,[admin,a,b]);
 await db.query('insert into vf_admins values($1)',[admin]);
 const raw=async(sql,args=[])=> (await db.query(sql,args)).rows;
 const as=async(user,sql,args=[],role='authenticated')=>{
  await db.exec('set role '+role);await db.query("select set_config('request.jwt.claim.sub',$1,false)",[user||'']);
  try{return await raw(sql,args);}finally{await db.exec('reset role');}
 };
 const rpc=async(user,name,args)=> (await as(user,'select '+name+'($1) as result',[args]))[0].result;
 const request=async(user,cnpj='11222333000181')=>(await as(user,'select vf_request_company($1,$2) as result',[cnpj,'Empresa de teste']))[0].result.id;
 const snapshot=async(user,id,dev=device)=>(await as(user,'select vf_license_snapshot($1,$2,$3) as result',[id,dev,'PC teste']))[0].result;
 const list=async()=> (await as(admin,'select vf_admin_list() as result'))[0].result;
 const get=async id=>(await list()).companies.find(c=>c.id===id);
 const change=async(id,action,extra={})=>{const l=await get(id);return rpc(admin,'vf_admin_change',{id,action,revision:l.revision,operation_id:randomUUID(),...extra});};
 let la,lb;
 await t.test('metadata do usuário não concede aprovação nem papel administrador',async()=>{const p=(await as(a,'select vf_client_state() as result'))[0].result;assert.equal(p.status,'pending');assert.equal(p.is_admin,false);});
 await t.test('anônimo não executa RPC e usuário não consulta tabelas',async()=>{await assert.rejects(()=>as(null,'select vf_client_state()',[],'anon'),/permission denied/);for(const table of ['vf_admins','vf_accounts','vf_licenses','vf_devices','vf_audit'])await assert.rejects(()=>as(a,'select * from '+table),/permission denied/);});
 await t.test('configuração protegida não pode ser lida por cliente nem anônimo',async()=>{await assert.rejects(()=>as(null,'select public.vf_runtime_config()',[],'anon'),/permission denied/);await assert.rejects(()=>as(a,'select public.vf_runtime_config()'),/permission denied/);await assert.rejects(()=>as(a,'select * from vf_private.runtime_settings'),/permission denied/);const publicDefiners=await raw("select p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'vf_%' and p.prosecdef");assert.deepEqual(publicDefiners,[]);});
 await t.test('não administrador não aprova nem vê painel',async()=>{await assert.rejects(()=>as(a,'select vf_admin_list()'),/exclusivo/);await assert.rejects(()=>rpc(a,'vf_admin_change',{id:a,action:'account_approve',operation_id:randomUUID()}),/exclusivo/);await assert.rejects(()=>as(a,'insert into vf_admins values($1)',[a]),/permission denied/);});
 await t.test('CNPJ válido e solicitações separadas por conta',async()=>{await assert.rejects(()=>request(a,'11111111111111'),/Confira/);la=await request(a);lb=await request(b);assert.notEqual(la,lb);assert.equal(await request(a),la);});
 await t.test('pendentes só veem a própria solicitação e não ativam emissão',async()=>{const p=(await as(a,'select vf_client_state() as result'))[0].result;assert.equal(p.companies.length,1);assert.equal(p.companies[0].id,la);await assert.rejects(()=>snapshot(a,la),/aprovação/);await assert.rejects(()=>snapshot(a,lb),/não autorizada/);});
 await t.test('prévia não aprova nem altera validade',async()=>{const p=await change(la,'approve_both',{preview:true,months:1});assert.equal(p.status,'approved');const l=await get(la);assert.equal(l.status,'pending');assert.equal(l.valid_until,null);assert.equal((await list()).history.length,0);});
 await t.test('aprova conta e primeiro CNPJ juntos, sem liberar outro usuário',async()=>{await change(la,'approve_both',{months:1,max_devices:1});const p=(await as(a,'select vf_client_state() as result'))[0].result;assert.equal(p.status,'approved');assert.equal(p.companies[0].status,'approved');assert.equal((await get(lb)).status,'pending');});
 await t.test('calendário: meses preservam dias pagos e tratam fim de mês',async()=>{for(const [today,previous,months,expected] of [['2026-11-12','2026-12-20',1,'2027-01-20'],['2026-11-12','2026-10-10',1,'2026-12-12'],['2026-01-31',null,1,'2026-02-28'],['2028-01-31',null,1,'2028-02-29'],['2026-11-12',null,12,'2027-11-12']]){const r=await raw('select vf_next_expiry($1::date,$2::date,$3)::text as d',[today,previous,months]);assert.equal(r[0].d,expected);}});
 await t.test('renovação idempotente não cobra dois períodos em repetição',async()=>{const l=await get(la);const op={id:la,action:'renew',months:1,revision:l.revision,operation_id:randomUUID()};const r=await rpc(admin,'vf_admin_change',op);assert.deepEqual(await rpc(admin,'vf_admin_change',op),r);assert.equal((await get(la)).valid_until,r.valid_until);});
 await t.test('alteração obsoleta e prazos não permitidos são rejeitados',async()=>{await assert.rejects(()=>rpc(admin,'vf_admin_change',{id:la,action:'renew',months:1,revision:1,operation_id:randomUUID()}),/alterada/);await assert.rejects(()=>change(la,'renew',{months:2}),/Escolha/);await assert.rejects(()=>change(la,'devices',{max_devices:0}),/computadores/);});
 await t.test('licença vincula pessoa, CNPJ e computador com prazo máximo de 72h',async()=>{const d=await snapshot(a,la);assert.equal(d.sub,a);assert.equal(d.installation_id,device);assert.equal(d.cnpj,'11222333000181');assert.equal(d.emit,true);assert.equal(d.read,true);assert.ok(d.emit_until-d.issued_at<=259200);});
 await t.test('limite de computadores e revogação não se reativam sozinhos',async()=>{await assert.rejects(()=>snapshot(a,la,randomUUID()),/Limite/);const listData=await list();const d=listData.devices.find(d=>d.license_id===la);await change(la,'revoke_device',{device_id:d.id});await assert.rejects(()=>snapshot(a,la,device),/desativado/);await snapshot(a,la,randomUUID());});
 await t.test('suspensão preserva consulta e impede emissão',async()=>{await change(la,'suspend');const dev=(await list()).devices.find(d=>d.license_id===la&&!d.revoked).installation_id;const d=await snapshot(a,la,dev);assert.equal(d.emit,false);assert.equal(d.read,true);await assert.rejects(()=>change(la,'renew'),/Reative/);await change(la,'reactivate');assert.equal((await snapshot(a,la,dev)).emit,true);});
 await t.test('suspensão da conta bloqueia emissão da empresa aprovada',async()=>{let acc=(await list()).accounts.find(c=>c.id===a);await rpc(admin,'vf_admin_change',{id:a,action:'account_suspend',revision:acc.revision,operation_id:randomUUID()});const dev=(await list()).devices.find(d=>d.license_id===la&&!d.revoked).installation_id;assert.equal((await snapshot(a,la,dev)).emit,false);});
 await t.test('vencimento corta emissão e mantém XML/consulta, sem liberar outra empresa',async()=>{await db.query("update vf_licenses set valid_until=current_date-1 where id=$1",[la]);const dev=(await list()).devices.find(d=>d.license_id===la&&!d.revoked).installation_id;const d=await snapshot(a,la,dev);assert.equal(d.emit,false);assert.equal(d.read,true);assert.equal(d.emit_until,d.issued_at);await assert.rejects(()=>snapshot(b,la),/não autorizada/);});
 }finally{await db.close();}
});
