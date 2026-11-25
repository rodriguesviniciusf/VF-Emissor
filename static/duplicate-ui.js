'use strict';
// The justification authorizes only a reviewed new operation. The fiscal engine
// rechecks the document set during preparation and before transmission.
(()=>{
 let pending=null;
 function finish(value){const state=pending;if(!state)return;pending=null;state.observer?.disconnect();closeDialog('duplicate-review');state.resolve(value);}
 const closeBeforeDuplicate=closeDialog;
 closeDialog=function(id){if(pending&&(id==='duplicate-review'||id==='note-modal'))finish(null);return closeBeforeDuplicate(id);};
 function requestReview(review,context){
  if(pending)throw Error('Já existe uma conferência de duplicidade aberta.');
  return new Promise(resolve=>{
   const rows=review.matches.map(m=>`<tr><td><b>NF-e ${esc(m.number)}</b><small>Série ${esc(m.series)}</small></td><td>${esc(m.issued_at?m.issued_at.slice(0,10).split('-').reverse().join('/'):'Não informada')}</td><td>${badge(m.status)}</td><td>${(S.documents||[]).some(n=>n._id===m.source)?`<button type="button" data-action="duplicate-inspect" data-id="${esc(m.source)}">Ver nota</button>`:''}</td></tr>`).join('');
   dialog('duplicate-review',review.blocked?'Confira a situação da nota existente':'Justificar nova operação',`<div class="duplicate-intro">${notice(review.blocked?'Há uma operação semelhante em processamento ou com resultado incerto. Consulte a situação da nota existente antes de criar outra.':'Já existe nota autorizada com destinatário e itens iguais. Confira o documento abaixo antes de continuar.','warning')}<p><b>${esc(review.recipient)}</b> · ${esc(envName(review.environment))}</p></div><div class="table-wrap"><table><thead><tr><th>Documento</th><th>Emissão</th><th>Situação</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${review.blocked?'':`<form id="duplicate-justification-form"><label class="field">Justificativa da nova operação<textarea id="duplicate-reason" name="reason" minlength="15" maxlength="1000" required placeholder="Ex.: Nova venda referente ao pedido 123, realizada em outra data, com os mesmos produtos e valores."></textarea></label><p class="hint">Descreva a operação que realmente ocorreu, com pedido, data ou outro identificador. Mínimo de 15 caracteres. O registro fica no histórico local desta nota.</p><label class="check"><input type="checkbox" id="duplicate-ack">Conferi a nota existente e confirmo que esta é uma nova operação legítima.</label><p id="duplicate-form-error" role="alert"></p></form>`}`,`<button type="button" data-action="duplicate-cancel">Voltar sem emitir</button>${review.blocked?'':'<button type="button" class="primary" data-action="duplicate-confirm">Confirmar justificativa e continuar</button>'}`,'medium');
   // dialog() closes a previous instance before creating the new one; assign the
   // pending promise only after that lifecycle has completed.
   pending={resolve,context,review};
   if(typeof MutationObserver!=='undefined'){
    const state=pending,overlay=$('#duplicate-review');
    state.observer=new MutationObserver(()=>{if(pending===state&&!overlay.isConnected)finish(null);});
    state.observer.observe($('#modal-root'),{childList:true});
   }
   const close=$('#duplicate-review .dialog-head button');if(close)close.dataset.action='duplicate-cancel';
  });
 }
 handlers['duplicate-cancel']=()=>finish(null);
 handlers['duplicate-inspect']=b=>noteDetail(b.dataset.id);
 handlers['duplicate-confirm']=()=>{
  const state=pending;if(!state||state.review.blocked)return;
  if(state.context!==S.cid){finish(null);throw Error('A empresa mudou. Reabra a nota na empresa correta.');}
  const reason=$('#duplicate-reason').value.trim(),ack=$('#duplicate-ack').checked,error=$('#duplicate-form-error');
  if(reason.length<15||reason.length>1000){error.textContent='Escreva uma justificativa de 15 a 1.000 caracteres.';$('#duplicate-reason').focus();return;}
  if(!ack){error.textContent='Confirme que conferiu a nota existente e que se trata de uma nova operação.';$('#duplicate-ack').focus();return;}
  finish({duplicate_ack:true,duplicate_reason:reason,duplicate_approval:state.review.token,duplicate_revision:state.review.revision});
 };
 const apiBeforeDuplicate=api;
 api=async function(command,p={}){
  if(command!=='prepare')return apiBeforeDuplicate(command,p);
  const context=S.cid,review=await apiBeforeDuplicate('duplicate_review',{id:p.id});
  if(context!==S.cid)throw Error('A empresa mudou. Reabra a nota na empresa correta.');
  if(!review.matches.length||review.approved)return apiBeforeDuplicate(command,p);
  const approval=await requestReview(review,context);
  if(!approval)throw Error(review.blocked?'Consulte a situação da nota existente antes de criar outra.':'Emissão interrompida. A nova nota continua salva como rascunho.');
  if(context!==S.cid)throw Error('A empresa mudou. Reabra a nota na empresa correta.');
  return apiBeforeDuplicate(command,{...p,...approval});
 };
 const detailBeforeDuplicate=noteDetail;
 noteDetail=function(id){detailBeforeDuplicate(id);const reason=selectedNote(id)._duplicate_reason;if(reason)$('#detail-modal .dialog-body').insertAdjacentHTML('beforeend',`<section class="section duplicate-record"><h2>Justificativa de nova operação</h2><p>${esc(reason)}</p><small>Registro interno vinculado à conferência de duplicidade desta NF-e.</small></section>`);};
})();
