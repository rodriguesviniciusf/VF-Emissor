'use strict';
const ncmDate=value=>value?String(value).slice(0,10).split('-').reverse().join('/'):'—';
function ncmWarnings(warnings=[]){return warnings.length?notice(`<b>Vigência do NCM: confira a data da tabela</b><ul>${warnings.map(w=>`<li>${esc(w.message)}</li>`).join('')}</ul>`,'warning'):'';}
function ncmSource(table){return `<small class="ncm-source">Receita Federal / Siscomex · tabela de ${ncmDate(table.reference_date)}${table.stale?' · cópia local: atualizar vigência':''}<br>${esc(table.act||'')} · <a href="${esc(table.official_page)}" target="_blank" rel="noopener noreferrer">Fonte oficial</a></small>`;}
function ncmResult(result){
 const valid=result.status==='valid',bad=['not_found','expired','not_started'].includes(result.status);
 const group=result.hierarchy.filter(r=>r.code.length>=5).map(r=>r.description).join(' › ');
 return `<div class="ncm-result ${valid?'ncm-valid':bad?'ncm-invalid':'ncm-pending'}"><div class="ncm-result-head"><b>${esc(result.formatted)}${result.description?' · '+esc(result.description):''}</b><span>${valid?'Vigente':bad?'Revisar NCM':'Conferir vigência'}</span></div>${group?`<p class="ncm-group">${esc(group)}</p>`:''}${result.hierarchy.length?`<details class="ncm-details"><summary>Ver classificação completa</summary><ol class="ncm-hierarchy">${result.hierarchy.map(r=>`<li><span>${esc(r.formatted)}</span>${esc(r.description)}</li>`).join('')}</ol></details>`:''}<p>${esc(result.message)}</p>${result.start?`<small>Início: ${ncmDate(result.start)} · Fim: ${result.end==='9999-12-31'?'sem término informado':ncmDate(result.end)} · Data da emissão: ${ncmDate(result.checked_date)}</small>`:''}${ncmSource(result.table)}<p class="hint">Confira se a descrição corresponde à mercadoria. Esta consulta não define a tributação do produto.</p></div>`;
}
let ncmTarget=null,ncmSearchTimer;
function attachNcmFields(){
 for(const input of $$('input[name="NCM"],input[name="product.NCM"]')){
  if(input.dataset.ncmAttached)return;input.dataset.ncmAttached='1';input.inputMode='numeric';input.maxLength=10;
  const wrapper=document.createElement('div');wrapper.className='ncm-helper';wrapper.innerHTML='<div class="ncm-actions"><button type="button" class="text-btn ncm-open-search">Pesquisar código ou descrição</button><button type="button" class="text-btn" data-action="ncm-refresh">Atualizar tabela oficial</button></div><div class="ncm-answer" role="status" aria-live="polite"></div>';
  const label=input.closest('label'),group=document.createElement('div');group.className='ncm-field';label.before(group);group.append(label,wrapper);
  const output=wrapper.querySelector('.ncm-answer');let sequence=0,timer;
  const lookup=async()=>{
   const seq=++sequence,code=input.value.trim(),cid=S.cid,issued_on=input.name==='product.NCM'?(draft?.issued_at||''):'';
   if(!/^(?:\d{8}|\d{4}\.\d{2}\.\d{2})$/.test(code)){output.innerHTML='<p class="hint">Digite os 8 dígitos para consultar descrição, grupo e vigência.</p>';return;}
   output.textContent='Consultando a tabela local…';
   try{const result=await api('ncm_lookup',{code,issued_on});if(seq===sequence&&input.isConnected&&input.value.trim()===code&&S.cid===cid)output.innerHTML=ncmResult(result);}
   catch(e){if(seq===sequence&&input.isConnected&&S.cid===cid)output.textContent=e.message;}
  };
  input.addEventListener('input',()=>{sequence++;clearTimeout(timer);timer=setTimeout(lookup,180);});
  input.addEventListener('change',lookup);
  input.addEventListener('blur',()=>{if(/^\d{4}\.\d{2}\.\d{2}$/.test(input.value))input.value=input.value.replaceAll('.','');});
  wrapper.querySelector('.ncm-open-search').addEventListener('click',()=>{
   ncmTarget={input,cid:S.cid};
   dialog('ncm-search-modal','Consultar NCM',`<p>Pesquise parte do código ou palavras da descrição. Selecione a classificação após conferir o grupo e a mercadoria.</p><label class="field">Código ou descrição<input id="ncm-search-query" placeholder="Ex.: camarões, larvas ou 0306" autocomplete="off"></label><p class="hint">Até 30 resultados por busca. Refine as palavras para localizar a mercadoria.</p><div id="ncm-search-results" role="status" aria-live="polite"></div>`,`<button data-action="ncm-refresh">Atualizar tabela oficial</button><button data-action="close-dialog" data-id="ncm-search-modal">Voltar</button>`,'medium');
  });
  input.ncmLookup=lookup;lookup();
 }
 for(const input of $$('input[name="nature"]')){
  if(input.dataset.natureAttached||input.closest('#nature-add-form'))continue;input.dataset.natureAttached='1';
  const id='nature-options-'+assistanceUuid();input.setAttribute('list',id);input.maxLength=60;
  input.insertAdjacentHTML('afterend',`<datalist id="${id}">${(S.natures||[]).map(n=>`<option value="${esc(n.name)}"></option>`).join('')}</datalist>`);
 }
}
let ncmFrame=0;
new MutationObserver(()=>{if(!ncmFrame)ncmFrame=requestAnimationFrame(()=>{ncmFrame=0;attachNcmFields();});}).observe(document.body,{childList:true,subtree:true});
attachNcmFields();
document.addEventListener('input',e=>{
 if(e.target.id==='ncm-search-query'){
  clearTimeout(ncmSearchTimer);const query=e.target.value,cid=S.cid,input=e.target;
  ncmSearchTimer=setTimeout(async()=>{
   const output=$('#ncm-search-results');if(!output)return;
   if(query.trim().length<2){output.textContent='Digite pelo menos dois caracteres.';return;}
   try{const result=await api('ncm_search',{query});if(!input.isConnected||input.value!==query||S.cid!==cid)return;
    output.innerHTML=`<div class="ncm-search-list">${result.results.map(r=>`<article><div><b>${esc(r.formatted)} · ${esc(r.description)}</b><p>${esc(r.context)}</p></div><button type="button" data-action="ncm-select" data-code="${r.code}">Usar NCM</button></article>`).join('')||'<p>Nenhum código encontrado nesta tabela. Refine a descrição ou atualize a fonte oficial.</p>'}</div>${ncmSource(result.table)}`;
   }catch(error){if(input.isConnected&&input.value===query&&S.cid===cid)output.textContent=error.message;}
  },250);
 }
 if(e.target.name==='issued_at')for(const input of $$('input[name="product.NCM"]'))input.ncmLookup?.();
});
handlers['ncm-select']=b=>{
 if(!ncmTarget?.input.isConnected||ncmTarget.cid!==S.cid)throw Error('Reabra o produto da empresa atual para escolher o NCM.');
 const input=ncmTarget.input;input.value=b.dataset.code;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));closeDialog('ncm-search-modal');input.focus();ncmTarget=null;
};
handlers['ncm-refresh']=async b=>{const cid=S.cid;b.disabled=true;try{const result=await api('ncm_refresh');if(S.cid!==cid)return;S.ncm_status=result;for(const input of $$('input[data-ncm-attached]'))input.ncmLookup?.();toast(result.error||result.message||'Tabela conferida.');}finally{if(b.isConnected)b.disabled=false;}};

