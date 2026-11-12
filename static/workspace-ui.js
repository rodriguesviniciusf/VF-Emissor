'use strict';
// Apresentação: usa somente os cadastros e filtros já carregados pela empresa ativa.
const workspacePaths={
 inicio:'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
 clientes:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
 produtos:'m12 3 9 5-9 5-9-5 9-5ZM3 8v9l9 5 9-5V8M12 13v9M7.5 5.5l9 5',
 tributacao:'M4 3h16v18H4zM8 7h8M8 11h2M14 11h2M8 15h2M14 15h2M8 18h2M14 18h2',
 financeiro:'M20 7H4V4h14M4 7v13h17V7ZM21 11h-6v5h6M17 13.5h.01',
 relatorios:'M4 3v18h17M8 16v-4M13 16V7M18 16V10',
 configuracoes:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M10 3h4l.6 3 2.1 1.2 2.8-1 2 3.5-2.2 2v2.5l2.2 2-2 3.5-2.8-1-2.1 1.2L14 23h-4l-.6-3.1-2.1-1.2-2.8 1-2-3.5 2.2-2v-2.5l-2.2-2 2-3.5 2.8 1L9.4 6 10 3Z',
 ajuda:'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4M12 17h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
 add:'M12 5v14M5 12h14',
 money:'M12 2v20M17 5H9a3 3 0 0 0 0 6h6a3 3 0 0 1 0 6H6',
 note:'M14 2H5v20h14V7l-5-5ZM14 2v6h5M8 12h8M8 16h5',
 draft:'M4 20h4l12-12-4-4L4 16v4ZM14 6l4 4'};
function workspaceIcon(name){return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${workspacePaths[name]||workspacePaths.note}"/></svg>`;}
function workspaceMetric(label,value,hint,icon,featured=false){return `<article class="workspace-metric${featured?' featured':''}"><span class="metric-label">${esc(label)}${workspaceIcon(icon)}</span><strong>${esc(value)}</strong><small>${esc(hint)}</small></article>`;}
function workspaceOverview(){
 const notes=filteredNotes(),authorized=notes.filter(n=>n._status==='AUTORIZADA'),drafts=notes.filter(n=>['RASCUNHO','PREPARADA'].includes(n._status));
 const parts=month.split('-'),period=month?new Date(Number(parts[0]),Number(parts[1])-1,1).toLocaleDateString('pt-BR',{month:'long',year:'numeric'}):'Todos os meses';
 return `<section class="workspace-hero"><div><span class="hero-eyebrow">SEU ESPAÇO DE TRABALHO</span><h2>Sua rotina fiscal, <em>mais organizada.</em></h2><p>Notas, produtos e cadastros reunidos em um só lugar.</p></div><div class="hero-period">Período selecionado<b>${esc(period)}</b>${envName(S.company.environment)} · ${S.company.CRT==='3'?'Regime Normal':'Simples Nacional'}</div></section><div class="workspace-metrics">${workspaceMetric('Valor autorizado',brl(authorized.reduce((sum,n)=>sum+Number(n._total||0),0)),'Nas notas do filtro atual','money',true)}${workspaceMetric('Notas autorizadas',String(authorized.length),'No período selecionado','note')}${workspaceMetric('Rascunhos e preparadas',String(drafts.length),'Aguardando conclusão','draft')}${workspaceMetric('Produtos cadastrados',String((S.products||[]).length),'Da empresa acessada','produtos')}</div>`;
}
const renderBeforeWorkspace=render;
render=function(){
 renderBeforeWorkspace();if(S.authenticated===false)return;
 document.body.dataset.workspacePage=page;
 const heading=$('#page-title');if(heading&&!heading.parentElement.classList.contains('page-heading-copy')){const copy=document.createElement('div');copy.className='page-heading-copy';heading.before(copy);copy.append(heading);}
 if(!$('.nav-caption')){const caption=document.createElement('div');caption.className='nav-caption';caption.textContent='ESPAÇO DE TRABALHO';$('#sidebar nav')?.before(caption);}
 $$('nav a[data-page]').forEach(a=>{const id=a.dataset.page;a.setAttribute('title',titles[id]);if(a.classList.contains('active'))a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');a.innerHTML=`<i>${workspaceIcon(id)}</i><span>${esc(titles[id])}</span>`;});
 const action=$('.page-head [data-action="new-note"]');if(action)action.innerHTML=workspaceIcon('add')+'Nova NF-e';
 const logout=$('.logout-top-btn');if(logout)logout.textContent=S.access?.enabled?'Sair':'Sair / trocar empresa';
 const noteTabs={nfe:'NF-e',cce:'Cartas de correção',fornecedor:'Fornecedor',recebidas:'Recebidas'};
 $$('.tabs [data-action="tab"]').forEach(b=>{if(noteTabs[b.dataset.id])b.innerHTML=workspaceIcon('note')+esc(noteTabs[b.dataset.id]);});
 const content=$('#content');if(page==='inicio'&&S.company&&S.cid)content.insertAdjacentHTML('afterbegin',workspaceOverview());
 const intros={clientes:['Seus clientes organizados para agilizar a próxima emissão.',(S.recipients||[]).length+' clientes'],produtos:['Encontre seus produtos e mantenha os cadastros sempre à mão.',(S.products||[]).length+' produtos'],tributacao:['Perfis fiscais da empresa, reunidos para revisão e aplicação.',(S.rules||[]).length+' perfis'],configuracoes:['Tudo o que sua empresa precisa para emitir com os dados corretos.','Por empresa'],financeiro:['Acompanhe os recebimentos vinculados às suas notas fiscais.','Visão financeira'],relatorios:['Consulte o movimento da empresa com clareza.','Visão geral'],ajuda:['Um guia para acompanhar você em cada etapa da emissão.','Primeiros passos']};
 if(intros[page]){const [text,count]=intros[page];content.insertAdjacentHTML('afterbegin',`<div class="workspace-intro"><p>${esc(text)}</p><span class="workspace-count">${esc(count)}</span></div>`);}
};
if(S.version)render();
document.addEventListener('click',e=>{const context=$('.account-context[open]');if(context&&!context.contains(e.target))context.open=false;});
document.addEventListener('keydown',e=>{const context=$('.account-context[open]');if(e.key==='Escape'&&context){const focused=context.contains(document.activeElement);context.open=false;if(focused)context.querySelector('summary')?.focus();}});
