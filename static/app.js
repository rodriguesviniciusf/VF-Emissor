'use strict';
let S={}, page='inicio', tab='nfe', selected='', month=new Date().toISOString().slice(0,7), search='', draft=null, itemDraft=null, itemIndex=-1, taxTab='icms';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const decimal=v=>{let s=String(v??'0').trim().replace(/R\$|\s/g,'');return s.includes(',')?s.replace(/\./g,'').replace(',','.'):s;};
const brl=v=>Number(decimal(v)||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const envName=e=>e==='1'?'Produção':'Homologação';
const titles={inicio:'Início',clientes:'Clientes',produtos:'Produtos',fornecedores:'Fornecedores',estoque:'Estoque',rejeicoes:'Retornos SEFAZ',tributacao:'Tributação',financeiro:'Financeiro',relatorios:'Relatórios',configuracoes:'Configurações',ajuda:'Como usar'};
const get=(o,path)=>path.split('.').reduce((a,k)=>a?.[k],o);
function set(o,path,v){let a=o;const ks=path.split('.');ks.slice(0,-1).forEach(k=>a=a[k]??={});a[ks.at(-1)]=v;}
function gather(form,base={}){const o=structuredClone(base);for(const e of form.elements){if(!e.name||e.disabled||e.type==='file')continue;set(o,e.name,e.type==='checkbox'?(e.checked?'1':'0'):e.value);}return o;}
function field(name,label,o={},extra=''){const value=get(o,name)??'';return `<label class="field ${extra}">${esc(label)}<input name="${esc(name)}" value="${esc(value)}" autocomplete="off"></label>`;}
function select(name,label,options,o={},extra=''){return `<label class="field ${extra}">${esc(label)}<select name="${esc(name)}">${options.map(v=>{const [id,label]=Array.isArray(v)?v:[v,v];return `<option value="${esc(id)}" ${String(get(o,name)??'')===String(id)?'selected':''}>${esc(label)}</option>`;}).join('')}</select></label>`;}
function area(name,label,o={},extra=''){return `<label class="field ${extra}">${esc(label)}<textarea name="${esc(name)}">${esc(get(o,name)||'')}</textarea></label>`;}
function check(name,label,o={}){return `<label class="check"><input type="checkbox" name="${esc(name)}" ${get(o,name)==='1'?'checked':''}>${esc(label)}</label>`;}
function notice(text,kind=''){return `<div class="notice ${kind}">${text}</div>`;}
function badge(v){const c=['AUTORIZADA','REGISTRADO'].includes(v)?'ok':['REJEITADA','CANCELADA','DENEGADA'].includes(v)?'bad':v==='RASCUNHO'?'':'wait';return `<span class="badge ${c}">${esc(v)}</span>`;}
function toast(msg,error=false){const el=$('#toast');el.textContent=msg;el.className=error?'error':'';el.style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.style.display='none',error?12000:4500);}
async function api(action,p={}){const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-VF-CSRF':S.csrf,'X-VF-Company':S.cid||''},body:JSON.stringify({action,cid:S.cid,...p})});const d=await r.json();if(!r.ok)throw Error(d.error||'Não foi possível concluir.');return d;}
async function refresh(cid=S.cid){const r=await fetch('/api/state?cid='+encodeURIComponent(cid||''));const d=await r.json();if(!r.ok)throw Error(d.error);S=d;if(!S.company&&S.companies&&S.companies.length){S.company=S.companies.find(c=>c._id===(S.cid||cid))||S.companies[0];}render();}
function download(kind,id=''){window.open('/api/download?'+new URLSearchParams({kind,id,cid:S.cid||''}),'_blank','noopener');}
function closeDialog(id){$('#'+id)?.remove();}
function dialog(id,title,body,footer='',size=''){closeDialog(id);const overlay=document.createElement('div');overlay.id=id;overlay.className='overlay'+($('#modal-root').children.length?' level2':'');overlay.innerHTML=`<section role="dialog" aria-modal="true" aria-label="${esc(title)}" class="dialog ${size}"><div class="dialog-head"><span>${esc(title)}</span><button aria-label="Fechar" data-action="close-dialog" data-id="${id}">×</button></div><div class="dialog-body">${body}</div>${footer?`<div class="dialog-foot">${footer}</div>`:''}</section>`;$('#modal-root').append(overlay);overlay.querySelector('input,select,textarea,button')?.focus();}
function section(title,body,open=true){return `<details class="block" ${open?'open':''}><summary>${esc(title)}</summary>${body}</details>`;}
const empty=(title,text,action='',label='')=>`<div class="empty"><strong>${esc(title)}</strong>${esc(text)}${action?`<br><button class="primary" data-action="${action}">${esc(label)}</button>`:''}</div>`;

function renderLogin(){
  return `<div class="login-wrapper"><div class="login-card"><div class="login-brand"><strong>vf<span>e</span><sup>✣</sup></strong><small>EMISSOR WEB</small></div><h2>Acesso por Empresa</h2><p class="login-subtitle">Informe o CNPJ da empresa cliente para emitir e gerenciar suas notas fiscais com total isolamento.</p><form id="login-form"><label class="field">CNPJ da Empresa<input name="cnpj" id="login-cnpj" placeholder="00.000.000/0000-00" maxlength="18" required autocomplete="off"></label><label class="field">Senha de Acesso<input name="password" id="login-password" type="password" placeholder="Senha da empresa (se houver)" autocomplete="current-password"></label><button type="submit" class="primary login-submit-btn">Entrar na Empresa</button></form><div class="login-divider"><span>ou</span></div><div class="login-actions"><button type="button" class="side-btn" data-action="login-new-company">⊞ Cadastrar Novo Cliente / Empresa</button></div><small class="login-footnote">Ambiente 100% isolado por empresa. Seus dados, clientes e certificados não são visíveis para outros CNPJs.</small></div></div>`;
}

function render(){
  if(S.rtc_table?.csts)customSelectLists.CST_IBSCBS=S.rtc_table.csts.map(r=>[r.Cst,r.Cst+' — '+r.NomeCst]);
  if(S.authenticated===false){
    document.body.classList.add('auth-mode');
    $('#content').innerHTML=renderLogin();
    return;
  }
  document.body.classList.remove('auth-mode');
  page=location.hash.slice(1)||'inicio';if(!titles[page])page='inicio';
  $('.account').innerHTML=`<div class="active-account-box"><span class="co-name"><strong>${esc(S.company?.fantasia||S.company?.xNome||'Empresa')}</strong></span><small>${esc(S.company?.CNPJCPF||'')} · ${envName(S.company?.environment||'2')}</small><button type="button" class="text-btn logout-top-btn" data-action="logout" title="Sair desta empresa e voltar ao login">🚪 Sair / Trocar Empresa</button></div>`;
  $('.local-pill').textContent=S.preview?'● Prévia de avaliação':'● Sistema Ativo';$('#page-title').textContent=titles[page];$$('nav a').forEach(a=>a.classList.toggle('active',a.dataset.page===page));
  $('#scope-banner').innerHTML=S.company?`<strong>${envName(S.company.environment)}</strong> · Conector AL / ${S.company.CRT==='3'?'Regime Normal':'Simples Nacional'} · Emissões em 2026 ${S.preview?'· <b class="preview-label">Prévia para avaliação — use o pacote Windows para certificado e SEFAZ</b>':''}`:'';
  if(!S.cid&&page!=='configuracoes'&&page!=='ajuda'){$('#content').innerHTML=`<div class="panel">${empty('Seu emissor está pronto para configurar','Comece cadastrando a empresa e conferindo os dados fiscais.','new-company','Cadastrar empresa')}</div>`;return;}
  const pages={inicio:renderInvoices,clientes:()=>renderCatalog('recipient'),produtos:()=>renderCatalog('product'),fornecedores:()=>renderCatalog('supplier'),estoque:()=>typeof renderStock==='function'?renderStock():notice('Carregando estoque…'),rejeicoes:()=>typeof renderRejections==='function'?renderRejections():notice('Carregando retornos…'),tributacao:()=>renderCatalog('rule'),financeiro:renderFinance,relatorios:renderReports,configuracoes:renderConfig,ajuda:renderHelp};
  $('#content').innerHTML=pages[page]();
}
function filteredNotes(){return (S.documents||[]).filter(n=>n.environment===S.company.environment&&(!month||n.issued_at?.startsWith(month))&&[n.number,n._recipient,n._key,n._status].join(' ').toLowerCase().includes(search.toLowerCase())).sort((a,b)=>b.issued_at.localeCompare(a.issued_at));}
function renderInvoices(){
  let body='';
  if(tab==='nfe'){
    const notes=filteredNotes();
    body=`<div class="toolbar"><button class="lime" data-action="new-note">⊞ Nova</button><button class="icon-btn" title="Atualizar lista" aria-label="Atualizar lista" data-action="refresh">↻</button><button title="Consultar situação na SEFAZ" data-action="query-note">? Consultar</button><button title="Cancelar NF-e autorizada" data-action="cancel-note">⊘</button><button title="Baixar DANFE" data-action="danfe">▤ DANFE</button><button title="Status do serviço SEFAZ" data-action="sefaz-status">▥</button><button data-action="import-xml">↓ Importar XML</button><span class="spacer"></span><input id="note-search" aria-label="Pesquisar notas" placeholder="Pesquisar notas…" value="${esc(search)}"><input id="month-filter" type="month" aria-label="Mês das notas" value="${month}" style="width:158px"><button title="Todos os meses" data-action="all-months">Todos</button></div>
    <div class="table-wrap"><table><thead><tr><th></th><th>NF-e</th><th>Destinatário</th><th>Série</th><th>CFOP</th><th>Emissão</th><th class="number">Total</th><th>Situação</th><th></th></tr></thead><tbody>${notes.map(n=>`<tr class="${selected===n._id?'selected':''}"><td><input type="checkbox" aria-label="Selecionar nota ${esc(n.number)}" data-select="${n._id}" ${selected===n._id?'checked':''}></td><td><button class="link" data-action="edit-note" data-id="${n._id}">${esc(n.number)}</button></td><td>${esc(n._recipient||'Destinatário pendente')}</td><td>${esc(n.series)}</td><td>${esc(n.items?.[0]?.rule?.CFOP||'—')}</td><td>${esc(n.issued_at?.slice(0,10).split('-').reverse().join('/'))}</td><td class="number">${brl(n._total)}</td><td>${badge(n._status)}</td><td><div class="row-actions"><button class="text-btn" data-action="note-detail" data-id="${n._id}">Detalhes</button>${['RASCUNHO','PREPARADA'].includes(n._status)?`<button class="text-btn danger-text" data-action="delete-note" data-id="${n._id}" title="Excluir este rascunho">Excluir</button>`:''}</div></td></tr>`).join('')||`<tr><td colspan="9">${empty('Nenhuma nota encontrada','Crie sua primeira nota ou ajuste o filtro do período.','new-note','⊞ Nova NF-e')}</td></tr>`}</tbody></table></div><div class="table-foot"><span>TOTAL LISTADO: <b>${notes.length} notas</b></span><b>${brl(notes.reduce((s,n)=>s+Number(n._total),0))}</b></div>`;
  }else if(tab==='cce'){
    const events=(S.events||[]).filter(e=>e.environment===S.company.environment);
    body=`<div class="toolbar"><button data-action="new-event">⊞ Carta de correção</button><button data-action="inutil">Inutilizar numeração</button></div><div class="table-wrap"><table><thead><tr><th>Tipo</th><th>Sequência</th><th>Data</th><th>Situação</th><th>Retorno</th><th></th></tr></thead><tbody>${events.map(e=>`<tr><td>${e.kind==='110110'?'Carta de correção':e.kind==='110111'?'Cancelamento':'Inutilização'}</td><td>${e.sequence}</td><td>${esc(e.created.slice(0,10))}</td><td>${badge(e.status)}</td><td>${esc(e.reason)}</td><td><button data-action="event-review" data-id="${e.id}">Detalhes</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty">Nenhum evento registrado neste ambiente.</td></tr>'}</tbody></table></div>`;
  }else{
    const received=(S.received||[]).filter(n=>n.environment===S.company.environment&&(tab!=='recebidas'||n.direction==='recebida'));
    body=`<div class="toolbar"><button class="primary" data-action="import-xml">↓ Importar XML autorizado</button><span class="hint">Importação de arquivos. A busca automática na distribuição DF-e ainda não está disponível.</span></div><div class="table-wrap"><table><thead><tr><th>NF-e</th><th>Emitente</th><th>Destinatário</th><th>Emissão</th><th>Total</th><th>Arquivo</th></tr></thead><tbody>${received.map(n=>`<tr><td>${esc(n.number)}</td><td>${esc(n.issuer)}</td><td>${esc(n.recipient)}</td><td>${esc(n.issued_at.slice(0,10))}</td><td>${brl(n.total)}</td><td><button data-action="received-xml" data-id="${n._id}">XML</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty">Nenhum XML importado.</td></tr>'}</tbody></table></div>`;
  }
  return `<div class="tabs">${[['nfe','▧ NF-E'],['cce','▧ C. CORREÇÃO'],['fornecedor','▧ NFE FORNECEDOR'],['recebidas','▧ RECEBIDAS']].map(([id,label])=>`<button data-action="tab" data-id="${id}" class="${tab===id?'active':''}">${label}</button>`).join('')}</div><div class="panel">${body}</div>`;
}
function renderCatalog(kind){const config={supplier:['Fornecedores','Novo fornecedor',S.suppliers||[],['Nome / Razão social','CPF/CNPJ','Município','UF'],r=>[r.xNome,r.CNPJCPF,r.xMun,r.UF]],recipient:['Clientes','Novo cliente',S.recipients,['Nome / Razão social','CPF/CNPJ','Município','UF'],r=>[r.xNome,r.CNPJCPF,r.xMun,r.UF]],product:['Produtos','Novo produto',S.products,['Código','Descrição','NCM','Unidade','Preço'],r=>[r.code,r.name,r.NCM,r.unit,brl(r.price)]],rule:['Tributações','Nova tributação',S.rules,['Nome','CFOP','CSOSN','PIS','COFINS','Revisado'],r=>[r.name,r.CFOP,r.icms_code,r.pis_code,r.cofins_code,r.reviewed==='1'?'Sim':'Pendente']]}[kind];
 return `<div class="panel"><div class="toolbar"><button class="primary" data-action="new-catalog" data-kind="${kind}">⊞ ${config[1]}</button><span class="spacer"></span><input id="catalog-search" placeholder="Pesquisar…" aria-label="Pesquisar cadastros"></div><div class="table-wrap"><table id="catalog-table"><thead><tr>${config[3].map(c=>`<th>${c}</th>`).join('')}<th></th></tr></thead><tbody>${config[2].map(r=>`<tr><td>${esc(config[4](r)[0])}</td>${config[4](r).slice(1).map(c=>`<td>${esc(c)}</td>`).join('')}<td><div class="row-actions"><button data-action="edit-catalog" data-kind="${kind}" data-id="${r._id}">Editar</button><button data-action="archive" data-kind="${kind}" data-id="${r._id}">Arquivar</button></div></td></tr>`).join('')||`<tr><td colspan="8">${empty('Nenhum cadastro','Use o botão acima para começar.')}</td></tr>`}</tbody></table></div></div>`;}
function partyFields(o={},isCompany=false){o=o||{};return `<div class="grid">${field('xNome','Razão social / Nome',o,'span2')}${field('fantasia','Nome fantasia',o)}${field('CNPJCPF','CPF/CNPJ (somente números)',o)}${field('IE','Inscrição estadual',o)}${isCompany?select('CRT','Regime tributário',[['1','1 — Simples Nacional'],['3','3 — Regime Normal (Lucro Real / Presumido)']],o):select('indIEDest','Indicador da IE do destinatário',customSelectLists.indIEDest,o)}${field('Email','E-mail',o)}${field('Fone','Telefone',o)}${field('CEP','CEP (8 dígitos)',o)}${field('xLgr','Logradouro',o,'span2')}${field('nro','Número',o)}${field('xCpl','Complemento',o)}${field('xBairro','Bairro',o)}${field('xMun','Município',o)}${field('cMun','Código IBGE (7 dígitos)',o)}${select('UF','UF','AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' '),o)}${isCompany?`<label class="field">Senha de acesso (login da empresa)<input type="password" name="password" placeholder="${o?._id?'Deixe em branco para manter a atual':'Defina uma senha de acesso'}" autocomplete="new-password"></label>`:''}</div>`;}
const csosn=[
  ['102','102 — Sem crédito (Venda / Revenda de mercadorias sem ST — Padrão mais comum)'],
  ['101','101 — Com permissão de crédito (Permite crédito de ICMS ao adquirente PJ)'],
  ['103','103 — Isenção do ICMS no Simples Nacional para faixa de receita bruta'],
  ['201','201 — Com crédito e cobrança do ICMS ST (Indústria ou equiparado)'],
  ['202','202 — Sem crédito e cobrança do ICMS ST (Revenda com ST a recolher)'],
  ['203','203 — Isenção no SN e cobrança do ICMS ST'],
  ['300','300 — Imune de ICMS (Exportação, livros, jornais, periódicos)'],
  ['400','400 — Não tributada pelo Simples Nacional (Isenção ou não incidência estadual)'],
  ['500','500 — ICMS cobrado anteriormente por ST ou antecipação (Revenda com ST já retida na entrada)'],
  ['900','900 — Outros (Bonificações, remessas, devoluções e operações diversas)']
];
const pisCodes=[
  ['99','99 — Outras operações (CST padrão para Simples Nacional e diversas saídas)'],
  ['01','01 — Operação tributável com alíquota básica (PIS 0,65%/1,65% · COFINS 3%/7,6%)'],
  ['02','02 — Operação tributável com alíquota diferenciada'],
  ['03','03 — Operação tributável com alíquota por unidade de medida'],
  ['04','04 — Operação monofásica — revenda com alíquota zero (bebidas, medicamentos, autopeças, combustíveis)'],
  ['05','05 — Operação tributável por substituição tributária (ST)'],
  ['06','06 — Operação tributável a alíquota zero'],
  ['07','07 — Operação isenta da contribuição'],
  ['08','08 — Operação sem incidência da contribuição'],
  ['09','09 — Operação com suspensão da contribuição'],
  ['49','49 — Outras operações de saída (Muito comum no Simples Nacional)']
];
const customSelectLists = {
 CST_IBSCBS: [
  ['000','000 — Tributação integral pelo IBS e CBS'],
  ['010','010 — Tributação com alíquota reduzida (saúde, educação, alimentos)'],
  ['011','011 — Alíquota reduzida de 60% (bens e serviços essenciais)'],
  ['012','012 — Alíquota reduzida de 30% (serviços de profissionais liberais)'],
  ['020','020 — Tributação com alíquota diferenciada'],
  ['030','030 — Alíquota uniforme por unidade de medida (ad rem)'],
  ['040','040 — Isenção do IBS e CBS'],
  ['050','050 — Imunidade constitucional (exportações, livros, templos)'],
  ['060','060 — Não incidência'],
  ['070','070 — Diferimento total ou parcial do IBS e CBS'],
  ['200','200 — Monofásica (combustíveis e lubrificantes)'],
  ['400','400 — Simples Nacional sem apropriação de crédito pelo adquirente (Padrão SN)'],
  ['410','410 — Simples Nacional com direito a crédito pelo adquirente PJ'],
  ['620','620 — Regime aduaneiro especial / ZFM / Áreas de Livre Comércio'],
  ['900','900 — Outras hipóteses de tributação / Ajustes'],
  ['999','999 — Outras operações não especificadas']
 ],
 CST_ICMS: typeof normalCST!=='undefined'?normalCST:[],
 CST_PIS: pisCodes,
 CST_COFINS: pisCodes,
 motDesICMS: [
  ['1','1 — Táxi / Transporte de passageiros'],
  ['2','2 — Deficiente físico / condutor / não condutor'],
  ['3','3 — Produtor agropecuário'],
  ['4','4 — Frotista / Locadora de veículos'],
  ['5','5 — Diplomático / Consular'],
  ['6','6 — Utilitários/motocicletas Amazônia Ocidental e Áreas de Livre Comércio'],
  ['7','7 — SUFRAMA (Suframa / incentivo regional)'],
  ['8','8 — Venda a órgãos da administração pública'],
  ['9','9 — Outros motivos de desoneração'],
  ['10','10 — Deficiente condutor'],
  ['11','11 — Deficiente não condutor'],
  ['12','12 — Fomento e desenvolvimento agropecuário'],
  ['16','16 — Olimpíadas Rio 2016'],
  ['28','28 — Venda a produtor agropecuário (máquinas e implementos)'],
  ['90','90 — Solicitado pelo Fisco / Exigência fiscal']
 ],
 cEnq: [
  ['999','999 — 999 - Tributação normal / Outros enquadramentos (Mais comum)'],
  ['101','101 — 101 - Imunidade - Livros, jornais, periódicos e papel'],
  ['102','102 — 102 - Imunidade - Energia elétrica, combustíveis e derivados'],
  ['103','103 — 103 - Imunidade - Exportação para o exterior'],
  ['301','301 — 301 - Isenção - Zona Franca de Manaus (ZFM)'],
  ['302','302 — 302 - Isenção - Áreas de Livre Comércio (ALC)'],
  ['601','601 — 601 - Suspensão - Matérias-primas e insumos industriais'],
  ['602','602 — 602 - Suspensão - Remessa para industrialização por encomenda'],
  ['603','603 — 603 - Suspensão - Remessa em consignação ou demonstração'],
  ['604','604 — 604 - Suspensão - Exportação temporária / Drawback']
 ],
 modBC: [
  ['3','3 — Valor da operação (Preço real praticado — padrão mais comum)'],
  ['0','0 — Margem de Valor Agregado (% MVA)'],
  ['1','1 — Pauta (Valor fiscal fixado pelo Estado)'],
  ['2','2 — Preço tabelado máximo (fixado por autoridade)']
 ],
 modBCST: [
  ['4','4 — Margem de Valor Agregado (% MVA — modalidade mais usada)'],
  ['0','0 — Preço tabelado ou máximo sugerido'],
  ['1','1 — Lista Negativa (medicamentos e correlatos)'],
  ['2','2 — Lista Positiva (medicamentos e correlatos)'],
  ['3','3 — Lista Neutra (medicamentos e correlatos)'],
  ['5','5 — Pauta fiscal (valor fixado pela SEFAZ)'],
  ['6','6 — Valor da operação']
 ],
 orig: [
  ['0','0 — Nacional, exceto as indicadas nos códigos 3, 4, 5 e 8'],
  ['1','1 — Estrangeira — Importação direta, exceto código 6'],
  ['2','2 — Estrangeira — Adquirida no mercado interno, exceto código 7'],
  ['3','3 — Nacional, mercadoria com Conteúdo de Importação > 40% e <= 70%'],
  ['4','4 — Nacional, produção conforme processos produtivos básicos (PPB)'],
  ['5','5 — Nacional, mercadoria com Conteúdo de Importação <= 40%'],
  ['6','6 — Estrangeira — Importação direta, sem similar nacional (CAMEX)'],
  ['7','7 — Estrangeira — Mercado interno, sem similar nacional (CAMEX)'],
  ['8','8 — Nacional, mercadoria com Conteúdo de Importação > 70%']
 ],
 indDeduzDeson: [
  ['0','0 — Não deduzir o ICMS desonerado do valor total da NF-e'],
  ['1','1 — Deduzir o ICMS desonerado do valor total da NF-e']
 ],
 tPag: [
  ['01','01 — Dinheiro'],
  ['17','17 — Pagamento Instantâneo (PIX)'],
  ['15','15 — Boleto Bancário'],
  ['03','03 — Cartão de Crédito'],
  ['04','04 — Cartão de Débito'],
  ['16','16 — Depósito Bancário'],
  ['14','14 — Duplicata Mercantil'],
  ['90','90 — Sem pagamento'],
  ['99','99 — Outros']
 ],
 indPag: [
  ['0','0 — Pagamento à vista'],
  ['1','1 — Pagamento a prazo']
 ],
 indIEDest: [
  ['9','9 — Não Contribuinte (Consumidor final físico ou jurídico sem IE)'],
  ['1','1 — Contribuinte do ICMS (Empresas com Inscrição Estadual ativa)'],
  ['2','2 — Contribuinte Isento de Inscrição no cadastro de Contribuintes']
 ]
};
window.customSelectLists = customSelectLists;
window.pisCodes = pisCodes;
const defaultRule=()=>({name:'',CFOP:'5102',origin:'0',icms_code:'102',icms_rate:'0',credit_rate:'0',pis_code:'99',pis_rate:'0',cofins_code:'99',cofins_rate:'0',exclude_icms:'0',rtc_status:'nao_aplicavel_revisado',reviewed:'0'});
function ruleFields(o){return `<div class="grid">${field('name','Nome da tributação',o,'span2')}${field('CFOP','CFOP (4 dígitos)',o)}${select('icms_code',S.company?.CRT==='3'?'Situação do ICMS / CST':'Situação do ICMS / CSOSN',S.company?.CRT==='3'?(typeof normalCST!=='undefined'?normalCST:[]):csosn,o,'span2')}${select('origin','Origem da mercadoria',customSelectLists.orig,o)}${field('icms_rate','Alíquota ICMS (%)',o)}${S.company?.CRT==='3'?'':field('credit_rate','Alíquota crédito SN (%)',o)}${select('pis_code','CST PIS',pisCodes,o)}${field('pis_rate','Alíquota PIS (%)',o)}${select('cofins_code','CST COFINS',pisCodes,o)}${field('cofins_rate','Alíquota COFINS (%)',o)}</div>${check('exclude_icms','Excluir ICMS da base de PIS/COFINS, quando aplicável',o)}${check('reviewed','Conferi o enquadramento fiscal e as alíquotas deste perfil',o)}<p class="hint">${S.company?.CRT==='3'?'Os grupos completos são editados no item. Também é possível salvar a tributação do item como perfil.':'ST e FECOEP ST são preenchidos em cada item e ficam restritos à homologação no Simples Nacional.'} Não há enquadramento tributário automático.</p>`;}
function editCatalog(kind,id=''){
 let o={};
 if(id){
   const list=({recipient:S.recipients,supplier:S.suppliers,product:S.products,rule:S.rules,company:S.companies}[kind])||[];
   o=list.find(r=>r._id===id)||(kind==='company'&&(S.company?._id===id||S.cid===id)?S.company:{})||{};
 } else {
   o=kind==='rule'?(S.company?.CRT==='3'?{...defaultRule(),icms_code:'00'}:defaultRule()):kind==='product'?{unit:'UN',price:'0'}:kind==='company'?{UF:'AL',CRT:'1',environment:'2',series:'1',next_number:'1',production_series:'1',production_next_number:'1'}:{UF:S.company?.UF||'AL',indIEDest:'9'};
 }
 o=o||{};
 let body=kind==='recipient'||kind==='supplier'||kind==='company'?partyFields(o,kind==='company'):kind==='rule'?ruleFields(o):`<div class="grid">${field('code','Código próprio',o)}${field('name','Nome do produto',o,'span2')}${field('NCM','NCM (8 dígitos)',o)}${field('CEST','CEST (7 dígitos, se aplicável)',o)}${field('unit','Unidade',o)}${field('price','Preço unitário',o)}${field('gtin','EAN / GTIN (vazio = SEM GTIN)',o)}${select('rule_id','Tributação padrão',[['','Selecionar ao adicionar na nota'],...S.rules.map(r=>[r._id,r.name])],o)}${area('description','Observações internas',o,'span3')}</div>`;
 if(kind==='company')body+=(typeof normalCompanyFields==='function'?normalCompanyFields(o):'')+`<h3>Numeração e ambiente</h3><div class="grid">${select('environment','Ambiente',[['2','Homologação (testes)'],['1','Produção (validade fiscal)']],o)}${field('series','Série de homologação',o)}${field('next_number','Próximo número de homologação',o)}${field('production_series','Série de produção',o)}${field('production_next_number','Próximo número de produção',o)}</div>${notice('Confira a numeração utilizada em outros emissores antes de habilitar produção. A primeira etapa é testar o fluxo em homologação.','warning')}<label class="check"><input name="enable_production" type="checkbox"> Habilitar produção para esta empresa</label>${field('ack','Para habilitar, digite PRODUÇÃO')}`;
 dialog('catalog-modal',(id?'Editar ':'Cadastrar ')+({company:'empresa',recipient:'cliente',supplier:'fornecedor',product:'produto',rule:'tributação'}[kind]),`<form id="catalog-form" data-kind="${kind}" data-id="${id}">${body}</form>`,`<button data-action="close-dialog" data-id="catalog-modal">Voltar</button><button class="primary" data-action="save-catalog">Salvar</button>`,'medium');
}
async function saveCatalog(){const form=$('#catalog-form'),existing=({company:S.companies,recipient:S.recipients,supplier:S.suppliers,product:S.products,rule:S.rules}[form.dataset.kind]||[]).find(r=>r._id===form.dataset.id)||(form.dataset.kind==='company'&&form.dataset.id?S.company:{})||{},data=gather(form,existing);const enable=data.enable_production==='1';delete data.enable_production;const ack=data.ack;delete data.ack;const r=await api('save_catalog',{kind:form.dataset.kind,id:form.dataset.id,data,enable_production:enable,ack});closeDialog('catalog-modal');if(form.dataset.kind==='company'&&(!S.authenticated||!form.dataset.id)){try{await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cnpj:data.CNPJCPF,password:data.password||''})});}catch(e){}}await refresh(form.dataset.kind==='company'?(r.id||S.cid):S.cid);if(form.dataset.kind==='company'&&$('#note-form')){renderNote();toast('Dados da empresa atualizados na nota.');return;}if(form.dataset.kind==='recipient'&&$('#note-form')){draft.recipient_id=r.id;renderNote();toast('Dados do cliente atualizados na nota.');return;}toast('Cadastro salvo.');}
function currentDraft(){if($('#note-form'))draft=gather($('#note-form'),draft);if(draft.issued_at&&draft.issued_at.length<=19)draft.issued_at=draft.issued_at+(draft.issued_at.length===16?':00':'')+'-03:00';return draft;}
async function openNote(id='',n=null){if(!S.cid)return editCatalog('company');if(id){n=n||S.documents.find(d=>d._id===id);if(!['RASCUNHO','REJEITADA','PREPARADA'].includes(n._status))return noteDetail(id);}draft=structuredClone(n||(await api('new_note')).note);draft._id=id;renderNote();}
function renderNote(){const n=draft,co=S.company;const recipientOptions=[['','Selecione o destinatário'],...S.recipients.map(r=>[r._id,r.xNome+' · '+r.CNPJCPF])];
 const rec=S.recipients.find(r=>r._id===n.recipient_id);
 const recipientCard=rec?`<div class="note-recipient-card"><div class="co-header"><strong style="color:#26593b;font-size:13px">${esc(rec.xNome)}</strong><button type="button" class="text-btn co-edit-btn" data-action="edit-note-recipient" title="Editar dados deste cliente">✎ Editar dados do cliente</button></div><div><span>CPF/CNPJ: <b>${esc(rec.CNPJCPF)}</b></span> · <span>IE: <b>${esc(rec.IE||'Isento / Não informado')}</b></span> ${rec.Fone?`· <span>Fone: ${esc(rec.Fone)}</span>`:''}</div><div><span>${esc(rec.xLgr||'')}, ${esc(rec.nro||'s/n')}${rec.xCpl?' · '+esc(rec.xCpl):''} - ${esc(rec.xBairro||'')}</span> · <span>${esc(rec.xMun||'')} / ${esc(rec.UF||'')} · CEP: ${esc(rec.CEP||'')}</span></div></div>`:'';
 const general=`<div class="grid">${field('nature','Natureza da operação',n,'span2')}<label class="field">Data e hora de emissão<input type="datetime-local" name="issued_at" value="${esc(n.issued_at?.slice(0,16)||'')}"></label>${select('operation','Tipo de operação',[['1','Saída'],['0','Entrada']],n)}${select('destination','Destino da operação',[['1','Operação interna'],['2','Operação interestadual (envio limitado)']],n)}${select('presence','Presença do comprador',[['0','Não se aplica'],['1','Operação presencial'],['2','Pela Internet'],['3','Teleatendimento'],['5','Fora do estabelecimento'],['9','Outros']],n)}${select('purpose','Finalidade',[['1','NF-e normal'],['2','Complementar'],['3','Ajuste'],['4','Devolução']],n)}${field('series','Série',n)}${field('number','Número (vazio = automático)',n)}${select('has_reference','Possui documento referenciado?',[['0','Não'],['1','Sim']],n)}${field('references','Chaves referenciadas (separadas por vírgula)',n,'span2')}${field('cMunFG','Código IBGE do fato gerador (vazio = emitente)',n)}${field('authorized_xml','CPF/CNPJ autorizados a acessar XML',n,'span2')}</div>`;
 const recipient=`<div class="grid">${select('recipient_id','Razão / Nome do destinatário',recipientOptions,n,'span2')}${select('final','Destinado a consumidor final',[['1','Sim'],['0','Não']],n)}</div><div class="actions" style="margin-top:8px"><button class="text-btn" type="button" data-action="new-catalog" data-kind="recipient">⊞ Cadastrar novo cliente</button>${rec?`<button class="text-btn" type="button" data-action="edit-note-recipient" style="color:#2c7ba0;font-weight:600">✎ Editar dados do cliente selecionado</button>`:''}</div>${recipientCard}`;
 const billing=`<div class="grid">${field('invoice_number','Número da fatura',n)}${field('invoice_original','Valor original',n)}${field('invoice_discount','Desconto da fatura',n)}${field('invoice_net','Valor líquido',n)}${area('duplicates','Duplicatas: 001|AAAA-MM-DD|valor;002|AAAA-MM-DD|valor',n,'span2')}</div>`;
 const transport=`<div class="grid">${select('transport_mode','Modalidade do frete',[['9','9 — Sem transporte'],['0','0 — Por conta do emitente'],['1','1 — Por conta do destinatário'],['2','2 — Terceiros'],['3','3 — Próprio por conta do emitente'],['4','4 — Próprio por conta do destinatário']],n,'span2')}${field('carrier_doc','CPF/CNPJ transportadora',n)}${field('carrier_name','Nome da transportadora',n,'span2')}${field('carrier_ie','IE transportadora',n)}${field('carrier_address','Endereço transportadora',n)}${field('carrier_city','Município transportadora',n)}${field('carrier_uf','UF transportadora',n)}${field('vehicle_plate','Placa (sem hífen)',n)}${field('vehicle_uf','UF do veículo',n)}${field('volume_qty','Quantidade de volumes',n)}${field('volume_type','Espécie dos volumes',n)}${field('volume_brand','Marca dos volumes',n)}${field('volume_number','Numeração dos volumes',n)}${field('net_weight','Peso líquido (kg)',n)}${field('gross_weight','Peso bruto (kg)',n)}</div><p class="hint">Frete, seguro e despesas são informados em cada item. Os totais da nota refletem a soma dos itens.</p>`;
 dialog('note-modal',n._id?'Editando NF-e '+n.number:'Criando nova NF-e',`<div class="note-info"><div class="note-company-card"><div class="co-header"><b>${esc(co.xNome)}</b><button type="button" class="text-btn co-edit-btn" data-action="edit-note-company" title="Editar dados da empresa emitente">✎ Editar dados da empresa</button></div>${co.fantasia?`<small>Fantasia: ${esc(co.fantasia)}</small>`:''}<small>${esc(co.xLgr||'Endereço ainda não informado')}, ${esc(co.nro||'s/n')}${co.xCpl?' · '+esc(co.xCpl):''} - ${esc(co.xBairro||'')}</small><small>${esc(co.xMun||'')} / ${esc(co.UF||'')} · CEP: ${esc(co.CEP||'')}</small><small>CNPJ: ${esc(co.CNPJCPF)} · IE: ${esc(co.IE||'pendente')}${co.Fone?' · Fone: '+esc(co.Fone):''}</small><small>Regime: <b>${co.CRT==='1'?'1 — Simples Nacional':'3 — Regime Normal'}</b></small></div><div class="note-number">Número da NF-e<b>${esc(n.number||'{automático}')}</b>Série ${esc(n.series)}<br><span class="env">${envName(n.environment)}</span></div></div><div id="note-validation"></div><form id="note-form">${section('Dados gerais',general)}${section('Dados do destinatário',recipient)}${section('Lista de produtos / serviços',`<div class="hint-box notice"><b>Itens desta NF-e:</b> Você pode editar valores, descrição ou tributação de cada produto exclusivamente para esta nota fiscal sem afetar o cadastro geral.</div><div id="note-items"></div><div class="actions"><button type="button" class="primary" data-action="add-item">⊞ Adicionar produto</button><button type="button" data-action="add-catalog-items">Selecionar produtos cadastrados</button></div>`)}${section('Totais (valores calculados automaticamente)','<div id="note-totals"></div>')}${S.company?.CRT==='3'&&typeof normalNoteSections==='function'?normalNoteSections(n):''}${section('Fatura e duplicatas',billing,false)}${section('Informações de pagamento',select('payment','Forma de pagamento',customSelectLists.tPag,n),false)}${section('Dados do transporte',transport,false)}${section('Informações de compras',`<div class="grid">${field('purchase_order','Pedido de compra',n)}${field('purchase_contract','Contrato',n)}${field('purchase_commitment','Nota de empenho',n)}</div>`,false)}${section('Outras informações',area('info','Informações complementares',n)+area('info_fisco','Informações para o Fisco',n))}</form>`,`<span class="form-footer-note">${envName(n.environment)} · Salvar rascunho não transmite a nota.</span><span class="spacer"></span>${n._id&&['RASCUNHO','PREPARADA'].includes(n._status||'RASCUNHO')?`<button type="button" class="danger" data-action="delete-note" data-id="${n._id}">Excluir rascunho</button>`:''}<button type="button" data-action="validate-note">✓ Conferir</button><button type="button" class="blue" data-action="preview-danfe" title="Visualizar prévia do DANFE em PDF antes da emissão">📄 Prévia do DANFE</button><button type="button" data-action="save-note">Apenas salvar</button><button type="button" class="primary" data-action="prepare-note">Salvar e enviar</button><button type="button" data-action="close-note">Voltar</button>`);
 renderItems();updateTotals();
}
function renderItems(){const items=draft.items||[];$('#note-items').innerHTML=items.length?`<div class="table-wrap"><table><thead><tr><th>Código</th><th>Descrição</th><th>CFOP</th><th>Qtd.</th><th>Unitário</th><th>Desconto</th><th>Total</th><th></th></tr></thead><tbody>${items.map((i,n)=>`<tr><td>${esc(i.product.code)}</td><td>${esc(i.product.name)}${i.infAdProd?`<br><small class="hint">${esc(i.infAdProd)}</small>`:''}</td><td>${esc(i.rule.CFOP)}</td><td>${esc(i.quantity)}</td><td>${brl(i.price)}</td><td>${brl(i.discount)}</td><td class="number">${brl(Number(i.quantity||1)*Number(i.price||0)-Number(i.discount||0))}</td><td><div class="row-actions"><button type="button" data-action="edit-item" data-id="${n}" title="Editar este item na nota">Editar item na nota</button><button type="button" class="danger-text" data-action="remove-item" data-id="${n}">Remover</button></div></td></tr>`).join('')}</tbody></table></div><br>`:empty('Adicione os produtos da nota','Os tributos de cada produto são organizados por tópico.');}
async function updateTotals(){try{const r=await api('calculate',{note:draft});if(!$('#note-totals'))return;$('#note-totals').innerHTML=`${r.errors.length?notice(r.errors.map(esc).join('<br>'),'warning'):''}<div class="total-grid"><div><label>Total dos produtos</label><b>${brl(r.totals.gross)}</b></div><div><label>Desconto</label><b>${brl(r.totals.discount)}</b></div><div><label>TOTAL DA NF-e</label><b>${brl(draft.normal_vnftot||r.totals.net)}</b></div></div>`;}catch(e){toast(e.message,true);}}
function addItem(index=-1,product=null){currentDraft();itemIndex=index;taxTab='icms';if(index>=0)itemDraft=structuredClone(draft.items[index]);else{const rule=product?.rule_id?S.rules.find(r=>r._id===product.rule_id):null;itemDraft={product:product?structuredClone(product):{code:'',name:'',unit:'UN',NCM:'',CEST:'',gtin:''},rule:structuredClone(rule||defaultRule()),quantity:'1',price:product?.price||'0',discount:'0',freight:'0',insurance:'0',other:'0',auto_calc:'1',manual:{},taxes:{}};}if(S.company?.CRT==='3'&&typeof initializeNormalItem==='function')initializeNormalItem(itemDraft);renderItem();}
function renderItem(){if(S.company?.CRT==='3'&&typeof renderNormalItem==='function')return renderNormalItem();const i=itemDraft;
 const general=`<div class="notice"><strong>Item exclusivo desta nota:</strong> As alterações feitas abaixo aplicam-se apenas a esta nota fiscal. O cadastro geral de produtos permanece protegido.</div><div class="grid">${field('product.name','Nome / Descrição do produto',i,'span2')}${field('product.code','Código próprio',i)}${field('quantity','Quantidade',i)}${field('price','Preço unitário',i)}${field('discount','Desconto',i)}${field('rule.CFOP','CFOP',i)}${field('freight','Frete',i)}${field('insurance','Seguro',i)}${field('other','Outras despesas',i)}${field('product.unit','Unidade',i)}${field('product.NCM','NCM (8 dígitos)',i)}${field('product.CEST','CEST (quando aplicável)',i)}${field('product.gtin','EAN / GTIN',i)}${select('rule.origin','Origem da mercadoria',customSelectLists.orig,i)}${area('infAdProd','Informações adicionais do produto nesta nota (infAdProd — máx 500 caracteres)',i,'span3')}</div>${i.product?._id?check('sync_to_catalog','Atualizar também os dados deste item no cadastro geral de produtos',i):check('save_new_to_catalog','Salvar também este item no cadastro geral de produtos para futuras notas',i)}`;
 dialog('item-modal','Produto / Serviço na NF-e',`<form id="item-form"><section class="section"><h2>Dados do produto na nota</h2>${general}</section><section class="section"><h2>Dados tributários</h2><label class="field">Escolher tributação cadastrada<select id="item-rule"><option value="">Preenchimento manual</option>${S.rules.map(r=>`<option value="${r._id}">${esc(r.name)}</option>`).join('')}</select></label><br><div class="tax-tabs">${[['icms','ICMS'],['st','ICMS ST'],['fcp','FCP / FECOEP'],['ipi','IPI'],['pis','PIS'],['cofins','COFINS'],['rtc','IBS / CBS (Reforma)']].map(([id,label])=>`<button type="button" data-action="tax-tab" data-id="${id}" class="${taxTab===id?'active':''}">${label}</button>`).join('')}</div><div id="tax-fields"></div><div id="item-calc-errors"></div><div class="item-summary"><span>Os cálculos usam o enquadramento informado.</span><b id="item-total">Total: —</b></div></section><section class="section">${check('rule.reviewed','Conferi a tributação e as alíquotas deste produto',i)}<p class="hint">IBS/CBS, IPI normal e DIFAL não estão implementados no XML desta versão. O envio admite CRT 1, AL e 2026. Combinações sem suporte são bloqueadas na conferência.</p></section></form>`,`<button data-action="close-dialog" data-id="item-modal">Voltar</button><button class="primary" data-action="save-item">Salvar produto na nota</button>`);renderTaxFields();calculateItem();}
