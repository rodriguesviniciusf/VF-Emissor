const {test}=require('node:test'),assert=require('node:assert/strict'),{webcrypto}=require('node:crypto');
test('Edge Function verifica identidade antes de assinar ou recuperar acesso',async t=>{
 const keys=await webcrypto.subtle.generateKey('Ed25519',true,['sign','verify']);
 const env={SUPABASE_URL:'https://abcdefghijklmnopqrst.supabase.co',SUPABASE_ANON_KEY:'public-test',SUPABASE_SERVICE_ROLE_KEY:'secret-only-on-server',VF_PORTAL_ORIGINS:'https://admin.example.invalid',VF_LICENSE_PRIVATE_KEY:Buffer.from(await webcrypto.subtle.exportKey('pkcs8',keys.privateKey)).toString('base64')};
 let handler,isAdmin=false,validAuth=true,mismatch=false,outage=false,calls=[];
 const oldDeno=global.Deno,oldFetch=global.fetch;
 global.Deno={env:{get:n=>env[n]},serve:f=>handler=f};
 global.fetch=async(url,p)=>{calls.push({url,p});if(outage)throw new TypeError('synthetic outage');
  const r=(v,s=200)=>new Response(JSON.stringify(v),{status:s});
  if(url.endsWith('/auth/v1/user'))return r({id:'user-id'},validAuth?200:401);
  if(url.endsWith('vf_license_snapshot'))return r({version:1,sub:mismatch?'other-id':'user-id',cnpj:'11222333000181',emit:true});
  if(url.endsWith('vf_is_admin'))return r(isAdmin);
  if(url.endsWith('vf_admin_list'))return r({accounts:[{id:'client-id',email:'client@example.invalid'}]});
  if(url.endsWith('vf_admin_recovery_audit'))return r({ok:true});
  if(url.endsWith('/auth/v1/admin/generate_link'))return r({hashed_token:'synthetic-one-time-recovery-code'});
  throw Error('Unexpected fetch '+url);
 };
 try{
  await import('../supabase/functions/vf-license/index.ts');
  const call=(p,headers={},method='POST')=>handler(new Request('https://edge.example.invalid/vf-license',{method,headers:{Authorization:'Bearer synthetic',...headers},...(method==='POST'?{body:JSON.stringify(p)}:{})}));
  await t.test('origem não autorizada e método incorreto não acessam banco',async()=>{calls=[];assert.equal((await call({}, {Origin:'https://evil.example'})).status,403);assert.equal((await call({}, {},'GET')).status,405);assert.equal(calls.length,0);});
  await t.test('JWT é validado no Auth, não apenas decodificado',async()=>{validAuth=false;calls=[];assert.equal((await call({action:'license'})).status,401);assert.equal(calls.length,1);validAuth=true;});
  await t.test('assinatura Ed25519 confere sobre os bytes exatos',async()=>{const r=await call({action:'license',license_id:'license',installation_id:'device'});assert.equal(r.status,200);const d=await r.json();assert.ok(await webcrypto.subtle.verify('Ed25519',keys.publicKey,Buffer.from(d.signature,'base64'),Buffer.from(d.payload,'base64')));assert.equal(JSON.parse(Buffer.from(d.payload,'base64')).sub,'user-id');});
  await t.test('identidade divergente não recebe licença',async()=>{mismatch=true;assert.equal((await call({action:'license'})).status,400);mismatch=false;});
  await t.test('indisponibilidade usa 503 e não simula revogação',async()=>{outage=true;assert.equal((await call({action:'license'})).status,503);outage=false;});
  await t.test('cliente comum não usa credencial administrativa na recuperação',async()=>{calls=[];assert.equal((await call({action:'recovery',user_id:'client-id',identity_checked:true})).status,403);assert.equal(calls.some(c=>c.url.endsWith('generate_link')),false);});
  await t.test('admin confirma identidade antes de gerar código',async()=>{isAdmin=true;calls=[];assert.equal((await call({action:'recovery',user_id:'client-id'})).status,400);assert.equal(calls.some(c=>c.url.endsWith('generate_link')),false);});
  await t.test('recuperação é auditada sem registrar código ou senha',async()=>{calls=[];const r=await call({action:'recovery',user_id:'client-id',identity_checked:true});assert.equal(r.status,200);const d=await r.json();assert.equal(d.recovery_code,'synthetic-one-time-recovery-code');const audit=calls.find(c=>c.url.endsWith('vf_admin_recovery_audit'));assert.ok(audit);assert.equal(audit.p.body.includes(d.recovery_code),false);const secret=calls.find(c=>c.url.endsWith('generate_link'));assert.equal(secret.p.headers.Authorization,'Bearer secret-only-on-server');});
 }finally{global.Deno=oldDeno;global.fetch=oldFetch;}
});
