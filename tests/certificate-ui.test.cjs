const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8').replace("refresh().catch(e=>{$('#content').innerHTML=notice(esc(e.message),'warning');});",'');
function setup({remember=true,legacy=false,file=true}={}){
 const nodes={},calls=[],messages=[];const password={value:'synthetic-password'};
 const form={isConnected:true,querySelector:s=>s==='#cert-file'?{files:file?[{}]:[]}:s==='#cert-password'?password:s==='#cert-remember'?(legacy?null:{checked:remember}):null};nodes['#certificate-form']=form;
 const context=vm.createContext({document:{querySelector:s=>nodes[s]||null,querySelectorAll:()=>[],addEventListener:()=>{}},window:{addEventListener:()=>{}},setTimeout:()=>0,clearTimeout:()=>{},structuredClone,__api:async(a,p)=>{calls.push({action:a,...p});return {saved:p.remember};},__toast:s=>messages.push(s),__close:()=>{form.isConnected=false;},__read:async()=> 'SYNTHETIC-PFX',__dialog:(_id,_title,body)=>{context.body=body;}});
 vm.runInContext(source,context);vm.runInContext("S={cid:'company-a',preview:false};api=__api;refresh=async()=>{};fileBase64=__read;toast=__toast;closeDialog=__close;dialog=__dialog;",context);
 return {context,calls,messages,form,password,load:()=>vm.runInContext("handlers['load-certificate']()",context)};
}
test('certificate button resolves the current form, including checked persistence',()=>{
 const x=setup();vm.runInContext("handlers.certificate()",x.context);assert.match(x.context.body,/id="cert-remember" checked/);
 vm.runInContext("certificateForm=()=>{globalThis.currentFormOpened=true;};handlers.certificate();",x.context);assert.equal(x.context.currentFormOpened,true);
});
test('saves certificate and password by default and clears the input',async()=>{
 const x=setup();await x.load();assert.equal(x.calls[0].remember,true);assert.equal(x.calls[0].cid,'company-a');assert.equal(x.calls[0].password,'synthetic-password');assert.equal(x.password.value,'');assert.match(x.messages[0],/salvos com proteção/);
});
test('legacy form without checkbox also persists and never reads null.checked',async()=>{
 const x=setup({legacy:true});await x.load();assert.equal(x.calls[0].remember,true);
});
test('explicit unchecked choice remains session-only',async()=>{
 const x=setup({remember:false});await x.load();assert.equal(x.calls[0].remember,false);assert.match(x.messages[0],/somente para esta sessão/);
});
test('no selected file gives an actionable error without sending credentials',async()=>{
 const x=setup({file:false});await assert.rejects(x.load(),/Selecione o arquivo/);assert.equal(x.calls.length,0);
});
test('failed backend load clears the password field',async()=>{
 const x=setup();x.context.__api=async()=>{throw Error('Senha incorreta');};vm.runInContext('api=__api',x.context);await assert.rejects(x.load(),/Senha incorreta/);assert.equal(x.password.value,'');
});
test('closing the form during file reading prevents upload',async()=>{
 const x=setup();let finish;x.context.__read=()=>new Promise(resolve=>{finish=resolve;});vm.runInContext('fileBase64=__read',x.context);const loading=x.load();x.form.isConnected=false;finish('SYNTHETIC-PFX');await assert.rejects(loading,/janela mudou/);assert.equal(x.calls.length,0);assert.equal(x.password.value,'');
});
test('switching company during file reading prevents cross-company upload',async()=>{
 const x=setup();let finish;x.context.__read=()=>new Promise(resolve=>{finish=resolve;});vm.runInContext('fileBase64=__read',x.context);const loading=x.load();vm.runInContext("S.cid='company-b'",x.context);finish('SYNTHETIC-PFX');await assert.rejects(loading,/empresa ou a janela mudou/);assert.equal(x.calls.length,0);
});