function renderTaxFields(){if(S.company?.CRT==='3'&&typeof renderNormalTaxFields==='function')return renderNormalTaxFields();const i=itemDraft;let html='';
 if(taxTab==='icms')html=`<h3>ICMS — Situação Tributária (CSOSN)</h3><div class="grid">${select('rule.icms_code','Situação do ICMS (CSOSN)',csosn,i,'span2')}${field('rule.credit_rate','Alíquota de crédito SN (%) — CSOSN 101/201',i)}${field('rule.icms_rate','Alíquota ICMS próprio (%) — CSOSN 900',i)}</div><p class="hint">Escolha o CSOSN conforme a operação. Para revenda de mercadorias no Simples Nacional sem ST, use <b>102</b>. Para mercadorias com ST já recolhida na entrada, use <b>500</b>.</p>`;
 if(taxTab==='st')html=notice('A Substituição Tributária (ICMS ST) está disponível para CSOSN 201, 202 e 203. Informe a modalidade da base, alíquota e fundamentação.','warning')+`<div class="grid">${select('taxes.st_mode','Modalidade de determinação da base ST',customSelectLists.modBCST,i,'span2')}${field('taxes.st_base','Base de cálculo do ICMS ST (R$)',i)}${field('taxes.st_rate','Alíquota do ICMS ST (%)',i)}${field('taxes.st_deduction','ICMS próprio a deduzir (R$)',i)}${field('taxes.st_mva','Margem de Valor Agregado — MVA (%)',i)}${field('taxes.st_reduction','Percentual de redução da base ST (%)',i)}${area('taxes.legal_reference','Fundamentação legal do ICMS ST (mínimo 15 caracteres)',i,'span3')}</div>${check('taxes.reviewed','Conferi os parâmetros do ICMS ST e a fundamentação legal',i)}`;
 if(taxTab==='fcp')html=`<h3>FCP / FECOEP ST (Fundo de Combate à Pobreza)</h3>${check('taxes.fcpst_enabled','Informar FCP / FECOEP ST para este item',i)}<div class="grid two">${field('taxes.fcpst_base','Base de cálculo FCP ST',i)}${field('taxes.fcpst_rate','Alíquota FCP ST (%) — Normalmente 1% ou 2%',i)}</div><p class="hint">O FECOEP/FCP é um adicional aplicado ao ICMS ST em produtos específicos definidos pela legislação estadual de destino (ex: 1% ou 2% em supérfluos). Exige CSOSN com ST e fundamentação revisada.</p>`;
 if(taxTab==='ipi')html=notice('IPI devolvido para operações de devolução de mercadoria.','warning')+check('taxes.ipi_return_enabled','Informar IPI devolvido neste item',i)+`<div class="grid">${field('taxes.ipi_original_value','Valor do IPI da nota fiscal de origem',i)}${field('taxes.ipi_return_percent','Percentual devolvido (%)',i)}${field('taxes.ipi_origin_key','Chave de acesso da NF-e de origem',i,'span3')}${area('taxes.ipi_reason','Motivo da devolução (mínimo 15 caracteres)',i,'span3')}${area('taxes.legal_reference','Fundamentação legal da devolução',i,'span3')}</div>${check('taxes.reviewed','Conferi os dados do IPI devolvido e a chave referenciada',i)}`;
 if(['pis','cofins'].includes(taxTab))html=`<h3>${taxTab.toUpperCase()} — Situação Tributária (CST)</h3><div class="grid two">${select('rule.'+taxTab+'_code','CST do '+taxTab.toUpperCase(),pisCodes,i)}${field('rule.'+taxTab+'_rate','Alíquota do '+taxTab.toUpperCase()+' (%)',i)}</div>${check('rule.exclude_icms','Excluir ICMS da base de cálculo de PIS/COFINS quando aplicável',i)}<p class="hint">No Simples Nacional, use o CST <b>99 — Outras operações</b> ou <b>49 — Outras saídas</b>. Para produtos monofásicos (bebidas, medicamentos, autopeças, combustíveis), utilize o CST <b>04</b>.</p>`;
 if(taxTab==='rtc')html=`<h3>IBS e CBS — Reforma Tributária (2026/2027)</h3><div class="notice"><strong>Reforma Tributária (EC 132/2023):</strong> O IBS (Estadual/Municipal) e a CBS (Federal) unificam os tributos sobre o consumo. No Simples Nacional, as empresas continuam recolhendo pelo Simples, podendo destacar o CST correspondente para fins de conferência e transição.</div><div class="grid">${select('rule.rtc_cst','Situação Tributária do IBS/CBS (CST)',customSelectLists.CST_IBSCBS,i,'span2')}${field('rule.cClassTrib','Classificação Tributária (cClassTrib — 6 dígitos)',i)}${field('taxes.rtc_base','Base de cálculo IBS/CBS',i)}${field('taxes.rtc_pIBSUF','Alíquota IBS Estadual (%)',i)}${field('taxes.rtc_pIBSMun','Alíquota IBS Municipal (%)',i)}${field('taxes.rtc_pCBS','Alíquota CBS Federal (%)',i)}</div><p class="hint">No Simples Nacional, o CST padrão mais comum é <b>400 — Simples Nacional sem apropriação de crédito</b>, ou <b>410</b> para permitir crédito ao adquirente PJ.</p>`;
 $('#tax-fields').innerHTML=html;}
