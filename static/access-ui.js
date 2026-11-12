'use strict';
let accessView='login';
const accessLabels={pending:'Aguardando aprovação',approved:'Aprovada',rejected:'Reprovada',suspended:'Suspensa'};
const accessDate=v=>v?String(v).slice(0,10).split('-').reverse().join('/'):'Sem validade liberada';
async function accessCall(action,p={}){
 const r=await fetch('/api/access',{method:'POST',headers:{'Content-Type':'application/json','X-VF-CSRF':S.csrf},body:JSON.stringify({action,...p})});
 const d=await r.json();if(!r.ok)throw Error(d.error||'Não foi possível concluir.');return d;
}
function accessLogin(){
 const signup=accessView==='signup',recovery=accessView==='recovery';
 return `<div class="login-wrapper"><div class="login-card access-card"><div class="login-brand"><strong>vf<span>e</span><sup>✣</sup></strong><small>EMISSOR DE NF-e</small></div><h2>${signup?'Solicitar acesso':recovery?'Recuperar acesso':'Bem-vindo ao VF Emissor'}</h2><p class="login-subtitle">${signup?'Sua conta e o CNPJ serão liberados pela administração.':recovery?'Solicite um código ao suporte pelo seu contato já cadastrado.':'Entre na sua conta e escolha a empresa para trabalhar.'}</p><form id="access-form" data-mode="${accessView}">${signup?'<label class="field">Seu nome<input name="name" required maxlength="200" autocomplete="name"></label>':''}${!recovery?'<label class="field">E-mail<input name="email" type="email" required maxlength="254" autocomplete="username"></label>':'<label class="field">Código de recuperação<input name="code" required autocomplete="off"></label>'}<label class="field">${recovery?'Nova senha':'Senha'}<input name="password" type="password" required ${signup||recovery?'minlength="10" maxlength="128"':''} autocomplete="${signup||recovery?'new-password':'current-password'}"></label>${signup?'<label class="field">CNPJ da primeira empresa<input name="cnpj" required inputmode="numeric" maxlength="18" placeholder="Somente números"></label><label class="field">Razão social<input name="company_name" required minlength="2" maxlength="200"></label>':''}<button class="primary login-submit-btn" type="submit">${signup?'Enviar para aprovação':recovery?'Salvar nova senha':'Entrar'}</button></form><div class="access-links"><button data-action="access-view" data-view="${signup||recovery?'login':'signup'}">${signup||recovery?'Voltar para entrar':'Criar conta'}</button>${!signup&&!recovery?'<button data-action="access-view" data-view="recovery">Esqueci minha senha</button>':''}</div><small class="login-footnote">Seus XML e certificados continuam neste computador. O acesso de cada empresa depende de aprovação e validade.</small></div></div>`;
}
function accessHome(){
 const a=S.access.account;
 return `<section class="access-home"><header class="access-home-head"><div><span class="access-eyebrow">SUA CONTA</span><h1>Minhas empresas</h1><p>${esc(a.name)} · ${esc(a.email)}</p></div><button data-action="logout">Sair da conta</button></header><div class="access-account-state"><span class="badge ${a.status==='approved'?'ok':'wait'}">Conta ${esc(accessLabels[a.status]||a.status)}</span><button data-action="access-refresh">Atualizar situação</button></div>${a.status!=='approved'?notice('Sua conta está '+esc((accessLabels[a.status]||a.status).toLowerCase())+'. A administração confere seu cadastro e a autorização de cada empresa.','warning'):''}<div class="access-company-grid">${(a.companies||[]).map(c=>`<article class="access-company"><span class="badge ${c.status==='approved'?'ok':'wait'}">${esc(accessLabels[c.status]||c.status)}</span><h2>${esc(c.name)}</h2><p>CNPJ ${esc(c.cnpj)}</p><p>Vencimento: <strong>${accessDate(c.valid_until)}</strong></p><small>Até ${Number(c.max_devices)} computadores autorizados</small>${c.ever_approved?`<button class="primary" data-action="access-select" data-id="${esc(c.id)}">Abrir empresa neste computador</button>`:'<p class="hint">Aguardando liberação da administração.</p>'}</article>`).join('')||'<article class="access-company"><h2>Adicione sua empresa</h2><p>Solicite a autorização do CNPJ abaixo.</p></article>'}</div>${['pending','approved'].includes(a.status)?`<section class="section"><h2>Solicitar outro CNPJ</h2><form id="access-company-form" class="access-request"><label class="field">CNPJ<input name="cnpj" required inputmode="numeric" maxlength="18"></label><label class="field">Razão social<input name="name" required minlength="2" maxlength="200"></label><button class="primary" type="submit">Solicitar liberação</button></form></section>`:''}<p class="hint">Os cadastros fiscais e XML são locais. Em outro computador, configure a empresa e restaure seu backup quando necessário.</p></section>`;
}
const renderBeforeAccess=render;render=function(){
 document.querySelectorAll('.access-license-banner').forEach(el=>el.remove());
 if(S.access?.enabled&&!S.authenticated){
  document.body.classList.add('auth-mode');$('#content').innerHTML=S.access.account?accessHome():accessLogin();return;
 }
 renderBeforeAccess();
 if(S.access?.enabled&&S.authenticated){
  $('.account').insertAdjacentHTML('beforeend','<button class="access-switch" data-action="access-home">Minhas empresas</button>');
  const l=S.access.license;
  $('#scope-banner').insertAdjacentHTML('afterend',`<div class="access-license-banner ${l.can_emit?'':'restricted'}">${l.can_emit?'Assinatura liberada':'Novas emissões bloqueadas · consultas e backups disponíveis'} · Vencimento ${accessDate(l.valid_until)}${l.offline?' · Autorização temporária sem conexão':''}</div>`);
 }
};
const loginBeforeAccess=renderLogin;renderLogin=function(){return loginBeforeAccess()+`<div class="access-legacy-config"><button data-action="access-configure">Configurar acesso por e-mail</button></div>`;};
const generalBeforeAccess=configGeneral;configGeneral=function(){return generalBeforeAccess()+configCard('Conta e acesso',S.access?.enabled?`<p>${esc(S.access.account.email)} · validade desta empresa: ${accessDate(S.access.license.valid_until)}</p><button data-action="access-home">Minhas empresas e solicitações</button>${S.access.account.is_admin?'<button data-action="access-admin">Gestão de acessos</button>':''}`:'<p>Ative a conta por e-mail quando o serviço de aprovação estiver pronto. A ativação preserva os dados locais e exige uma licença aprovada para cada CNPJ.</p><button data-action="access-configure">Configurar acesso por e-mail</button>');};
handlers['access-admin']=()=>window.open('/gestao/','_blank','noopener');
const partyBeforeAccess=partyFields;partyFields=function(o={},company=false){let html=partyBeforeAccess(o,company);if(company&&S.access?.enabled){const template=document.createElement('template');template.innerHTML=html;template.content.querySelector('[name="password"]')?.closest('label')?.remove();html=template.innerHTML;}return html;};
handlers['access-view']=b=>{accessView=b.dataset.view;render();};
handlers['access-refresh']=async()=>{await accessCall('profile');await refresh();toast('Situação atualizada.');};
handlers['access-home']=async()=>{if($('#note-modal'))throw Error('Salve e feche a edição da nota antes de trocar de empresa.');await accessCall('home');draft=null;itemDraft=null;selected='';$('#modal-root').innerHTML='';await refresh('');};
handlers['access-select']=async b=>{const result=await accessCall('select',{id:b.dataset.id});await refresh();if(result.created){editCatalog('company',result.cid);toast('Complete os dados fiscais desta empresa.');}};
const newCompanyBeforeAccess=handlers['new-company'];handlers['new-company']=b=>S.access?.enabled?handlers['access-home']():newCompanyBeforeAccess(b);
handlers['access-configure']=()=>{dialog('access-config-modal','Ativar acesso por e-mail',`<p>Use o arquivo de configuração pública fornecido pela administração. Cada CNPJ existente precisará estar aprovado na sua conta. Faça um backup antes da ativação.</p><label class="field">Arquivo de configuração pública (.json)<input id="access-config-file" type="file" accept=".json"></label><label class="check"><input id="access-config-ack" type="checkbox">Tenho minha conta e meus CNPJs aprovados e preservei meu backup.</label>`,`<button data-action="close-dialog" data-id="access-config-modal">Voltar</button><button class="primary" data-action="access-config-save">Ativar novo acesso</button>`,'small');};
handlers['access-config-save']=async()=>{const f=$('#access-config-file').files[0];if(!f||f.size>8192||!$('#access-config-ack').checked)throw Error('Selecione a configuração pública e confirme a preparação.');await accessCall('configure',{config:JSON.parse(await f.text())});$('#modal-root').innerHTML='';await refresh('');toast('Acesso por e-mail ativado. Entre na sua conta.');};
document.addEventListener('submit',async e=>{
 const f=e.target;if(!['access-form','access-company-form'].includes(f.id))return;e.preventDefault();
 const button=f.querySelector('button[type="submit"]');if(button.disabled)return;button.disabled=true;
 try{const p=Object.fromEntries(new FormData(f));
  if(f.id==='access-company-form'){await accessCall('request_company',p);toast('CNPJ enviado para aprovação.');}
  else if(f.dataset.mode==='recovery'){await accessCall('finish_recovery',p);accessView='login';toast('Senha alterada. Entre novamente.');}
  else{await accessCall(f.dataset.mode==='signup'?'signup':'login',p);toast(f.dataset.mode==='signup'?'Solicitação enviada para aprovação.':'Conta acessada.');}
  f.querySelector('[name="password"]')?.setAttribute('value','');await refresh('');
 }catch(err){toast(err.message,true);}finally{const pw=f.querySelector('[name="password"]');if(pw)pw.value='';button.disabled=false;}
});
if(S.version)render();
