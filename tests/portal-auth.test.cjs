const {test}=require('node:test'),assert=require('node:assert/strict');
const {createRecovery,email,errorMessage}=require('../portal/auth.js');
const config={url:'https://abcdefghijklmnopqrst.supabase.co',publishable_key:'sb_publishable_synthetic'};
function fixture(){
 const calls=[],state={};
 const recovery=createRecovery(config,async(url,p)=>{
  calls.push({url,...p,body:p.body?JSON.parse(p.body):undefined});
  if(state.offline)throw new TypeError('synthetic');
  const reply=(d,s=200)=>new Response(JSON.stringify(d),{status:s});
  if(url.endsWith('/recover'))return state.sendError?reply({code:state.sendError},429):reply({});
  if(url.endsWith('/verify'))return state.verifyError?reply({code:'otp_expired'},403):reply({access_token:'eyJsynthetic.recovery.token',user:{email:state.otherEmail?'other@example.invalid':'admin@example.invalid'},expires_in:3600});
  if(p.method==='GET')return state.invalidToken?reply({},401):reply({id:'synthetic-user',email:'admin@example.invalid'});
  if(p.method==='PUT')return state.updateError?reply({code:state.updateError},state.updateStatus||422):reply({id:'synthetic-user'});
  throw Error('unexpected request');
 });return {recovery,calls,state};
}
const verify=f=>f.recovery.verify('admin@example.invalid','12345678');
test('Recuperação do painel preserva a identidade e mantém credenciais só em memória',async t=>{
 await t.test('normaliza apenas o e-mail e envia pedido sem credencial administrativa',async()=>{const f=fixture();assert.deepEqual(await f.recovery.send(' ADMIN@EXAMPLE.INVALID '),{ok:true});assert.deepEqual(f.calls[0].body,{email:'admin@example.invalid'});assert.equal(f.calls[0].headers.apikey,config.publishable_key);assert.equal(f.calls[0].headers.Authorization,undefined);});
 await t.test('e-mail inválido não dispara pedido',async()=>{const f=fixture();await assert.rejects(()=>f.recovery.send('bad'),/válido/);assert.equal(f.calls.length,0);});
 await t.test('limite de envio é explicado sem afirmar que a senha está errada',async()=>{const f=fixture();f.state.sendError='over_email_send_rate_limit';await assert.rejects(()=>f.recovery.send('admin@example.invalid'),/Muitas tentativas/);});
 await t.test('código válido usa somente o fluxo de recuperação',async()=>{const f=fixture();assert.deepEqual(await verify(f),{ok:true});assert.deepEqual(f.calls[0].body,{email:'admin@example.invalid',token:'12345678',type:'recovery'});});
 await t.test('link do e-mail é conferido e trocado sem seguir redirecionamentos',async()=>{const f=fixture();await f.recovery.verify('admin@example.invalid',config.url+'/auth/v1/verify?token='+'x'.repeat(64)+'&type=recovery&redirect_to=https://example.invalid');assert.equal(f.calls.length,1);assert.equal(f.calls[0].url,config.url+'/auth/v1/verify');assert.deepEqual(f.calls[0].body,{token_hash:'x'.repeat(64),type:'recovery'});});
 await t.test('links de outro servidor e de outro tipo são recusados antes de usar a rede',async()=>{for(const link of ['https://evil.example/auth/v1/verify?token='+'x'.repeat(64)+'&type=recovery',config.url+'/auth/v1/verify?token='+'x'.repeat(64)+'&type=email']){const f=fixture();await assert.rejects(()=>f.recovery.verify('admin@example.invalid',link),/link de recuperação/);assert.equal(f.calls.length,0);}});
 await t.test('código vencido e identidade divergente não autorizam nova senha',async()=>{for(const flag of ['verifyError','otherEmail']){const f=fixture();f.state[flag]=true;await assert.rejects(()=>verify(f));await assert.rejects(()=>f.recovery.update('NovaSenha-2026','NovaSenha-2026'),/autorização venceu/);assert.equal(f.calls.length,1);}});
 await t.test('callback valida sessão no Auth antes de aceitar a nova senha',async()=>{const f=fixture();await f.recovery.acceptToken('eyJsynthetic.recovery.token');assert.equal(f.calls[0].method,'GET');assert.equal(f.calls[0].body,undefined);assert.equal(f.calls[0].headers.Authorization,'Bearer eyJsynthetic.recovery.token');await f.recovery.update(' NovaSenha-2026 ',' NovaSenha-2026 ');assert.equal(f.calls[1].body.password,' NovaSenha-2026 ');});
 await t.test('callback inválido não habilita atualização',async()=>{const f=fixture();f.state.invalidToken=true;await assert.rejects(()=>f.recovery.acceptToken('eyJsynthetic.invalid.token'));await assert.rejects(()=>f.recovery.update('NovaSenha-2026','NovaSenha-2026'),/autorização venceu/);assert.equal(f.calls.length,1);});
 await t.test('mínimo e repetição são validados antes de alterar a senha',async()=>{const f=fixture();await verify(f);await assert.rejects(()=>f.recovery.update('curta','curta'),/10 a 128/);await assert.rejects(()=>f.recovery.update('NovaSenha-2026','outra'),/iguais/);assert.equal(f.calls.length,1);});
 await t.test('nova senha é enviada por PUT com a sessão de recuperação e não é devolvida',async()=>{const f=fixture();await verify(f);const result=await f.recovery.update('NovaSenha-2026','NovaSenha-2026');assert.deepEqual(result,{ok:true});assert.equal(f.calls[1].method,'PUT');assert.equal(f.calls[1].headers.Authorization,'Bearer eyJsynthetic.recovery.token');assert.deepEqual(f.calls[1].body,{password:'NovaSenha-2026'});await assert.rejects(()=>f.recovery.update('OutraSenha-2026','OutraSenha-2026'),/autorização venceu/);});
 await t.test('senha igual à anterior pode ser corrigida sem consumir outro link',async()=>{const f=fixture();await verify(f);f.state.updateError='same_password';await assert.rejects(()=>f.recovery.update('NovaSenha-2026','NovaSenha-2026'),/diferente/);f.state.updateError=null;await f.recovery.update('OutraSenha-2026','OutraSenha-2026');assert.equal(f.calls.filter(c=>c.url.endsWith('/verify')).length,1);});
 await t.test('sessão recusada é descartada',async()=>{const f=fixture();await verify(f);f.state.updateError='session_not_found';f.state.updateStatus=401;await assert.rejects(()=>f.recovery.update('NovaSenha-2026','NovaSenha-2026'));await assert.rejects(()=>f.recovery.update('OutraSenha-2026','OutraSenha-2026'),/autorização venceu/);assert.equal(f.calls.length,2);});
 await t.test('sair da recuperação descarta a autorização',async()=>{const f=fixture();await verify(f);f.recovery.clear();await assert.rejects(()=>f.recovery.update('NovaSenha-2026','NovaSenha-2026'),/autorização venceu/);});
 await t.test('falha de conexão não se confunde com senha inválida',async()=>{const f=fixture();f.state.offline=true;await assert.rejects(()=>f.recovery.send('admin@example.invalid'),/internet/);});
 await t.test('mensagens separam credencial inválida de falta de permissão',()=>{assert.match(errorMessage('/auth/v1/token?grant_type=password',{code:'invalid_credentials'},400),/Esqueci minha senha/);assert.equal(errorMessage('/rest/v1/rpc/vf_admin_list',{message:'Acesso exclusivo da administração.'},400),'Acesso exclusivo da administração.');assert.equal(email(' ADMIN@EXAMPLE.INVALID '),'admin@example.invalid');});
});
