// Somente QA: backend PostgreSQL isolado em memória e identidades fictícias.
// O painel usa as RPCs reais da migração; nenhuma conexão ao Supabase de produção.
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {PGlite}=require(process.env.VF_PGLITE_PATH||'@electric-sql/pglite');
const ROOT=path.resolve(__dirname,'..'),admin='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const db=new PGlite();
(async()=>{
 await db.exec(`create role service_role;create role anon;create role authenticated;create schema auth;create table auth.users(id uuid primary key,email text,raw_user_meta_data jsonb default '{}'::jsonb);create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;grant usage on schema public,auth to anon,authenticated;grant execute on function auth.uid() to anon,authenticated;`);
 await db.exec(fs.readFileSync(path.join(ROOT,'supabase/migrations/202611120001_access.sql'),'utf8'));
 await db.query('insert into auth.users(id,email,raw_user_meta_data) values($1,$2,$3)',[admin,'administracao@vf.exemplo.invalid',{name:'Administração de demonstração'}]);
 await db.query('insert into vf_admins values($1)',[admin]);
 const names=['Comércio Horizonte','Distribuidora Aurora','Oficina Nova','Mercado Central'];
 for(let i=0;i<4;i++){
  const id=`bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb${i}`;
  await db.query('insert into auth.users(id,email,raw_user_meta_data) values($1,$2,$3)',[id,`cliente${i+1}@exemplo.invalid`,{name:['Marina — demonstração','João — demonstração','Ana — demonstração','Carlos — demonstração'][i]}]);
  if(i)await db.query("update vf_accounts set status='approved' where id=$1",[id]);
  await db.query("insert into vf_licenses(owner_id,cnpj,name,status,valid_until,ever_approved) values($1,'11222333000181',$2,$3,(now() at time zone 'America/Sao_Paulo')::date+$4::integer,$5)",[id,names[i]+' · demonstração',i?'approved':'pending',i===1?45:i===2?5:i===3?-8:null,Boolean(i)]);
 }
 let serial=Promise.resolve();
 const port=Number(process.env.PORT||process.argv[process.argv.indexOf('--port')+1])||4173;
 http.createServer((req,res)=>{
  const respond=(code,value,type='application/json')=>{const raw=Buffer.isBuffer(value)?value:typeof value==='string'?value:JSON.stringify(value);res.writeHead(code,{'Content-Type':type,'Cache-Control':'no-store'});res.end(raw);};
  if(req.url.startsWith('/qa-supabase/')){
   let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{serial=serial.then(async()=>{
    try{const p=JSON.parse(raw||'{}');const route=req.url.slice('/qa-supabase'.length);
     if(route.startsWith('/auth/v1/token')){if(p.email!=='administracao@vf.exemplo.invalid'||p.password!=='Demonstracao-2026')return respond(400,{error:'Credencial fictícia incorreta.'});return respond(200,{access_token:'demo-admin',refresh_token:'demo-refresh',expires_in:3600});}
     if(req.headers.authorization!=='Bearer demo-admin')return respond(401,{error:'Entre na demonstração.'});
     const name=route.split('/').at(-1);if(!['vf_client_state','vf_admin_list','vf_admin_change'].includes(name))return respond(400,{error:'RPC não disponível na demonstração.'});
     await db.exec('set role authenticated');await db.query("select set_config('request.jwt.claim.sub',$1,false)",[admin]);
     try{const r=await db.query(`select ${name}(${name==='vf_admin_change'?'$1':''}) as result`,name==='vf_admin_change'?[p.p]:[]);respond(200,r.rows[0].result);}finally{await db.exec('reset role');}
    }catch(e){respond(400,{message:e.message});}
   });});return;
  }
  if(req.url==='/config.json')return respond(200,{url:'https://abcdefghijklmnopqrst.supabase.co',publishable_key:'sb_publishable_demo-not-a-real-key-123456789'});
  const name=req.url.split('?')[0]==='/'?'index.html':req.url.split('?')[0].slice(1);
  if(!['index.html','app.js','style.css','favicon.svg'].includes(name))return respond(404,'Não encontrado.','text/plain');
  let file=fs.readFileSync(path.join(ROOT,'portal',name));
  if(name==='app.js')file=Buffer.from(file.toString().replace('fetch(config.url+path','fetch(\'/qa-supabase\'+path')
   .replace('const handlers={',"const handlers={'demo-start':async()=>{session={access_token:'demo-admin',until:Date.now()+3600000};await refresh();},")
   .replace('if(!session){$(\'#app\').innerHTML=login();return;}',"if(!session){$('#app').innerHTML=login().replace('<form id=\"login\">','<button type=\"button\" class=\"primary\" data-action=\"demo-start\">Abrir demonstração de gestão</button><form id=\"login\">');return;}"));
  if(name==='index.html')file=Buffer.from(file.toString().replace('<body>','<body><div style="padding:7px;background:#dce9bd;text-align:center;font:12px Segoe UI;color:#314c2e">DEMONSTRAÇÃO · dados fictícios · nenhuma alteração em clientes reais</div>'));
  respond(200,file,({'index.html':'text/html; charset=utf-8','app.js':'text/javascript','style.css':'text/css','favicon.svg':'image/svg+xml'})[name]);
 }).listen(port,'0.0.0.0',()=>process.stdout.write('Demonstração isolada na porta '+port+'\n'));
})();
