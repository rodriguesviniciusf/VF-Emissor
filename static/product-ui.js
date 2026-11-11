'use strict';
// Os seletores de CST trocam a estrutura, não apenas o código dentro de um grupo incompatível.
const taxDescriptions={
 ICMS:Object.fromEntries([...normalCST,['02','02 — Monofásico próprio — combustíveis'],['15','15 — Monofásico com retenção — combustíveis'],['53','53 — Monofásico diferido — combustíveis'],['61','61 — Monofásico cobrado anteriormente']]),
 PIS:Object.fromEntries(pisCodes),COFINS:Object.fromEntries(pisCodes),
 IPI:{'00':'00 — Entrada com recuperação de crédito','01':'01 — Entrada com alíquota zero','02':'02 — Entrada isenta','03':'03 — Entrada não tributada','04':'04 — Entrada imune','05':'05 — Entrada com suspensão','49':'49 — Outras entradas','50':'50 — Saída tributada','51':'51 — Saída com alíquota zero','52':'52 — Saída isenta','53':'53 — Saída não tributada','54':'54 — Saída imune','55':'55 — Saída com suspensão','99':'99 — Outras saídas'}
};
function findFieldSpec(s,name){if(s.kind==='element'&&s.name===name)return s;for(const c of s.content?[s.content]:s.children||[]){const v=findFieldSpec(c,name);if(v)return v;}return null;}
function taxAlternatives(name){const spec=S.tax_schema[name];if(!spec)return [];const choice=spec.content?.kind==='choice'?spec.content:spec.content?.children?.find(c=>c.kind==='choice');return (choice?.children||[]).filter(c=>!c.name?.startsWith('ICMSSN'));}
function taxOptions(name){return taxAlternatives(name).flatMap(s=>(findFieldSpec(s,'CST')?.enum||[]).map(e=>({value:s.name+'|'+e.value,group:s.name,code:e.value,label:(s.name==='ICMSPart'?'Partilha ':s.name==='ICMSST'?'Repasse ':'')+(taxDescriptions[name]?.[e.value]||e.value+' — '+ngLabel(s))})));}
function taxSelected(name){const group=itemDraft.normal_groups?.[name]||{};const [key,data]=Object.entries(group).find(([k,v])=>v&&typeof v==='object'&&'CST' in v)||[];return key?key+'|'+data.CST:'';}
function taxCstControl(name){const value=taxSelected(name);return `<label class="field span3">Situação tributária do ${name} (CST)<select data-tax-cst="${name}">${name==='IPI'?'<option value="">Não informar IPI</option>':''}${taxOptions(name).map(e=>`<option value="${esc(e.value)}" ${e.value===value?'selected':''}>${esc(e.label)}</option>`).join('')}</select></label>`;}
function setTaxCst(name,value){const old=itemDraft.normal_groups[name]||{};if(!value){delete itemDraft.normal_groups[name];return;}
 const [branch,code]=value.split('|'),spec=taxAlternatives(name).find(s=>s.name===branch);if(!spec)return;
 const previous=Object.values(old).find(v=>v&&typeof v==='object'&&'CST' in v)||{};const next=ngInitial(spec);next.CST=code;
 // Preserva apenas parâmetros que pertencem ao grupo de destino. Valores calculados serão refeitos.
 for(const key of Object.keys(next)){if(key!=='CST'&&key in previous&&typeof next[key]!=='object')next[key]=previous[key];}
 if(name==='ICMS'){
  next.orig=previous.orig??itemDraft.rule.origin??'0';
  if('pICMS' in next)next.pICMS=previous.pICMS??itemDraft.rule.icms_rate??'0';
  if('modBC' in next)next.modBC=previous.modBC??'3';
  if(['10','30','70'].includes(code)){next.modBCST='4';next.pMVAST=previous.pMVAST||'0';next.pRedBCST=previous.pRedBCST||'0';next.pICMSST=previous.pICMSST||'0';itemDraft.normal_st_base_mode='formula';}
  itemDraft.rule.icms_code=code;
 }else if(name==='PIS'||name==='COFINS')itemDraft.rule[name.toLowerCase()+'_code']=code;
 itemDraft.normal_groups[name]=name==='IPI'?{cEnq:old.cEnq||'999',[branch]:next}:{[branch]:next};
 itemDraft.rule.reviewed='0';const review=$('#item-form [name="rule.reviewed"]');if(review)review.checked=false;
}
const schemaFieldsBase=schemaFields;
schemaFields=function(s,path,context='item',filter='all'){
 if(context==='item'&&s.kind==='element'&&!s.content){
  if(s.name==='CST'&&/^normal_groups\.(ICMS|PIS|COFINS|IPI)\./.test(path))return `<input type="hidden" name="${esc(path+'.CST')}" value="${esc(get(itemDraft,path+'.CST')??s.fixed??s.enum?.[0]?.value??'')}">`;
  if(s.name==='pMVAST'&&get(itemDraft,path+'.modBCST')!=='4')return '';
  if(s.name==='cEnq')return field(path+'.cEnq','Código de enquadramento legal do IPI',itemDraft);
  if(s.name==='CST'&&path==='normal_groups.IBSCBS')return rtcCstField();
  if(s.name==='cClassTrib'&&path==='normal_groups.IBSCBS')return rtcClassField();
 }
 return schemaFieldsBase(s,path,context,filter);
};
const normalGroupBase=normalGroupForm;
normalGroupForm=function(name,context='item',filter='all'){
 if(context==='item'&&['ICMS','PIS','COFINS','IPI'].includes(name)){
  const selected=taxSelected(name),branch=selected.split('|')[0],spec=taxAlternatives(name).find(s=>s.name===branch);
  let fields=spec?schemaFields(spec.content,'normal_groups.'+name+'.'+branch,context,filter):'';
  if(name==='IPI'&&spec)fields=field('normal_groups.IPI.cEnq','Código de enquadramento legal do IPI',itemDraft)+fields;
  const control=filter==='all'||filter==='icms'?taxCstControl(name):'';
  return `<div class="tax-editor-group grid">${control}${fields||(!control?notice('Este CST não utiliza campos deste tópico. Selecione o CST correspondente na aba ICMS.'):name==='IPI'?'<p class="hint span3">IPI não informado neste item.</p>':'')}</div>`;
 }
 return normalGroupBase(name,context,filter);
};
function rtcRows(){const day=(draft?.issued_at||new Date().toISOString()).slice(0,10),valid=x=>(!x.DthIniVig||x.DthIniVig.slice(0,10)<=day)&&(!x.DthFimVig||x.DthFimVig.slice(0,10)>=day);return (S.rtc_table?.csts||[]).filter(valid).map(r=>({...r,classes:r.classes.filter(valid)})).filter(r=>r.classes.length);}
function rtcCstField(){const rows=rtcRows(),value=get(itemDraft,'normal_groups.IBSCBS.CST')||'';return `<label class="field">Situação tributária IBS/CBS<select name="normal_groups.IBSCBS.CST" data-rtc-cst><option value="">Selecionar CST</option>${rows.map(r=>`<option value="${r.Cst}" ${value===r.Cst?'selected':''}>${r.Cst} — ${esc(r.NomeCst)}</option>`).join('')}${value&&!rows.some(r=>r.Cst===value)?`<option selected value="${esc(value)}">${esc(value)} — revisar código da versão anterior</option>`:''}</select></label>`;}
function rtcClassField(){const value=get(itemDraft,'normal_groups.IBSCBS.cClassTrib')||'',cst=get(itemDraft,'normal_groups.IBSCBS.CST'),rows=rtcRows().find(r=>r.Cst===cst)?.classes||[];return `<label class="field span2">Classificação tributária (cClassTrib)<select name="normal_groups.IBSCBS.cClassTrib" data-rtc-class><option value="">Selecionar classificação</option>${rows.map(r=>`<option value="${r.CodClassTrib}" ${value===r.CodClassTrib?'selected':''}>${r.CodClassTrib} — ${esc(r.NomeReduzido)}</option>`).join('')}${value&&!rows.some(r=>r.CodClassTrib===value)?`<option selected value="${esc(value)}">${esc(value)} — revisar classificação</option>`:''}</select></label>`;}
function resetRtc(){const rtc=itemDraft.normal_groups.IBSCBS,row=S.rtc_table?.csts.find(r=>r.Cst===rtc.CST);if(!row)return;
 for(const key of ['gIBSCBS','gIBSCBSMono','gTransfCred','gAjusteCompet','gCredPresIBSZFM'])delete rtc[key];
 const container=S.tax_schema.IBSCBS;
 const enable=name=>{const spec=findFieldSpec(container,name);if(spec)rtc[name]=ngInitial(spec);};
 if(row.IndExigeTrib){enable('gIBSCBS');const g=rtc.gIBSCBS;if(g){for(const name of ['gIBSUF','gIBSMun','gCBS']){const part=g[name];if(!part)continue;if(row.IndReducaoAliq)part.gRed={pRedAliq:'0',pAliqEfet:'0'};if(row.IndDiferimento)part.gDif={pDif:'0',vDif:'0'};}}}
 if(row.IndMonofasica)enable('gIBSCBSMono');if(row.IndTransferenciaCred)enable('gTransfCred');if(row.IndAjusteCompet)enable('gAjusteCompet');if(row.IndCredPresIbsZfm)enable('gCredPresIBSZFM');
 rtc.cClassTrib='';itemDraft.rule.reviewed='0';const review=$('#item-form [name="rule.reviewed"]');if(review)review.checked=false;
}
const renderNormalTaxBefore=renderNormalTaxFields;
renderNormalTaxFields=function(){renderNormalTaxBefore();const el=$('#tax-fields');if(!el)return;
 if(taxTab==='st'){
  const icms=Object.values(itemDraft.normal_groups.ICMS||{})[0]||{};
  if('modBCST' in icms){const mode=itemDraft.normal_st_base_mode||'manual';el.insertAdjacentHTML('afterbegin',`<div class="grid two st-method">${select('normal_st_base_mode','Base de cálculo ST',[['manual','Informar base final conferida'],['formula','Calcular pela modalidade selecionada']],{normal_st_base_mode:mode})}${icms.modBCST==='5'?field('normal_st_unit_value','Preço unitário de pauta (R$)',itemDraft):''}</div>`);}
 }
 for(const input of el.querySelectorAll('[name="normal_ipi_original"],[name="normal_ipi_return_percent"]'))input.closest('label').hidden=itemDraft.normal_ipi_return_enabled!=='1';
 // Identifica escolhas de percentual / quantidade pelos campos reais do leiaute.
 for(const node of el.querySelectorAll('[data-normal-choice]')){const d=normalControls[Number(node.dataset.normalChoice)];if(d?.alternatives.every(x=>x.kind==='sequence')){node.closest('label').firstChild.textContent='Tipo de cálculo';for(let n=0;n<d.alternatives.length;n++){const names=ngNames(d.alternatives[n]);node.options[n+(node.options.length-d.alternatives.length)].textContent=names.some(x=>['qUnid','qBCProd'].includes(x))?'Por quantidade × valor por unidade':'Percentual sobre a base';}}}
};
function itemSummaryMarkup(){return `<aside id="item-live-summary" class="item-live-summary" aria-label="Resumo dos cálculos"><h3>Resumo do item</h3><div id="live-calc-state" class="hint" role="status">Calculando…</div><div id="live-calc-values"></div><div id="item-calc-errors" role="status"></div></aside>`;}
function decorateItem(){const form=$('#item-form');if(!form||form.querySelector('#item-live-summary'))return;const dialogEl=form.closest('.dialog');dialogEl.classList.add('product-dialog');form.querySelectorAll('.section').forEach((sec,n)=>sec.classList.add(n===0?'product-general':n===1?'product-taxes':'product-review'));
 const taxes=form.querySelector('.product-taxes');if(taxes&&!$('#tax-overview'))taxes.insertAdjacentHTML('afterbegin','<div id="tax-overview" class="tax-overview"></div>');
 form.querySelector('#item-calc-errors')?.remove();form.insertAdjacentHTML('beforeend',itemSummaryMarkup());
 const general=form.querySelector('.product-general h2');if(general)general.textContent='Dados gerais';
}
const renderItemPrior=renderItem;
renderItem=function(){renderItemPrior();decorateItem();};
// renderNormalItem é chamado diretamente em alguns fluxos; a decoração é idempotente por formulário.
const renderNormalPrior=renderNormalItem;
renderNormalItem=function(){renderNormalPrior();decorateItem();};
function showLiveResult(r){const totals=r.totals||{},g=r.groups||itemDraft.normal_groups||{};
 const list=[['gross','Produtos'],['discount','Desconto'],['freight','Frete'],['insurance','Seguro'],['other','Despesas'],['icms_base','Base ICMS'],['icms','ICMS'],['st_base','Base ICMS ST'],['st','ICMS ST'],['fcp','FCP'],['fcpst','FCP ST'],['ipi','IPI'],['ipi_return','IPI devolvido'],['pis','PIS'],['cofins','COFINS'],['difal','DIFAL'],['ibs','IBS'],['cbs','CBS']];
 $('#live-calc-values').innerHTML=`<dl>${list.map(([k,label])=>`<div><dt>${label}</dt><dd data-calc="${k}">${brl(totals[k]||0)}</dd></div>`).join('')}</dl><div class="item-grand-total"><span>Total do item</span><strong data-calc="net">${brl(totals.net||0)}</strong></div>`;
 const icms=Object.values(g.ICMS||{})[0]||{},pis=Object.values(g.PIS||{})[0]||{},cofins=Object.values(g.COFINS||{})[0]||{},ipi=g.IPI?.IPITrib||g.IPI?.IPINT||{};
 if($('#tax-overview'))$('#tax-overview').innerHTML=[['ICMS',icms.CST||itemDraft.rule.icms_code,totals.icms,'icms'],['IPI',ipi.CST||'—',totals.ipi,'ipi'],['PIS',pis.CST||itemDraft.rule.pis_code,totals.pis,'pis'],['COFINS',cofins.CST||itemDraft.rule.cofins_code,totals.cofins,'cofins']].map(([name,cst,value,id])=>`<button type="button" class="tax-overview-card ${id}" data-action="tax-tab" data-id="${id}"><b>${name} <small>${esc(cst)}</small></b><strong>${brl(value||0)}</strong></button>`).join('');
}
let itemCalcRequest=0,itemCalcRevision=0;
calculateItem=async function(){const form=$('#item-form');if(!form)return;const request=++itemCalcRequest,revision=itemCalcRevision;const state=$('#live-calc-state');if(state)state.textContent='Atualizando cálculos…';
 try{const i=gather(form,itemDraft);const r=S.company?.CRT==='3'?await api('normal_calculate',{item:i}):await api('calculate',{note:{items:[i]}});
 if(request!==itemCalcRequest||revision!==itemCalcRevision||form!==$('#item-form'))return;
 if(r.errors?.length)throw Error(r.errors.join('\n'));itemDraft=i;if(r.groups)itemDraft.normal_groups=r.groups;
 for(const input of form.elements){if(input.name?.startsWith('normal_groups.')&&input.readOnly){const value=get(r,'groups.'+input.name.slice('normal_groups.'.length));input.value=value??'';}}
 if($('#item-total'))$('#item-total').textContent='Total: '+brl(r.totals.net);if($('#item-calc-errors'))$('#item-calc-errors').textContent='';if($('#live-calc-state'))$('#live-calc-state').textContent='Cálculos atualizados';showLiveResult(r);
 }catch(e){if(request!==itemCalcRequest||revision!==itemCalcRevision||form!==$('#item-form'))return;if($('#item-total'))$('#item-total').textContent='Total: conferir os campos';if($('#item-calc-errors'))$('#item-calc-errors').textContent=e.message;if($('#live-calc-state'))$('#live-calc-state').textContent='Confira os campos';for(const price of $$('#tax-overview strong'))price.textContent='—';if($('#live-calc-values'))$('#live-calc-values').innerHTML='<p class="hint">Complete os parâmetros para calcular os impostos.</p>';for(const input of form.elements)if(input.name?.startsWith('normal_groups.')&&input.readOnly)input.value='';}
};
function redrawTaxKeepPosition(){const body=$('#item-modal .dialog-body'),top=body?.scrollTop||0;renderTaxFields();if(body)body.scrollTop=top;calculateItem();}
document.addEventListener('input',e=>{if(e.target.closest('#item-form')){itemCalcRevision++;if($('#live-calc-state'))$('#live-calc-state').textContent='Atualizando cálculos…';}});
document.addEventListener('change',e=>{const t=e.target;if(!t.closest('#item-form'))return;itemCalcRevision++;try{
 if(t.dataset.taxCst){itemDraft=gather($('#item-form'),itemDraft);setTaxCst(t.dataset.taxCst,t.value);redrawTaxKeepPosition();}
 if(t.hasAttribute('data-rtc-cst')){itemDraft=gather($('#item-form'),itemDraft);resetRtc();redrawTaxKeepPosition();}
 if(t.hasAttribute('data-rtc-class')){itemDraft=gather($('#item-form'),itemDraft);const rtc=itemDraft.normal_groups.IBSCBS,row=S.rtc_table?.csts.find(r=>r.Cst===rtc.CST)?.classes.find(r=>r.CodClassTrib===rtc.cClassTrib);if(row&&rtc.gIBSCBS){for(const key of ['gIBSUF','gIBSMun','gCBS']){const red=rtc.gIBSCBS[key]?.gRed;if(red)red.pRedAliq=String(key==='gCBS'?row.PercRedCbs:row.PercRedIbs);}}redrawTaxKeepPosition();}
 if(t.name?.endsWith('.modBCST')){itemDraft=gather($('#item-form'),itemDraft);const icms=Object.values(itemDraft.normal_groups.ICMS||{})[0];if(icms.modBCST!=='4')delete icms.pMVAST;if(!['4','5','6'].includes(icms.modBCST))itemDraft.normal_st_base_mode='manual';redrawTaxKeepPosition();}
 if(t.name==='normal_ipi_return_enabled'){itemDraft=gather($('#item-form'),itemDraft);redrawTaxKeepPosition();}
 if(t.name==='normal_st_base_mode'){itemDraft=gather($('#item-form'),itemDraft);redrawTaxKeepPosition();}
 if(t.id==='item-rule'&&t.value&&S.company?.CRT==='3'){delete itemDraft.normal_groups;initializeNormalItem(itemDraft);renderItem();}
 if(S.company?.CRT!=='3'&&['rule.icms_code','rule.pis_code','rule.cofins_code','taxes.st_mode','taxes.fcpst_enabled','taxes.ipi_return_enabled'].includes(t.name)){itemDraft=gather($('#item-form'),itemDraft);redrawTaxKeepPosition();}
}catch(err){toast(err.message,true);}});
// Reação condicional também no Simples Nacional, mantendo seu motor fiscal existente.
const renderSimpleTax=renderTaxFields;
renderTaxFields=function(){renderSimpleTax();if(S.company?.CRT==='3')return;const el=$('#tax-fields');if(!el)return;if(taxTab==='rtc'){el.innerHTML=notice('Os grupos IBS/CBS do Simples Nacional ainda não estão integrados ao XML deste emissor. Confira a cobertura antes de emitir.');return;}const code=itemDraft.rule.icms_code;
 for(const input of el.querySelectorAll('[name]')){let visible=true;const name=input.name;
 if(name==='rule.credit_rate')visible=['101','201'].includes(code);
 if(name==='rule.icms_rate')visible=code==='900';
 if(name==='taxes.st_mva')visible=(itemDraft.taxes?.st_mode||'4')==='4';
 if(name.startsWith('taxes.fcpst_')&&name!=='taxes.fcpst_enabled')visible=itemDraft.taxes?.fcpst_enabled==='1';
 if(name.startsWith('taxes.ipi_')&&name!=='taxes.ipi_return_enabled')visible=itemDraft.taxes?.ipi_return_enabled==='1';
 if(['rule.pis_rate','rule.cofins_rate'].includes(name)){const k=name.includes('cofins')?'cofins':'pis';visible=!['04','05','06','07','08','09'].includes(itemDraft.rule[k+'_code']);}
 input.closest('label').hidden=!visible;
 }
 if(['st','fcp'].includes(taxTab)&&!['201','202','203'].includes(code))el.innerHTML=notice('O CSOSN selecionado não usa o grupo de ST implementado. Revise a situação tributária na aba ICMS.');
};
