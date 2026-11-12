'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.VFPortalAuth=api;})(globalThis,()=>{
 function email(value){return String(value||'').trim().toLowerCase();}
 function errorMessage(path,data,status){
  const code=data?.code||data?.error_code;
  if(status===429||['over_email_send_rate_limit','over_request_rate_limit'].includes(code))return 'Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.';
  if(code==='email_address_not_authorized')return 'O envio para este e-mail precisa ser liberado pelo responsável pelo projeto.';
  if(code==='email_not_confirmed')return 'O e-mail deste cadastro ainda não foi confirmado. Contate o responsável pelo projeto.';
  if(code==='otp_expired')return 'Código inválido ou vencido. Confira o código recebido ou solicite outro.';
  if(code==='same_password')return 'Escolha uma senha diferente da anterior.';
  if(code==='weak_password')return 'Use uma senha forte, com pelo menos 10 caracteres.';
  if(path.includes('grant_type=password'))return 'E-mail ou senha não conferem. Use Esqueci minha senha para redefinir o acesso.';
  if(path==='/auth/v1/verify')return 'Não foi possível validar o código. Confira o e-mail e o código recebido.';
  if(path==='/auth/v1/recover')return 'Não foi possível enviar o e-mail de recuperação. Tente novamente mais tarde ou contate o suporte.';
  if(path==='/auth/v1/user')return 'Não foi possível salvar a nova senha. Confira os campos e tente novamente.';
  if(path.startsWith('/auth/'))return 'Não foi possível concluir o cadastro. Confira os campos ou use a recuperação de senha se já possui conta.';
  return data?.message||data?.error||'Não foi possível concluir.';
 }
 function createRecovery(config,transport=globalThis.fetch){
  let verified=null;
  async function call(path,body,method='POST',token=''){
   let r;try{r=await transport(config.url+path,{method,headers:{apikey:config.publishable_key,'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});}catch{throw Error('Não foi possível conectar. Confira sua internet e tente novamente.');}
   let d;try{d=await r.json();}catch{throw Error('O serviço retornou uma resposta inválida. Tente novamente.');}
   if(!r.ok){if(r.status===401&&token)verified=null;throw Error(errorMessage(path,d,r.status));}return d;
  }
  return {
   clear(){verified=null;},
   async send(value){verified=null;const target=email(value);if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(target))throw Error('Informe um e-mail válido.');await call('/auth/v1/recover',{email:target});return {ok:true};},
   async verify(value,code){
    verified=null;const target=email(value),raw=String(code||'').trim();let payload;
    if(/^\d{6,10}$/.test(raw.replace(/\s/g,'')))payload={email:target,token:raw.replace(/\s/g,''),type:'recovery'};
    else{let url;try{url=new URL(raw);}catch{throw Error('Cole o endereço do botão de recuperação recebido por e-mail.');}if(url.origin!==config.url||url.pathname!=='/auth/v1/verify'||url.searchParams.get('type')!=='recovery')throw Error('Use o link de recuperação enviado para este painel.');const token=url.searchParams.get('token_hash')||url.searchParams.get('token');if(!token||!/^[a-zA-Z0-9_-]{20,300}$/.test(token))throw Error('Link de recuperação inválido. Solicite outro.');payload={token_hash:token,type:'recovery'};}
    const d=await call('/auth/v1/verify',payload);if(!d.access_token||email(d.user?.email)!==target)throw Error('Não foi possível conferir o titular da recuperação. Solicite outro link.');verified={token:d.access_token,until:Date.now()+Math.min(Number(d.expires_in)||600,600)*1000};return {ok:true};
   },
   async acceptToken(token){verified=null;if(typeof token!=='string'||token.length>8192||!/^eyJ[A-Za-z0-9_.-]+$/.test(token))throw Error('Link inválido. Solicite uma nova recuperação.');const d=await call('/auth/v1/user',undefined,'GET',token);if(!d.id||!d.email)throw Error('Não foi possível conferir a recuperação.');verified={token,until:Date.now()+600000};return {ok:true};},
   async update(password,repeat){if(typeof password!=='string'||password.length<10||password.length>128)throw Error('Use uma senha de 10 a 128 caracteres.');if(password!==repeat)throw Error('As duas senhas precisam ser iguais.');if(!verified||Date.now()>=verified.until){verified=null;throw Error('A autorização venceu. Solicite outro código de recuperação.');}await call('/auth/v1/user',{password},'PUT',verified.token);verified=null;return {ok:true};}
  };
 }
 return {email,errorMessage,createRecovery};
});