async function calculateItem(){try{const i=gather($('#item-form'),itemDraft);const r=await api('calculate',{note:{items:[i]}});if($('#item-total'))$('#item-total').textContent='Total: '+brl(r.totals.net);if($('#item-calc-errors'))$('#item-calc-errors').textContent=r.errors.join('\n');}catch(e){if($('#item-calc-errors'))$('#item-calc-errors').textContent=e.message;}}
async function saveItem(){itemDraft=gather($('#item-form'),itemDraft);for(const k of ['quantity','price','discount','freight','insurance','other'])itemDraft[k]=decimal(itemDraft[k]);if(!itemDraft.product.name||!itemDraft.product.code||!/^\d{8}$/.test(itemDraft.product.NCM))throw Error('Preencha código, nome e NCM com oito dígitos.');const sync=itemDraft.sync_to_catalog==='1',saveNew=itemDraft.save_new_to_catalog==='1';delete itemDraft.sync_to_catalog;delete itemDraft.save_new_to_catalog;if(sync&&itemDraft.product?._id){await api('save_catalog',{kind:'product',id:itemDraft.product._id,data:{code:itemDraft.product.code,name:itemDraft.product.name,NCM:itemDraft.product.NCM,CEST:itemDraft.product.CEST||'',unit:itemDraft.product.unit||'UN',price:itemDraft.price||'0',gtin:itemDraft.product.gtin||'',rule_id:itemDraft.rule?._id||''}});toast('Cadastro do produto atualizado.');}else if(saveNew){const res=await api('save_catalog',{kind:'product',data:{code:itemDraft.product.code,name:itemDraft.product.name,NCM:itemDraft.product.NCM,CEST:itemDraft.product.CEST||'',unit:itemDraft.product.unit||'UN',price:itemDraft.price||'0',gtin:itemDraft.product.gtin||'',rule_id:itemDraft.rule?._id||''}});itemDraft.product._id=res.id;toast('Produto salvo no cadastro geral.');}if(sync||saveNew)await refresh();if(itemIndex<0)draft.items.push(itemDraft);else draft.items[itemIndex]=itemDraft;closeDialog('item-modal');renderItems();updateTotals();}
function catalogItems(){currentDraft();dialog('pick-products','Selecionar produto cadastrado',S.products.length?`<div class="table-wrap"><table><thead><tr><th>Código</th><th>Produto</th><th>Preço</th><th></th></tr></thead><tbody>${S.products.map(p=>`<tr><td>${esc(p.code)}</td><td>${esc(p.name)}</td><td>${brl(p.price)}</td><td><button class="primary" data-action="pick-product" data-id="${p._id}">Adicionar</button></td></tr>`).join('')}</tbody></table></div>`:empty('Nenhum produto cadastrado','Cadastre um produto na seção Produtos ou adicione diretamente na nota.'),`<button data-action="close-dialog" data-id="pick-products">Voltar</button>`,'medium');}
function renderValidationIssues(issues){
  if(!issues||!issues.length)return notice('A conferência local e a validação do leiaute passaram sem pendências. A SEFAZ fará suas próprias validações fiscais na transmissão.','success');
  const badgeMap=field=>{
    if(field.startsWith('item.')) return `Item ${Number(field.split('.')[1]||0)+1}`;
    if(field.startsWith('recipient')) return 'Cliente';
    if(field.startsWith('company')) return 'Empresa';
    if(field==='items') return 'Itens';
    if(['nature','destination','operation','presence','purpose','final'].includes(field)) return 'Operação';
    if(['series','number','issued_at'].includes(field)) return 'Identificação';
    if(['references','has_reference'].includes(field)) return 'Doc. Ref.';
    if(field==='payment') return 'Pagamento';
    return 'Campo';
  };
  return `<div class="validation"><div class="validation-header"><strong>⚠️ Pendências encontradas (${issues.length}):</strong><small>Clique em qualquer item abaixo para ir diretamente ao campo correspondente e corrigir:</small></div><ul class="validation-list">${issues.map(i=>`<li class="validation-item"><button type="button" class="issue-link-btn" data-action="goto-field" data-field="${esc(i.field)}"><span class="issue-pill">${badgeMap(i.field)}</span><span class="issue-msg">${esc(i.message)}</span><span class="issue-jump">Ir para o campo ➔</span></button></li>`).join('')}</ul></div>`;
}

