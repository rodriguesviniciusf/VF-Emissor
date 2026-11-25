const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/duplicate-ui.js'),'utf8');
function setup({blocked=false,matches=true,approved=false}={}){
 const calls=[],closed=[],details=[],nodes={};let body='';
 const review={matches:matches?[{source:'old-note',number:10,series:1,status:blocked?'INCERTA':'AUTORIZADA',issued_at:'2026-11-01T10:00:00-03:00'}]:[],blocked,approved,token:'review-token',revision:'draft-revision',recipient:'Cliente de teste',environment:'2'};
 const context=vm.createContext({S:{cid:'company-a',documents:[{_id:'old-note'}]},handlers:{},__review:review,
  $:s=>nodes[s]||null,esc:v=>String(v??''),badge:v=>String(v),envName:()=> 'Homologação',notice:t=>t,
  api:async(command,p)=>{calls.push({command,p});return command==='duplicate_review'?review:{fiscal_id:'prepared'};},
  closeDialog:id=>closed.push(id),noteDetail:id=>details.push(id),selectedNote:()=>({_duplicate_reason:''}),
  dialog:(id,title,html)=>{context.closeDialog(id);body=html;nodes['#duplicate-review .dialog-head button']={dataset:{}};nodes['#duplicate-reason']={value:'',focus(){}};nodes['#duplicate-ack']={checked:false,focus(){}};nodes['#duplicate-form-error']={textContent:''};}
 });
 vm.runInContext(source,context);
 return {context,calls,closed,details,nodes,get body(){return body;},async open(){const promise=vm.runInContext('api("prepare",{id:"draft-a",simple_review_hash:"original-review"})',context);await new Promise(setImmediate);return {promise};},act:name=>context.handlers[name]()};
}
test('shows authorized note and waits for an explicit reason before preparation',async()=>{
 const x=setup(),{promise}=await x.open();assert.match(x.body,/NF-e 10/);assert.match(x.body,/duplicate-reason/);assert.equal(x.calls.length,1);assert.equal(x.nodes['#duplicate-review .dialog-head button'].dataset.action,'duplicate-cancel');
 x.nodes['#duplicate-reason'].value='Nova venda referente ao pedido 123.';x.nodes['#duplicate-ack'].checked=true;x.act('duplicate-confirm');await promise;
 assert.equal(x.calls[1].command,'prepare');assert.equal(x.calls[1].p.duplicate_reason,'Nova venda referente ao pedido 123.');assert.equal(x.calls[1].p.duplicate_ack,true);assert.equal(x.calls[1].p.duplicate_revision,'draft-revision');assert.equal(x.calls[1].p.simple_review_hash,'original-review');
});
test('short reason and unchecked confirmation keep the review open',async()=>{
 const x=setup(),{promise}=await x.open();x.nodes['#duplicate-reason'].value='Nova venda';x.act('duplicate-confirm');assert.match(x.nodes['#duplicate-form-error'].textContent,/15/);assert.equal(x.calls.length,1);
 x.nodes['#duplicate-reason'].value='Nova venda com produtos e valores iguais.';x.act('duplicate-confirm');assert.match(x.nodes['#duplicate-form-error'].textContent,/Confirme/);assert.equal(x.calls.length,1);
 x.act('duplicate-cancel');await assert.rejects(promise,/rascunho/);
});
test('cancel or close parent settles the pending operation without preparing',async()=>{
 for(const close of ['cancel','parent']){const x=setup(),{promise}=await x.open();if(close==='cancel')x.act('duplicate-cancel');else x.context.closeDialog('note-modal');await assert.rejects(promise,/rascunho/);assert.equal(x.calls.length,1);}
});
test('unresolved operation has no justification path',async()=>{
 const x=setup({blocked:true}),{promise}=await x.open();assert.doesNotMatch(x.body,/id="duplicate-reason"/);x.act('duplicate-confirm');assert.equal(x.calls.length,1);x.act('duplicate-cancel');await assert.rejects(promise,/Consulte/);
});
test('changing company while review is open never prepares another company',async()=>{
 const x=setup(),{promise}=await x.open();x.context.S.cid='company-b';assert.throws(()=>x.act('duplicate-confirm'),/empresa mudou/);await assert.rejects(promise);assert.equal(x.calls.length,1);
});
test('view existing note keeps the justification review pending',async()=>{
 const x=setup(),{promise}=await x.open();x.context.handlers['duplicate-inspect']({dataset:{id:'old-note'}});assert.deepEqual(x.details,['old-note']);assert.equal(x.calls.length,1);x.act('duplicate-cancel');await assert.rejects(promise);
});
test('no match or previously reviewed note proceeds through the original API',async()=>{
 for(const options of [{matches:false},{approved:true}]){const x=setup(options),{promise}=await x.open();await promise;assert.equal(x.calls[1].command,'prepare');assert.equal(x.body,'');}
});
