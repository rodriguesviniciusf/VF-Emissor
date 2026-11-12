// Segredos ficam somente na Edge Function. Não incluir chave privada no instalador.
const env = (name: string) => Deno.env.get(name) || '';
const json = (data: unknown, status = 200, origin = '') => new Response(JSON.stringify(data), {
 status, headers: {'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
 ...(origin ? {'Access-Control-Allow-Origin':origin,'Vary':'Origin'} : {})}
});
const b64 = (data: Uint8Array) => btoa(String.fromCharCode(...data));
class Unavailable extends Error {}
async function remote(url: string, options: RequestInit) {
 let r: Response;
 try { r=await fetch(url,options); } catch { throw new Unavailable('Serviço temporariamente indisponível.'); }
 if(r.status>=500||r.status===429)throw new Unavailable('Serviço temporariamente indisponível.');
 return r;
}
async function rpc(name: string, body: unknown, token: string) {
 const r = await remote(env('SUPABASE_URL')+'/rest/v1/rpc/'+name, {method:'POST',headers:{
  'apikey':env('SUPABASE_ANON_KEY'),'Authorization':token,'Content-Type':'application/json'},body:JSON.stringify(body)});
 const value = await r.json();
 if (!r.ok) throw new Error(value.message || 'Operação não autorizada.');
 return value;
}
let runtimeCache: {signing_key:string,portal_origins:string[]}|null=null;
let runtimeAt=0;
async function runtimeConfig(){
 if(env('VF_LICENSE_PRIVATE_KEY')&&env('VF_PORTAL_ORIGINS'))return {signing_key:env('VF_LICENSE_PRIVATE_KEY'),portal_origins:env('VF_PORTAL_ORIGINS').split(',').map(s=>s.trim()).filter(Boolean)};
 if(runtimeCache&&Date.now()-runtimeAt<60000)return runtimeCache;
 const key=env('SUPABASE_SERVICE_ROLE_KEY');
 if(!key)throw new Unavailable('Serviço de licenças ainda não configurado.');
 const r=await remote(env('SUPABASE_URL')+'/rest/v1/rpc/vf_runtime_config',{method:'POST',headers:{apikey:key,Authorization:'Bearer '+key,'Content-Type':'application/json'},body:'{}'});
 if(!r.ok)throw new Unavailable('Configuração protegida indisponível.');
 const d=await r.json();if(!d.signing_key||!Array.isArray(d.portal_origins))throw new Unavailable('Serviço de licenças ainda não configurado.');
 runtimeCache=d;runtimeAt=Date.now();return d as {signing_key:string,portal_origins:string[]};
}
Deno.serve(async (req: Request) => {
 const origin=req.headers.get('Origin')||'';
 try {
 const runtime=await runtimeConfig();
 const allowed=runtime.portal_origins;
 if(origin&&!allowed.includes(origin))return json({error:'Origem não autorizada.'},403);
 if(req.method==='OPTIONS')return new Response(null,{status:204,headers:{'Access-Control-Allow-Origin':origin,
  'Access-Control-Allow-Headers':'authorization,apikey,content-type','Access-Control-Allow-Methods':'POST','Vary':'Origin'}});
 if(req.method!=='POST')return json({error:'Método inválido.'},405,origin);
  const raw=await req.text();if(raw.length>8192)return json({error:'Requisição muito grande.'},413,origin);
  const p=JSON.parse(raw);
  if(p.action==='public_key'){
   const keyData=Uint8Array.from(atob(runtime.signing_key),c=>c.charCodeAt(0));
   const key=await crypto.subtle.importKey('pkcs8',keyData,{name:'Ed25519'},true,['sign']);
   const jwk=await crypto.subtle.exportKey('jwk',key);
   const publicBytes=Uint8Array.from(atob(jwk.x!.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
   return json({verification_key:b64(publicBytes)},200,origin);
  }
  const token=req.headers.get('Authorization')||'';
  if(!token.startsWith('Bearer '))return json({error:'Entre na sua conta.'},401,origin);
  const auth=await remote(env('SUPABASE_URL')+'/auth/v1/user',{headers:{apikey:env('SUPABASE_ANON_KEY'),Authorization:token}});
  if(!auth.ok)return json({error:'Sessão inválida. Entre novamente.'},401,origin);
  const user=await auth.json();
  if(p.action==='license'){
   const payload=await rpc('vf_license_snapshot',{license_value:p.license_id,installation_value:p.installation_id,computer_label:String(p.label||'Computador')},token);
   if(payload.sub!==user.id)throw new Error('Identidade divergente.');
   const keyData=Uint8Array.from(atob(runtime.signing_key),c=>c.charCodeAt(0));
   const key=await crypto.subtle.importKey('pkcs8',keyData,{name:'Ed25519'},false,['sign']);
   const bytes=new TextEncoder().encode(JSON.stringify(payload));
   const signature=await crypto.subtle.sign('Ed25519',key,bytes);
   return json({payload:b64(bytes),signature:b64(new Uint8Array(signature))},200,origin);
  }
  if(p.action==='recovery'){
   if(await rpc('vf_is_admin',{},token)!==true)return json({error:'Acesso exclusivo da administração.'},403,origin);
   if(p.identity_checked!==true)throw new Error('Confirme a identidade por um contato conhecido antes de liberar a recuperação.');
   const list=await rpc('vf_admin_list',{},token);const account=list.accounts.find((a: {id:string})=>a.id===p.user_id);
   if(!account||account.is_admin)throw new Error('Conta não encontrada.');
   await rpc('vf_admin_recovery_audit',{user_value:account.id,operation_value:crypto.randomUUID()},token);
   // Link não é enviado automaticamente. Nunca escrever links ou tokens no histórico/logs.
   const r=await remote(env('SUPABASE_URL')+'/auth/v1/admin/generate_link',{method:'POST',headers:{
    apikey:env('SUPABASE_SERVICE_ROLE_KEY'),Authorization:'Bearer '+env('SUPABASE_SERVICE_ROLE_KEY'),'Content-Type':'application/json'},
    body:JSON.stringify({type:'recovery',email:account.email})});
   if(!r.ok)throw new Error('Não foi possível gerar a recuperação. Confira a configuração do serviço.');
   const d=await r.json();return json({recovery_code:d.hashed_token,message:'Código de uso único. Entregue somente ao titular verificado; válido pelo prazo configurado no Auth.'},200,origin);
  }
  return json({error:'Ação inválida.'},400,origin);
 }catch(e){return json({error:e instanceof Error?e.message:'Não foi possível concluir.'},e instanceof Unavailable?503:400,origin);}
});