function natureSettings(){return configCard('Naturezas de operação desta empresa',`<p>Organize as descrições oferecidas ao preencher a NF-e e os modelos do Modo Simples. A natureza não substitui o CFOP nem configura os impostos.</p><form id="nature-add-form"><div class="nature-add"><label class="field">Nova natureza de operação<input name="name" maxlength="60" placeholder="Ex.: REMESSA PARA INDUSTRIALIZAÇÃO" autocomplete="off"></label><button type="button" class="primary" data-action="nature-add">Adicionar natureza</button></div></form><div class="table-wrap"><table id="nature-table"><thead><tr><th>Natureza de operação</th><th></th></tr></thead><tbody>${(S.natures||[]).map(n=>`<tr><td>${esc(n.name)}</td><td><button class="text-btn danger-text" data-action="nature-delete" data-id="${n.id}">Excluir</button></td></tr>`).join('')||'<tr><td colspan="2">Nenhuma natureza cadastrada. Adicione as que a empresa utiliza.</td></tr>'}</tbody></table></div><p class="hint">Excluir remove a opção da lista desta empresa. Notas salvas, o padrão fiscal e modelos existentes mantêm o texto já informado.</p>`);}
const configFiscalBeforeNatures=configFiscal;
configFiscal=function(){return configFiscalBeforeNatures()+natureSettings();};
handlers['nature-add']=async()=>{const name=$('#nature-add-form [name=name]').value;await api('nature_save',{name});await refresh();toast('Natureza adicionada nesta empresa.');};
document.addEventListener('submit',e=>{if(e.target.id==='nature-add-form'){e.preventDefault();const button=e.target.querySelector('[data-action="nature-add"]');if(button&&!button.disabled)button.click();}});
handlers['nature-delete']=async b=>{const n=S.natures.find(n=>n.id===b.dataset.id);if(!n||!confirm(`Excluir “${n.name}” da lista desta empresa? Notas e modelos existentes serão preservados.`))return;await api('nature_delete',{id:n.id});await refresh();toast('Natureza excluída da lista.');};
handlers['entry-delete']=async b=>{const doc=S.received.find(n=>n._id===b.dataset.id);if(!doc)return;if(!confirm(`Excluir a importação da NF-e ${doc.number}, série ${doc.series}, de ${doc.issuer}?\n\nA nota sairá da listagem e do pacote contábil. O estoque vinculado será estornado. O XML local e o histórico serão preservados. Isso não cancela a NF-e na SEFAZ.`))return;await api('entry_delete',{id:doc._id,ack:doc.key});await refresh();toast('Importação excluída. XML local preservado e estoque vinculado estornado.');};