function highlightAndFocus(el){
  if(!el)return;
  el.scrollIntoView({behavior:'smooth',block:'center'});
  try{el.focus();}catch(e){}
  el.classList.add('field-highlight');
  setTimeout(()=>el.classList.remove('field-highlight'),3500);
}

function focusIssueField(field){
  if(!field)return;
  if(field.startsWith('company.')){
    currentDraft();
    const prop=field.replace('company.','');
    editCatalog('company',S.cid);
    setTimeout(()=>{const el=$(`#catalog-form [name="${prop}"]`);if(el)highlightAndFocus(el);},220);
    return;
  }
  if(field.startsWith('recipient')){
    currentDraft();
    if(!draft.recipient_id){
      const el=$('#note-form [name="recipient_id"]');
      if(el)highlightAndFocus(el);
      return;
    }
    const prop=field.replace('recipient.','');
    editCatalog('recipient',draft.recipient_id);
    setTimeout(()=>{const el=$(`#catalog-form [name="${prop}"]`);if(el)highlightAndFocus(el);},220);
    return;
  }
  if(field.startsWith('item.')){
    const parts=field.split('.');
    const index=parseInt(parts[1])||0;
    const rest=parts.slice(2).join('.');
    addItem(index);
    setTimeout(()=>{
      if(rest.includes('icms')||rest.includes('vBC')||rest.includes('pICMS')){taxTab='icms';renderTaxFields();}
      else if(rest.includes('st')||rest.includes('ST')){taxTab='st';renderTaxFields();}
      else if(rest.includes('fcp')||rest.includes('FCP')||rest.includes('fecoep')){taxTab='fcp';renderTaxFields();}
      else if(rest.includes('ipi')||rest.includes('IPI')){taxTab='ipi';renderTaxFields();}
      else if(rest.includes('pis')||rest.includes('PIS')){taxTab='pis';renderTaxFields();}
      else if(rest.includes('cofins')||rest.includes('COFINS')){taxTab='cofins';renderTaxFields();}
      else if(rest.includes('ibs')||rest.includes('IBS')||rest.includes('cbs')||rest.includes('CBS')||rest.includes('rtc')){taxTab='rtc';renderTaxFields();}
      const leaf=parts.at(-1);
      const el=$(`#item-form [name="${rest}"]`)||$(`#item-form [name="${leaf}"]`)||$(`#item-form [name$=".${leaf}"]`)||$(`#item-form #${leaf}`)||(leaf==='icms_code'?$('#item-form [data-tax-cst=ICMS]'):null);
      if(el)highlightAndFocus(el);
      else{const c=$('#tax-fields')||$('#item-form');if(c)c.scrollIntoView({behavior:'smooth',block:'center'});}
    },250);
    return;
  }
  if(field==='items'){
    const el=$('[data-action="add-item"]')||$('#note-items');
    if(el)highlightAndFocus(el);
    return;
  }
  const el=$(`#note-form [name="${field}"]`);
  if(el){
    const det=el.closest('details');if(det)det.open=true;
    highlightAndFocus(el);
  }
}

