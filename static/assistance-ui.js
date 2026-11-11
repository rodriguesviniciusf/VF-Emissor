'use strict';
// Cadastros assistidos e cópias de edição; estes fluxos não transmitem NF-e.
let municipalityPromise,lookupReview=null;
const assistanceNormalize=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toLocaleLowerCase('pt-BR');
const assistanceUuid=()=>crypto.randomUUID().replaceAll('-','');
const assistanceInput=(form,name)=>form?.querySelector(`[name="${name}"]`);
const assistanceValue=(form,name)=>assistanceInput(form,name)?.value||'';
async function municipalities(){
 if(!municipalityPromise)municipalityPromise=fetch('/municipios.json').then(async r=>{if(!r.ok)throw Error('Não foi possível abrir a tabela de municípios. O preenchimento manual está disponível.');return r.json();}).catch(e=>{municipalityPromise=null;throw e;});
 return municipalityPromise;
}
partyFields=function(o={},isCompany=false){o=o||{};return `<div class="assistance-intro"><span class="assistance-icon">⌕</span><div><b>Cadastro com preenchimento assistido</b><p>Pesquise a cidade para preencher o IBGE. CEP e CNPJ permitem conferir os dados encontrados antes de aplicar.</p></div></div><div class="grid">${field('CNPJCPF','CPF/CNPJ',o)}<div class="field lookup-tool"><span>Dados cadastrais</span><button type="button" data-action="lookup-cnpj">Consultar CNPJ</button><small>Consulta pontual pela BrasilAPI.</small></div>${field('xNome','Razão social / Nome',o,'span2')}${field('fantasia','Nome fantasia',o)}${field('IE','Inscrição estadual',o)}${isCompany?select('CRT','Regime tributário',[['1','1 — Simples Nacional'],['3','3 — Regime Normal (Lucro Real / Presumido)']],o):select('indIEDest','Indicador da IE do destinatário',customSelectLists.indIEDest,o)}${field('Email','E-mail',o)}${field('Fone','Telefone',o)}${field('CEP','CEP (8 dígitos)',o)}<div class="field lookup-tool"><span>Endereço</span><button type="button" data-action="lookup-cep">Buscar CEP</button><small>O CEP informado é consultado no ViaCEP.</small></div>${field('xLgr','Logradouro',o,'span2')}${field('nro','Número',o)}${field('xCpl','Complemento',o)}${field('xBairro','Bairro',o)}${select('UF','UF','AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' '),o)}${field('xMun','Município — digite para pesquisar',o)}${field('cMun','Código IBGE (7 dígitos)',o)}${isCompany?`<label class="field">Senha de acesso (login da empresa)<input type="password" name="password" placeholder="${o?._id?'Deixe em branco para manter a atual':'Defina uma senha de acesso'}" autocomplete="new-password"></label>`:''}</div><p class="hint city-helper">Selecione a UF e escolha o município. A tabela do IBGE funciona sem internet.</p><div class="lookup-status" role="status" aria-live="polite"></div><p class="hint">A consulta envia somente o CEP ou CNPJ informado ao serviço indicado. IE, regime e tributação permanecem para sua conferência. Dados podem estar incompletos ou desatualizados.</p>`;};
async function prepareCity(form){
 const city=assistanceInput(form,'xMun');if(!city)return;
 const data=await municipalities();if(!form.isConnected)return;
 let list=form.querySelector('datalist[data-cities]');if(!list){list=document.createElement('datalist');list.dataset.cities='1';list.id='cities-'+assistanceUuid();form.append(list);city.setAttribute('list',list.id);city.setAttribute('autocomplete','off');city.setAttribute('aria-description','Escolha a UF e um município da lista para preencher o código IBGE.');}
 const uf=assistanceValue(form,'UF').toUpperCase();if(list.dataset.uf!==uf){list.dataset.uf=uf;list.innerHTML=data.municipalities.filter(r=>r[2]===uf).map(r=>`<option value="${esc(r[1])}">${esc(r[2])} · IBGE ${r[0]}</option>`).join('');}
 return data;
}
async function resolveCity(form,fromCode=false){
 const data=await prepareCity(form);if(!data||!form.isConnected)return;
 const name=assistanceInput(form,'xMun'),code=assistanceInput(form,'cMun'),uf=assistanceInput(form,'UF');if(!name||!uf)return;
 const found=data.municipalities.find(r=>fromCode?r[0]===code?.value.trim():r[2]===uf.value.toUpperCase()&&assistanceNormalize(r[1])===assistanceNormalize(name.value));
 if(found){name.value=found[1];uf.value=found[2];if(code)code.value=found[0];const hint=form.querySelector('.city-helper');if(hint)hint.textContent=`Município identificado: ${found[1]} / ${found[2]} · IBGE ${found[0]}.`;}
 else if(!fromCode){if(code)code.value='';const hint=form.querySelector('.city-helper');if(hint)hint.textContent='Escolha um município da lista da UF para preencher o IBGE. O preenchimento manual continua disponível.';}
}
function lookupStatus(form,message,bad=false){const el=form?.querySelector('.lookup-status');if(el){el.textContent=message;el.classList.toggle('error',bad);}}
const lookupNames={xNome:'Razão social / Nome',fantasia:'Nome fantasia',CNPJCPF:'CNPJ',Email:'E-mail',Fone:'Telefone',CEP:'CEP',xLgr:'Logradouro',nro:'Número',xCpl:'Complemento',xBairro:'Bairro'};
function proposalRows(form,fields){
 const rows=[];for(const [key,label] of Object.entries(lookupNames)){if(!fields[key]||!assistanceInput(form,key))continue;const before=assistanceValue(form,key);if(before!==String(fields[key]))rows.push({label,fields:{[key]:String(fields[key])},before,after:String(fields[key])});}
 if(fields.xMun&&fields.UF){const f={xMun:fields.xMun,UF:fields.UF};if(assistanceInput(form,'cMun'))f.cMun=fields.cMun||'';const before=Object.keys(f).map(k=>assistanceValue(form,k)).join(' / '),after=Object.values(f).join(' / ');if(before!==after)rows.push({label:'Município / UF / IBGE',fields:f,before,after});}return rows;
}
function reviewLookup(form,result,kind,key){
 const rows=proposalRows(form,result.fields);lookupReview={form,result,kind,key,rows,cid:S.cid||'',baseline:Object.fromEntries(rows.flatMap(r=>Object.keys(r.fields)).map(k=>[k,assistanceValue(form,k)]))};
 dialog('lookup-review',kind==='cnpj'?'Conferir dados do CNPJ':'Conferir endereço pelo CEP',`<div class="assistance-intro"><span class="assistance-icon">✓</span><div><b>Confira antes de preencher</b><p>${esc(result.provider)} · consulta ${esc(new Date(result.queried_at).toLocaleString('pt-BR'))}${result.cached?' · resultado reutilizado nesta sessão':''}</p></div></div>${Object.keys(result.details||{}).length?`<div class="lookup-details">${Object.entries(result.details).map(([k,v])=>`<p><small>${esc(k)}</small><b>${esc(v)}</b></p>`).join('')}</div>`:''}${rows.length?`<p>Marque os dados que deseja aplicar. Campos já preenchidos só serão substituídos com sua confirmação.</p><div class="table-wrap"><table class="lookup-table"><thead><tr><th>Aplicar</th><th>Campo</th><th>Atual</th><th>Encontrado</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td><input type="checkbox" checked data-lookup-row="${i}" aria-label="Aplicar ${esc(r.label)}"></td><td>${esc(r.label)}</td><td>${esc(r.before||'Vazio')}</td><td><b>${esc(r.after||'Não informado')}</b></td></tr>`).join('')}</tbody></table></div>`:notice('Os dados disponíveis já coincidem com o cadastro.')}<p class="hint">A aplicação preenche apenas este formulário. Use Salvar para gravar o cadastro. IE, regime e tributação não são alterados.</p>`,`<button data-action="close-dialog" data-id="lookup-review">Voltar</button>${rows.length?'<button class="primary" data-action="apply-lookup">Aplicar dados selecionados</button>':''}`,'medium');
}
async function runLookup(form,kind){
 if(!form)return;const input=assistanceInput(form,kind==='cep'?'CEP':'CNPJCPF');if(!input)return;
 clearTimeout(form.cepTimer);if(form.dataset.lookupBusy==='1')return;form.dataset.lookupBusy='1';
 const key=input.value.trim(),cid=S.cid||'',token=assistanceUuid();form.dataset.lookupRequest=token;lookupStatus(form,'Consultando '+(kind==='cep'?'CEP no ViaCEP…':'CNPJ na BrasilAPI…'));
 try{const r=await api('lookup_public',{kind,value:key});if(!form.isConnected||form.dataset.lookupRequest!==token||input.value.trim()!==key||(S.cid||'')!==cid)return;lookupStatus(form,'Consulta concluída. Confira a prévia antes de aplicar.');reviewLookup(form,r,kind,key);}
 catch(e){if(form.isConnected&&form.dataset.lookupRequest===token)lookupStatus(form,e.message,true);throw e;}
 finally{form.dataset.lookupBusy='0';if(form.isConnected&&input.value.trim()!==key)lookupStatus(form,'O número foi alterado. Consulte novamente para conferir os dados atuais.');}
}
handlers['lookup-cnpj']=b=>runLookup(b.closest('form'),'cnpj');handlers['lookup-cep']=b=>runLookup(b.closest('form'),'cep');
handlers['apply-lookup']=async()=>{
 const p=lookupReview;if(!p||!p.form.isConnected||(S.cid||'')!==p.cid)throw Error('O cadastro mudou. Consulte novamente.');
 if(assistanceValue(p.form,p.kind==='cep'?'CEP':'CNPJCPF').trim()!==p.key)throw Error('O número consultado foi alterado. Consulte novamente.');
 for(const [k,v] of Object.entries(p.baseline))if(assistanceValue(p.form,k)!==v)throw Error('O formulário mudou após a consulta. Feche esta prévia e consulte novamente.');
 const fields={};$$('#lookup-review [data-lookup-row]:checked').forEach(el=>Object.assign(fields,p.rows[Number(el.dataset.lookupRow)].fields));
 for(const [k,v] of Object.entries(fields)){const el=assistanceInput(p.form,k);if(el)el.value=v;}
 closeDialog('lookup-review');lookupStatus(p.form,'Dados aplicados ao formulário. Confira e clique em Salvar.');lookupReview=null;await prepareCity(p.form);toast('Dados preenchidos para conferência.');
};
document.addEventListener('focusin',e=>{if(['xMun','UF','cMun'].includes(e.target.name))prepareCity(e.target.form).catch(err=>toast(err.message,true));});
document.addEventListener('input',e=>{const t=e.target,form=t.form;if(!form)return;
 if(t.name==='xMun')resolveCity(form).catch(err=>lookupStatus(form,err.message,true));
 if(t.name==='cMun'&&/^\d{7}$/.test(t.value.trim()))resolveCity(form,true).catch(err=>lookupStatus(form,err.message,true));
 if(t.name==='CEP'&&assistanceInput(form,'CNPJCPF')){clearTimeout(form.cepTimer);if(/^\d{5}-?\d{3}$/.test(t.value.trim()))form.cepTimer=setTimeout(()=>{if(form.isConnected&&!$('#lookup-review'))runLookup(form,'cep').catch(()=>{});},900);}
});
document.addEventListener('change',e=>{if(e.target.name==='UF'&&assistanceInput(e.target.form,'xMun'))resolveCity(e.target.form).catch(err=>lookupStatus(e.target.form,err.message,true));});

let editingSession=null,editorTimer=null,editorBusy=null,editorManual=false;
function editorPayload(){
 if(!editingSession||!$('#note-form')||editingSession.cid!==S.cid)return null;
 const n=structuredClone(currentDraft());for(const k of Object.keys(n))if(k.startsWith('_'))delete n[k];
 const pending=$('#item-form')?gather($('#item-form'),itemDraft):null;
 return {note:n,pending_item:pending,item_index:pending?itemIndex:-1,tax_tab:pending?taxTab:'icms'};
}
function editorStatus(message,bad=false){const el=$('#editor-autosave-status');if(el){el.textContent=message;el.classList.toggle('error',bad);}}
function appendEditorStatus(){
 if(!$('#note-modal')||$('#editor-autosave-status'))return;
 const top=document.createElement('div');top.className='editor-autosave';top.innerHTML='<span class="autosave-dot"></span><div><b>Cópia automática neste computador</b><span id="editor-autosave-status" role="status" aria-live="polite">As alterações são guardadas após uma breve pausa na digitação.</span></div><button type="button" class="text-btn" data-action="retry-editor-save">Salvar cópia agora</button>';$('#note-modal .dialog-body').prepend(top);
 const close=$('#note-modal .dialog-foot [data-action="close-note"]');if(close)close.textContent='Guardar e voltar';
}
function initializeEditor(source='',base='',restored=null){
 editingSession={id:restored&&!restored.as_new?restored.id:assistanceUuid(),cid:S.cid,environment:draft.environment,source_id:source,base_revision:base,version:restored&&!restored.as_new?restored.version:0,last:'',pendingWrite:null};editingSession.last=restored?'':JSON.stringify(editorPayload());appendEditorStatus();
 if(restored){editorStatus('Cópia recuperada. Confira os dados e a data antes de salvar ou enviar.');queueEditorSave();}
}
function queueEditorSave(){if(editorManual||!editingSession)return;clearTimeout(editorTimer);editorTimer=setTimeout(()=>flushEditor().catch(()=>{}),900);}
async function flushEditor(){
 clearTimeout(editorTimer);if(editorManual||!editingSession||!$('#note-form'))return;
 if(editorBusy){await editorBusy;if(editingSession&&$('#note-form'))return flushEditor();return;}
 const context=editingSession,payload=editorPayload();if(!payload)return;
 if(JSON.stringify(payload)===context.last&&!context.pendingWrite)return;
 const request=context.pendingWrite||{...payload,id:context.id,version:context.version,write_id:assistanceUuid(),source_id:context.source_id,base_revision:context.base_revision,cid:context.cid};
 const saved=JSON.stringify({note:request.note,pending_item:request.pending_item,item_index:request.item_index,tax_tab:request.tax_tab});context.pendingWrite=request;editorStatus('Salvando cópia no banco local…');
 editorBusy=(async()=>{try{const r=await apiBeforeAssistance('editor_save',request);context.version=r.version;context.last=saved;context.pendingWrite=null;if(editingSession===context)editorStatus('Salvo neste PC às '+new Date(r.updated).toLocaleTimeString('pt-BR')+'. Não transmite nem reserva numeração.');}catch(e){if(editingSession===context)editorStatus('Cópia ainda não confirmada: '+e.message,true);throw e;}})();
 try{await editorBusy;}finally{editorBusy=null;}
 if(editingSession===context&&JSON.stringify(editorPayload())!==context.last)queueEditorSave();
}
const renderNoteBeforeAssistance=renderNote;renderNote=function(){renderNoteBeforeAssistance();appendEditorStatus();queueEditorSave();};
const renderItemsBeforeAssistance=renderItems;renderItems=function(){renderItemsBeforeAssistance();queueEditorSave();};
const openNoteBeforeAssistance=openNote;
openNote=async function(id='',n=null){
 if(editingSession&&$('#note-form'))await flushEditor();
 editingSession=null;closeDialog('item-modal');await openNoteBeforeAssistance(id,n);if(!$('#note-form'))return;
 const original=id?(S.documents||[]).find(d=>d._id===id):null;initializeEditor(id,original?._edit_revision||n?._edit_revision||'');
};
handlers['new-note']=()=>openNote();handlers['edit-note']=b=>openNote(b.dataset.id);
const apiBeforeAssistance=api;
api=async function(command,p={}){
 if(command!=='save_note'||!editingSession||!$('#note-form'))return apiBeforeAssistance(command,p);
 try{await flushEditor();}catch(e){/* A gravação manual permanece disponível se a cópia falhar. */}
 const context=editingSession;editorManual=true;
 try{const result=await apiBeforeAssistance(command,p);
  if(context.version){try{await apiBeforeAssistance('editor_drop',{id:context.id,version:context.version,cid:context.cid});}catch(e){toast('NF-e salva. A cópia anterior continua na recuperação: '+e.message,true);}}
  if(editingSession===context){draft._id=result.id;initializeEditor(result.id,result.revision||'');}return result;
 }finally{editorManual=false;}
};
handlers['retry-editor-save']=()=>flushEditor();
handlers['close-note']=async()=>{if($('#item-form'))throw Error('Salve ou volte do produto em edição antes de fechar a NF-e.');await flushEditor();closeDialog('note-modal');editingSession=null;await refresh();toast('As cópias confirmadas ficam disponíveis em Recuperar rascunhos.');};
const logoutBeforeAssistance=handlers.logout;handlers.logout=async b=>{if(editingSession&&$('#note-form'))await flushEditor();await logoutBeforeAssistance(b);if(S.authenticated===false){$('#modal-root').replaceChildren();editingSession=null;lookupReview=null;}};
handlers['recover-editors']=async()=>{
 const r=await api('editor_list');S.editing_drafts=r.copies;
 dialog('recover-editors','Recuperar rascunhos de edição',`<p>Somente ${esc(S.company.xNome)} · ${envName(S.company.environment)} · cópias guardadas neste PC.</p>${notice('Estas cópias preservam a edição. Não são documentos autorizados e não reservam numeração fiscal.')}<div class="table-wrap"><table><thead><tr><th>Última cópia</th><th>Documento</th><th>Conteúdo</th><th></th></tr></thead><tbody>${r.copies.map(c=>`<tr><td>${esc(new Date(c.updated).toLocaleString('pt-BR'))}</td><td>${c.source_id?'NF-e '+esc(c.number||'em edição'):'Nova NF-e'}${!c.can_resume?'<br><small>A nota original mudou. Confira uma nova cópia.</small>':''}</td><td>${c.items} itens${c.has_pending_item?' + produto em edição':''}</td><td><div class="row-actions">${c.can_resume?`<button class="primary" data-action="resume-editor" data-id="${c.id}">Recuperar edição</button>`:''}<button data-action="clone-editor" data-id="${c.id}">Recuperar como nova</button><button class="text-btn danger-text" data-action="drop-editor" data-id="${c.id}" data-version="${c.version}">Descartar cópia</button></div></td></tr>`).join('')||'<tr><td colspan="4">Nenhuma cópia automática neste ambiente.</td></tr>'}</tbody></table></div><p class="hint">Uma cópia de nota alterada ou finalizada não substitui a nota original. Ao recuperar como nova, identificação e revisões fiscais são renovadas. Descartar uma cópia não exclui a NF-e salva.</p>`,`<button data-action="close-dialog" data-id="recover-editors">Voltar</button>`,'medium');
};
async function resumeEditor(id,asNew){
 if(editingSession&&$('#note-form'))await flushEditor();const r=await api('editor_restore',{id,as_new:asNew});closeDialog('recover-editors');editingSession=null;closeDialog('item-modal');
 r.note._status=(S.documents||[]).find(n=>n._id===r.source_id)?._status||'RASCUNHO';await openNoteBeforeAssistance(r.source_id||'',r.note);initializeEditor(r.source_id||'',r.base_revision||'',r);
 if(r.pending_item){itemDraft=structuredClone(r.pending_item);itemIndex=r.item_index;taxTab=r.tax_tab||'icms';renderItem();queueEditorSave();toast('Recuperamos também o produto em edição. Confira e salve o produto na nota.');}else toast('Edição recuperada. Confira os dados antes de concluir.');
}
handlers['resume-editor']=b=>resumeEditor(b.dataset.id,false);handlers['clone-editor']=b=>resumeEditor(b.dataset.id,true);
handlers['drop-editor']=async b=>{if(!confirm('Descartar somente esta cópia automática? A NF-e salva e os XML serão preservados.'))return;await api('editor_drop',{id:b.dataset.id,version:Number(b.dataset.version)});await handlers['recover-editors']();await refresh();};
for(const event of ['input','change'])document.addEventListener(event,e=>{if(e.target.closest('#note-form,#item-form'))queueEditorSave();});
document.addEventListener('click',e=>{if(e.target.closest('#item-modal [data-action="close-dialog"]'))setTimeout(queueEditorSave,0);});
setInterval(()=>{if(editingSession&&$('#note-form')&&!editorManual)flushEditor().catch(()=>{});},10000);
window.addEventListener('pagehide',()=>{
 if(!editingSession||editorBusy||editorManual)return;const payload=editorPayload();if(!payload||JSON.stringify(payload)===editingSession.last)return;
 const body=JSON.stringify({action:'editor_save',cid:editingSession.cid,...payload,id:editingSession.id,version:editingSession.version,write_id:assistanceUuid(),source_id:editingSession.source_id,base_revision:editingSession.base_revision});
 if(new TextEncoder().encode(body).length<60000)fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-VF-CSRF':S.csrf},body,keepalive:true}).catch(()=>{});
});
function companyAttention(){
 const alerts=[],certificate=S.certificate,now=Date.now(),cfg=S.features||{};
 if(S.certificate_error)alerts.push({text:S.certificate_error,tab:'certificado',label:'Conferir A1',bad:true});
 else if(certificate?.expires){const delta=Date.parse(certificate.expires)-now,days=Math.ceil(delta/86400000);if(Number.isFinite(days)&&days<=30)alerts.push({text:delta<0?'O certificado A1 está vencido.':`O certificado A1 vence em ${days} dia${days===1?'':'s'}.`,tab:'certificado',label:'Conferir A1',bad:days<=7});}
 const backupError=(S.service_errors||[]).find(e=>e.service==='backup'),stamp=Date.parse(S.backup_status?.last_backup||'');
 if(backupError)alerts.push({text:backupError.error,tab:'backup',label:'Conferir backup',bad:true});
 else if(cfg.backup_enabled==='1'&&(!Number.isFinite(stamp)||now-stamp>Number(cfg.backup_hours||24)*3600000))alerts.push({text:Number.isFinite(stamp)?'O backup automático desta empresa está atrasado.':'O primeiro backup automático desta empresa ainda está pendente.',tab:'backup',label:'Fazer backup',bad:true});
 if(cfg.drive_enabled==='1'&&Number(S.drive_status?.pending||0)>0)alerts.push({text:`Há ${S.drive_status.pending} pendência(s) de cópia de XML para a pasta do Drive. Os originais continuam no PC.`,tab:'operacoes',label:'Conferir cópias',bad:true});
 const copies=S.editing_drafts||[];if(!alerts.length&&!copies.length)return '';
 return `<section class="attention-panel"><div class="attention-heading"><div><span class="hero-eyebrow">ACOMPANHAMENTO DA EMPRESA</span><h2>Continue com tudo em dia</h2></div><small>${envName(S.company.environment)}</small></div><div class="attention-items">${copies.length?`<article><span class="attention-symbol">↻</span><div><b>${copies.length} cópia${copies.length===1?'':'s'} de edição disponível${copies.length===1?'':'is'}</b><p>Retome a NF-e e os produtos que ficaram em edição neste computador.</p></div><button class="primary" data-action="recover-editors">Recuperar rascunhos</button></article>`:''}${alerts.map(a=>`<article class="${a.bad?'attention-warning':''}"><span class="attention-symbol">!</span><div><p>${esc(a.text)}</p></div><button data-action="attention-config" data-tab="${a.tab}">${esc(a.label)}</button></article>`).join('')}</div></section>`;
}
handlers['attention-config']=b=>{configTab=b.dataset.tab;location.hash='configuracoes';render();};
function decorateAddressSettings(){
 for(const form of $$('#general-settings,#accountant-settings')){if(form.querySelector('.lookup-status'))continue;
  const tools=document.createElement('div');tools.className='assistance-intro';tools.innerHTML=`<div><b>Preenchimento assistido</b><p>Pesquisa de cidade com IBGE offline. Confira os dados encontrados antes de aplicar ao cadastro.</p><div class="actions"><button type="button" data-action="lookup-cep">Buscar CEP</button>${assistanceInput(form,'CNPJCPF')?'<button type="button" data-action="lookup-cnpj">Consultar CNPJ</button>':''}</div></div>`;form.prepend(tools);
  const helper=document.createElement('p');helper.className='hint city-helper';helper.textContent='Escolha a UF e o município. CEP é consultado no ViaCEP; CNPJ na BrasilAPI, quando solicitado.';form.append(helper);const status=document.createElement('div');status.className='lookup-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');form.append(status);
 }
}
// Geral reúne identidade, certificado e rotinas da empresa, mantendo os formulários separados.
const configGeneralBeforeUnified=configGeneral;
configGeneral=function(){return configGeneralBeforeUnified()+`<div id="general-certificate" class="general-settings-section" tabindex="-1">${configCertificate()}</div><div id="general-operations" class="general-settings-section" tabindex="-1">${operationalSettings()}</div>`;};
for(let i=configTabs.length-1;i>=0;i--)if(['certificado','operacoes'].includes(configTabs[i][0]))configTabs.splice(i,1);
handlers['attention-config']=b=>{const target={certificado:'general-certificate',operacoes:'general-operations'}[b.dataset.tab];configTab=target?'geral':b.dataset.tab;location.hash='configuracoes';render();if(target)requestAnimationFrame(()=>{const el=document.getElementById(target);el?.scrollIntoView({behavior:'smooth',block:'start'});el?.focus({preventScroll:true});});};
const renderBeforeAssistance=render;
render=function(){if(['certificado','operacoes'].includes(configTab))configTab='geral';renderBeforeAssistance();if(S.authenticated===false)return;decorateAddressSettings();if(page==='inicio'&&S.cid){const html=companyAttention();if(html){const hero=$('#content .workspace-metrics');if(hero)hero.insertAdjacentHTML('afterend',html);else $('#content').insertAdjacentHTML('afterbegin',html);}}};
if(S.version)render();