async function saveNote(prepare=false){
  const n=currentDraft();
  try{
    const r=await api('save_note',{id:n._id,data:n});
    draft._id=r.id;
    const stateRes=await fetch('/api/state?cid='+S.cid).then(r=>r.json());
    const foundDoc=stateRes.documents?.find(d=>d._id===r.id);
    if(foundDoc)draft.number=foundDoc.number;
    if($('#note-form [name="number"]'))$('#note-form [name="number"]').value=draft.number||'';
    if(prepare){
      await api('prepare',{id:r.id});
      closeDialog('note-modal');
      await refresh();
      noteDetail(r.id);
      toast('XML assinado e preparado. Revise o resumo antes de transmitir.');
    }else{
      closeDialog('note-modal');
      await refresh();
      toast('Rascunho salvo com sucesso.');
    }
  }catch(err){
    try{
      const val=await api('validate',{note:currentDraft()});
      if(val.issues&&val.issues.length){
        $('#note-validation').innerHTML=renderValidationIssues(val.issues);
        $('#note-validation').scrollIntoView({behavior:'smooth',block:'nearest'});
      }
    }catch(ve){}
    throw err;
  }
}
async function validateNote(){const r=await api('validate',{note:currentDraft()});$('#note-validation').innerHTML=renderValidationIssues(r.issues);$('#note-validation').scrollIntoView({behavior:'smooth',block:'nearest'});}
function selectedNote(id=selected){const n=S.documents?.find(d=>d._id===id);if(!n)throw Error('Selecione uma nota na lista.');return n;}
function noteDetail(id){const n=selectedNote(id);selected=id;dialog('detail-modal','NF-e '+n.number+' · '+envName(n.environment),`<div class="section"><h2>Resumo do documento</h2><div class="grid two"><div><small>Destinatário</small><p>${esc(n._recipient||'Pendente')}</p></div><div><small>Total da nota</small><h2>${brl(n._total)}</h2></div><div>Série: <b>${esc(n.series)}</b> · Número: <b>${esc(n.number)}</b></div><div>${badge(n._status)}</div></div><p class="hint">Chave de acesso</p><p style="overflow-wrap:anywhere">${esc(n._key||'Ainda não gerada')}</p>${n._reason?notice(esc(n._reason)):''}${n._status==='PREPARADA'?notice(`Confira destinatário, itens, série e número. ${n.environment==='1'?'<b>O envio em produção tem validade fiscal.</b>':'Este envio é de homologação, sem validade fiscal.'}`,'warning'):''}</div>`,`${['RASCUNHO','PREPARADA'].includes(n._status)?`<button data-action="preview-danfe" data-id="${id}" class="blue" title="Visualizar prévia do DANFE">📄 Prévia do DANFE</button>`:''}<button data-action="preview-note" data-id="${id}">Conferência simples</button>${n._fiscal_id?`<button data-action="xml-note" data-id="${id}">XML</button><button data-action="query-note" data-id="${id}">Consultar SEFAZ</button>`:''}${['RASCUNHO','PREPARADA'].includes(n._status)?`<button class="danger" data-action="delete-note" data-id="${id}">Excluir rascunho</button>`:''}${n._status==='PREPARADA'?`<button class="primary" data-action="transmit" data-id="${id}">Confirmar transmissão</button>`:''}${n._status==='AUTORIZADA'?`<button data-action="danfe" data-id="${id}">DANFE</button><button data-action="cce-note" data-id="${id}">Carta de correção</button><button class="danger" data-action="cancel-note" data-id="${id}">Cancelar NF-e</button>`:''}<button data-action="duplicate-note" data-id="${id}">Duplicar</button><button data-action="close-dialog" data-id="detail-modal">Voltar</button>`,'medium');}
function eventForm(kind,id){const n=selectedNote(id);if(n._status!=='AUTORIZADA')throw Error('Selecione uma NF-e autorizada.');const cancel=kind==='110111';dialog('event-modal',cancel?'Cancelamento da NF-e '+n.number:'Carta de correção — NF-e '+n.number,notice(cancel?'Confirme que a operação não ocorreu e que atende às condições e ao prazo de cancelamento. Este comando prepara o evento para sua revisão.':'A CC-e não pode alterar valores de impostos, quantidades, preço, emitente, destinatário ou data de emissão. Confira as condições de uso antes de registrar.','warning')+`<form id="event-form" data-kind="${kind}" data-doc="${n._fiscal_id}">${area('content',cancel?'Justificativa (15 a 255 caracteres)':'Correção (15 a 1.000 caracteres)')}${check('ack','Conferi as condições aplicáveis e os dados do evento')}</form>`,`<button data-action="close-dialog" data-id="event-modal">Voltar</button><button class="primary" data-action="prepare-event">Preparar evento</button>`,'small');}
function eventReview(id){const e=S.events.find(v=>v.id===id);if(!e)throw Error('Evento não encontrado.');dialog('event-review','Evento fiscal',`<p>Tipo: ${e.kind==='110110'?'Carta de correção':e.kind==='110111'?'Cancelamento':'Inutilização'}</p><p>${badge(e.status)}</p><p>${esc(e.reason||'Evento assinado, ainda não transmitido.')}</p><p>Ambiente: <b>${envName(e.environment)}</b></p>${e.kind==='INUT'?`<p>Faixa: ${e.start_number} a ${e.end_number} · Série ${e.series}</p>`:''}<p style="white-space:pre-wrap">${esc(e.content||'')}</p>${notice('O envio registra este evento na SEFAZ. Confira o conteúdo preparado antes de confirmar.','warning')}`,`<button data-action="event-xml" data-id="${id}">XML do evento</button>${e.status==='PREPARADO'?`<button class="primary" data-action="send-event" data-id="${id}">Confirmar envio do evento</button>`:''}${e.kind!=='INUT'?`<button data-action="query-event" data-id="${id}">Consultar</button>`:''}<button data-action="close-dialog" data-id="event-review">Voltar</button>`,'small');}
function inutilForm(){dialog('inutil-modal','Inutilização de numeração',notice('Confira o histórico completo de emissão, inclusive notas de outros sistemas. Números inutilizados não poderão ser usados.','warning')+`<form id="inutil-form"><div class="grid two">${field('year','Ano',{year:new Date().getFullYear()})}${field('series','Série',{series:S.company[S.company.environment==='1'?'production_series':'series']||'1'})}${field('start','Número inicial')}${field('end','Número final')}</div>${area('reason','Justificativa (15 a 255 caracteres)')}${check('ack','Conferi o histórico completo e a faixa sem emissão')}</form>`,`<button data-action="close-dialog" data-id="inutil-modal">Voltar</button><button class="primary" data-action="prepare-inutil">Preparar inutilização</button>`,'small');}
function importForm(){dialog('import-modal','Importar XML de NF-e',notice('Selecione XML processado com protocolo de autorização. O arquivo deve identificar esta empresa como emitente ou destinatária. A importação não consulta a situação atual na SEFAZ.')+`<input class="file-input" type="file" id="xml-file" accept=".xml" aria-label="Arquivo XML de NF-e">`,`<button data-action="close-dialog" data-id="import-modal">Voltar</button><button class="primary" data-action="apply-import">Importar XML</button>`,'small');}
async function fileBase64(file){if(!file)throw Error('Selecione um arquivo.');if(file.size>8*1024*1024)throw Error('O arquivo excede 8 MB.');const bytes=new Uint8Array(await file.arrayBuffer());let result='';for(let i=0;i<bytes.length;i+=32768)result+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(result);}
function renderFinance(){const docs=(S.documents||[]).filter(n=>n.environment===S.company.environment&&n._status==='AUTORIZADA');const total=docs.reduce((s,n)=>s+Number(n._total),0);const invoiced=docs.filter(n=>n.invoice_number);return `<div class="stats"><div class="stat"><span>Notas autorizadas</span><strong>${docs.length}</strong></div><div class="stat"><span>Total autorizado</span><strong>${brl(total)}</strong></div><div class="stat"><span>Faturas informadas</span><strong>${invoiced.length}</strong></div><div class="stat"><span>Ambiente</span><strong style="font-size:18px">${envName(S.company.environment)}</strong></div></div>${notice('Visão das faturas e duplicatas das notas autorizadas. Não há integração bancária nem controle de baixa de pagamentos nesta versão.')}<div class="panel"><table><thead><tr><th>NF-e</th><th>Destinatário</th><th>Fatura</th><th>Valor líquido</th><th>Duplicatas</th></tr></thead><tbody>${invoiced.map(n=>`<tr><td>${esc(n.number)}</td><td>${esc(n._recipient)}</td><td>${esc(n.invoice_number)}</td><td>${brl(n.invoice_net)}</td><td>${esc(n.duplicates||'—')}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">Nenhuma fatura em nota autorizada.</td></tr>'}</tbody></table></div>`;}
function renderReports(){const docs=(S.documents||[]).filter(n=>n.environment===S.company.environment),authorized=docs.filter(n=>n._status==='AUTORIZADA'),rejected=docs.filter(n=>n._status==='REJEITADA'),total=authorized.reduce((s,n)=>s+Number(n._total),0);const months=Array.from({length:12},(_,i)=>`${new Date().getFullYear()}-${String(i+1).padStart(2,'0')}`),amounts=months.map(m=>authorized.filter(n=>n.issued_at.startsWith(m)).reduce((s,n)=>s+Number(n._total),0)),max=Math.max(1,...amounts);return `<div class="stats"><div class="stat"><span>Autorizadas</span><strong>${authorized.length}</strong></div><div class="stat"><span>Total autorizado</span><strong>${brl(total)}</strong></div><div class="stat"><span>Rascunhos</span><strong>${docs.filter(n=>n._status==='RASCUNHO').length}</strong></div><div class="stat"><span>Rejeitadas</span><strong>${rejected.length}</strong></div></div><div class="section"><h2>Emissões autorizadas por mês · ${new Date().getFullYear()}</h2><div class="report-bars">${amounts.map((v,i)=>`<div class="report-bar" title="${brl(v)}"><div class="fill" style="height:${Math.max(1,v/max*140)}px"></div><small>${['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][i]}</small></div>`).join('')}</div><p class="hint">Somente autorizações confirmadas, no ambiente ${envName(S.company.environment).toLowerCase()}. Passe sobre as barras para ver os valores.</p><button class="primary" data-action="export-csv">↓ Exportar todas as notas em CSV</button></div>`;}
function renderConfig(){const co=S.company,c=S.certificate;return `<div class="section"><div class="config-row"><div><h2>Empresas</h2><p>${co?esc(co.xNome)+' · '+esc(co.CNPJCPF):'Nenhuma empresa cadastrada.'}</p></div><div class="actions">${co?`<button data-action="edit-company">Editar empresa ativa</button>`:''}<button class="primary" data-action="new-company">⊞ Nova empresa</button></div></div></div>${co?`<div class="section"><h2>Certificado digital A1</h2>${S.preview?notice('Esta é uma prévia para avaliação. Carregue o certificado somente no pacote local do Windows.','warning'):notice('O arquivo A1 e a senha ficam em memória por uma hora. O certificado não é incluído nos backups. Ao encerrar o serviço, a sessão é encerrada.')}<div class="config-row"><div>${c?`<p class="notice success">Certificado carregado · CNPJ ${esc(c.cnpj)}<br>Validade: ${esc(c.expires.slice(0,10))}<br>Sessão até ${new Date(c.session_expires*1000).toLocaleTimeString('pt-BR')}</p>`:'<p>Nenhum certificado carregado.</p>'}</div><div class="actions"><button class="primary" data-action="certificate">Carregar A1 (.pfx / .p12)</button>${c?'<button data-action="forget-certificate">Encerrar sessão do A1</button>':''}</div></div><p class="hint">Certificados A3 / token não são suportados nesta versão.</p></div><div class="section"><h2>Emissão e ambientes</h2><p>Ambiente ativo: <b>${envName(co.environment)}</b>. Série: <b>${esc(co[co.environment==='1'?'production_series':'series']||'1')}</b></p><p>Conector: <b>Alagoas / SVRS, CRT 1 e CRT 3, 2026</b>.</p><p class="hint">No regime normal, ICMS, FCP, ST, IPI, II, PIS/COFINS, DIFAL e os grupos da reforma tributária são configurados no item. Fórmulas comuns têm cálculo automático; grupos especiais exigem revisão manual. No Simples Nacional, ST/FECOEP ST e IPI devolvido permanecem restritos à homologação. Consulte a cobertura no pacote antes do uso fiscal.</p><button data-action="sefaz-status">Consultar status SEFAZ</button></div>`:''}<div class="section"><h2>Backup dos dados</h2><p>O banco, os XML e o histórico fiscal ficam na pasta <b>dados</b>, junto do programa. O backup gera uma cópia que pode ser guardada em outro disco.</p><button class="primary" data-action="backup">↓ Baixar backup completo</button><p class="hint">Para restaurar: encerre o emissor, preserve uma cópia da pasta atual e extraia a pasta dados do backup na pasta do programa.</p></div>`;}
function certificateForm(){if(S.preview)throw Error('O certificado é carregado somente no aplicativo local do Windows.');dialog('certificate-modal','Carregar certificado A1',notice('Selecione o certificado da empresa ativa. O arquivo e a senha não são gravados nos dados do aplicativo.')+`<form id="certificate-form"><label class="field">Arquivo A1 (.pfx / .p12)<input type="file" id="cert-file" accept=".pfx,.p12"></label><br><label class="field">Senha do certificado<input type="password" id="cert-password" autocomplete="off"></label></form>`,`<button data-action="close-dialog" data-id="certificate-modal">Voltar</button><button class="primary" data-action="load-certificate">Carregar por uma hora</button>`,'small');}
function renderHelp(){return `<div class="section"><h2>Comece por aqui</h2><ol class="guide-list"><li>Em <b>Configurações</b>, cadastre a empresa, endereço completo, IE e numeração.</li><li>Cadastre os <b>Clientes</b>, <b>Produtos</b> e os perfis em <b>Tributação</b>.</li><li>Crie uma <b>Nova NF-e</b>. Confira destinatário, operação e itens.</li><li>Em cada produto, preencha os impostos nos tópicos <b>ICMS, ICMS ST, FECOEP ST, IPI, PIS e COFINS</b>.</li><li>Use <b>Conferir</b> para ver pendências. <b>Apenas salvar</b> mantém um rascunho.</li><li>Carregue o A1 em Configurações. <b>Salvar e enviar</b> assina e abre o resumo para confirmar a transmissão.</li><li>Depois da autorização, baixe o <b>XML</b> e o <b>DANFE</b>.</li></ol></div><div class="section"><h2>Uso no computador</h2><p>Instale com o arquivo Setup e abra pelo ícone <b>VF Emissor</b> na área de trabalho. As atualizações são verificadas no início. Para fechar o serviço, use <b>Encerrar programa</b>.</p><p>O endereço local é <b>http://127.0.0.1:8787</b>. O programa atende somente neste computador. Consultas e transmissões à SEFAZ exigem internet.</p><p>O banco e os XML ficam em %LOCALAPPDATA%\\VFEmissor\\Dados. Atualizações preservam essa pasta. Guarde também backups da empresa. A senha do NF-e Mais não é utilizada pelo emissor local.</p></div><div class="section"><h2>Cobertura desta versão</h2><p>Interface própria baseada na organização observada no NF-e Mais. Não é um produto da Zipline e não utiliza sua assinatura nem seu servidor para autorizar notas.</p><p>Conector fiscal AL, CRT 1 e CRT 3, ano 2026. Vendas e operações aceitas pelo validador; pagamentos simplificados e detalhados no CRT 3. No Simples Nacional, ST/FECOEP ST e IPI devolvido apenas em homologação. Cálculos e bloqueios seguem a cobertura documentada no pacote.</p><p>Emissão não foi validada com o A1 da sua empresa. Faça o primeiro teste em homologação e confira o retorno da SEFAZ antes de habilitar produção.</p><p class="hint">NFS-e, NFC-e, DF-e automático, exportação, grupos de produtos específicos, outros conectores de UF e autenticação para hospedagem pública não estão implementados. No CRT 3, os grupos tributários completos do leiaute são editáveis; fórmulas comuns têm cálculo automático e os grupos especiais exigem revisão manual. Veja COBERTURA.md no pacote.</p></div>`;}

const handlers={
 'refresh':async()=>{await refresh();toast('Lista atualizada.');},'help':()=>location.hash='ajuda','backup':()=>download('backup'),
 'logout':async()=>{if(!confirm('Deseja encerrar a sessão desta empresa e voltar ao login?'))return;await fetch('/api/logout',{method:'POST'});await refresh();toast('Sessão encerrada.');},
 'login-new-company':()=>editCatalog('company'),
 'tab':b=>{tab=b.dataset.id;selected='';render();},'all-months':()=>{month='';render();},
 'new-company':()=>editCatalog('company'),'edit-company':()=>editCatalog('company',S.cid),
 'new-catalog':b=>editCatalog(b.dataset.kind),'edit-catalog':b=>editCatalog(b.dataset.kind,b.dataset.id),'save-catalog':saveCatalog,
 'close-dialog':b=>b.dataset.id==='note-modal'?handlers['close-note']():closeDialog(b.dataset.id),'close-note':()=>{if(confirm('Fechar a edição? Alterações ainda não salvas serão descartadas.'))closeDialog('note-modal');},
 'archive':async b=>{if(confirm('Arquivar este cadastro? Os documentos existentes serão preservados.')){await api('archive',{kind:b.dataset.kind,id:b.dataset.id});await refresh();toast('Registro arquivado.');}},
 'delete-note':async b=>{const id=b.dataset.id;if(!id)return;if(!confirm('Deseja realmente excluir este rascunho de nota fiscal? Esta operação não pode ser desfeita.'))return;await api('delete_note',{id});closeDialog('detail-modal');closeDialog('note-modal');await refresh();toast('Rascunho excluído com sucesso.');},
 'delete-draft':async b=>handlers['delete-note'](b),
 'edit-note-company':()=>{currentDraft();editCatalog('company',S.cid);},
 'edit-note-recipient':()=>{currentDraft();if(!draft.recipient_id)throw Error('Selecione um cliente para editar.');editCatalog('recipient',draft.recipient_id);},
 'goto-field':b=>focusIssueField(b.dataset.field),
 'preview-danfe':async b=>{let id=b?.dataset?.id;if(!id&&$('#note-form')){const n=currentDraft();const r=await api('save_note',{id:n._id,data:n});draft._id=r.id;id=r.id;await refresh(S.cid);}if(!id)id=selected;if(!id)throw Error('Selecione ou salve a nota para visualizar o DANFE.');download('danfe_preview',id);},
 'new-note':()=>openNote(),'edit-note':b=>openNote(b.dataset.id),'note-detail':b=>noteDetail(b.dataset.id),
 'add-item':()=>addItem(),'edit-item':b=>addItem(Number(b.dataset.id)),'remove-item':b=>{draft.items.splice(Number(b.dataset.id),1);renderItems();updateTotals();},
 'add-catalog-items':catalogItems,'pick-product':b=>{closeDialog('pick-products');addItem(-1,S.products.find(p=>p._id===b.dataset.id));},
 'tax-tab':b=>{itemDraft=gather($('#item-form'),itemDraft);taxTab=b.dataset.id;$$('.tax-tabs button').forEach(x=>x.classList.toggle('active',x.dataset.id===taxTab));renderTaxFields();},
 'save-item':saveItem,'save-note':()=>saveNote(false),'prepare-note':()=>saveNote(true),'validate-note':validateNote,
 'preview-note':b=>download('preview',b.dataset.id),'xml-note':b=>download('xml',selectedNote(b.dataset.id)._fiscal_id),
 'danfe':b=>{const n=selectedNote(b.dataset.id||selected);if(n._status!=='AUTORIZADA')throw Error('O DANFE exige autorização confirmada. Use Detalhes → Conferência para um rascunho.');download('danfe',n._fiscal_id);},
 'query-note':async b=>{const n=selectedNote(b.dataset.id||selected);if(!n._fiscal_id)throw Error('Este rascunho ainda não possui XML assinado.');const r=await api('query',{id:n._fiscal_id});await refresh();toast('Retorno: '+r.status);if($('#detail-modal'))noteDetail(n._id);},
 'transmit':async b=>{const n=selectedNote(b.dataset.id);try{const r=await api('send',{id:n._fiscal_id,ack_key:n._key});await refresh();noteDetail(n._id);toast('Retorno: '+r.status);}catch(e){await refresh();noteDetail(n._id);throw e;}},
 'duplicate-note':async b=>{const n=(await api('duplicate',{id:b.dataset.id})).note;closeDialog('detail-modal');await openNote('',n);},
 'sefaz-status':async()=>{const r=await api('sefaz_status');toast(r.message);},
 'cancel-note':b=>eventForm('110111',b.dataset.id||selected),'cce-note':b=>eventForm('110110',b.dataset.id||selected),
 'new-event':()=>{const docs=S.documents.filter(n=>n._status==='AUTORIZADA'&&n.environment===S.company.environment);if(!docs.length)throw Error('É necessário ter uma NF-e autorizada para criar uma carta de correção.');dialog('pick-event','Selecionar NF-e',docs.map(n=>`<p><button data-action="cce-note" data-id="${n._id}">NF-e ${esc(n.number)} · ${esc(n._recipient)}</button></p>`).join(''),'','medium');},
 'prepare-event':async()=>{const f=$('#event-form'),v=gather(f);const r=await api('event_prepare',{id:f.dataset.doc,kind:f.dataset.kind,content:v.content,ack:v.ack==='1'});closeDialog('event-modal');await refresh();eventReview(r.id);},
 'event-review':b=>eventReview(b.dataset.id),'event-xml':b=>download('event_xml',b.dataset.id),'send-event':async b=>{const r=await api('event_send',{id:b.dataset.id,ack:true});await refresh();eventReview(b.dataset.id);toast('Retorno: '+r.status);},
 'query-event':async b=>{const r=await api('event_query',{id:b.dataset.id});await refresh();eventReview(b.dataset.id);toast('Retorno: '+r.status);},
 'inutil':inutilForm,'prepare-inutil':async()=>{const v=gather($('#inutil-form'));const r=await api('inutil_prepare',{...v,ack:v.ack==='1'});closeDialog('inutil-modal');await refresh();eventReview(r.id);},
 'import-xml':importForm,'apply-import':async()=>{const data=await fileBase64($('#xml-file').files[0]);const r=await api('import_xml',{data});closeDialog('import-modal');await refresh();toast(r.message);},
 'received-xml':b=>download('received_xml',b.dataset.id),'export-csv':()=>download('csv'),
 'certificate':certificateForm,'load-certificate':async()=>{const data=await fileBase64($('#cert-file').files[0]),password=$('#cert-password').value;try{await api('load_certificate',{data,password,remember:$('#cert-remember').checked});closeDialog('certificate-modal');await refresh();toast('Certificado carregado para esta empresa.');}finally{if($('#cert-password'))$('#cert-password').value='';}},
 'forget-certificate':async()=>{await api('forget_certificate');await refresh();toast('Sessão do certificado encerrada.');}
};
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action]');if(!b)return;e.preventDefault();const h=handlers[b.dataset.action];if(!h)return;const wasDisabled=b.disabled;b.disabled=true;document.body.classList.add('busy');try{await h(b);}catch(err){toast(err.message,true);}finally{b.disabled=wasDisabled;document.body.classList.remove('busy');}});
document.addEventListener('submit',async e=>{
  if(e.target.id==='login-form'){
    e.preventDefault();
    const cnpj=$('#login-cnpj')?.value,password=$('#login-password')?.value;
    try{
      const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cnpj,password})});
      const data=await r.json();
      if(!r.ok)throw Error(data.error||'Erro ao autenticar.');
      toast('Empresa '+(data.name||'')+' acessada.');
      await refresh();
    }catch(err){toast(err.message,true);}
    return;
  }
  e.preventDefault();
});
document.addEventListener('change',async e=>{const t=e.target;try{
 if(t.id==='company-switch'){selected='';await refresh(t.value);}
 if(t.id==='month-filter'){month=t.value;render();}
 if(t.dataset.select){selected=t.checked?t.dataset.select:'';render();}
 if(t.id==='item-rule'&&t.value){itemDraft=gather($('#item-form'),itemDraft);itemDraft.rule=structuredClone(S.rules.find(r=>r._id===t.value));renderItem();}
 if(t.closest('#item-form')){clearTimeout(calculateItem.timer);calculateItem.timer=setTimeout(calculateItem,250);}
 if(t.name==='recipient_id'){currentDraft();const r=S.recipients.find(r=>r._id===t.value);if(r){draft.destination=r.UF===S.company.UF?'1':'2';draft.final=r.indIEDest==='9'?'1':draft.final;}renderNote();}
}catch(err){toast(err.message,true);}});
document.addEventListener('input',e=>{const t=e.target;
 if(t.id==='login-cnpj')t.value=t.value.replace(/\D/g,'').slice(0,14);
 if(t.id==='note-search'){const pos=t.selectionStart;search=t.value;render();$('#note-search').focus();$('#note-search').setSelectionRange(pos,pos);}
 if(t.id==='catalog-search'){const value=t.value.toLowerCase();$$('#catalog-table tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(value));}
 if(t.closest('#item-form')){clearTimeout(calculateItem.timer);calculateItem.timer=setTimeout(calculateItem,160);}});
window.addEventListener('hashchange',()=>{render();refresh().catch(e=>toast(e.message,true));});
window.addEventListener('beforeunload',e=>{if($('#note-modal')){e.preventDefault();e.returnValue='';}});
refresh().catch(e=>{$('#content').innerHTML=notice(esc(e.message),'warning');});
