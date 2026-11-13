'use strict';
/* Motion inspired by Transitions.dev. Presentation only: no business requests,
   delays to actions, data persistence, counters or changes to fiscal values. */
(()=>{
 const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
 const ease='cubic-bezier(.22,1,.36,1)',tabPositions=new Map(),running=new Set();
 let previousView='',previousScreen='',resizeFrame=0;
 function play(element,frames,options={}){
  if(reduced.matches||!element?.animate)return;
  const animation=element.animate(frames,{duration:250,easing:ease,...options});
  running.add(animation);
  const done=()=>running.delete(animation);animation.onfinish=done;animation.oncancel=done;
  return animation;
 }
 function viewKey(){
  if(S.authenticated===false)return S.access?.account?'companies:'+S.access.account.id:'access:'+String(typeof accessView==='undefined'?'login':accessView);
  return [S.cid,page,typeof configTab==='undefined'?'':page==='configuracoes'?configTab:'',typeof tab==='undefined'?'':page==='inicio'?tab:''].join(':');
 }
 // Transitions.dev — Tabs sliding, adapted for the existing synchronous renderer.
 // One decorative pill follows the selected button. The buttons remain native.
 function syncTabs(animate=true){
  document.querySelectorAll('#content .tabs').forEach((bar,index)=>{
   const buttons=[...bar.children].filter(el=>el.tagName==='BUTTON');
   const active=buttons.find(b=>b.classList.contains('active')||b.getAttribute('aria-selected')==='true');
   if(!active||!active.offsetWidth)return;
   bar.classList.add('motion-tabs');
   const key=page+':'+index+':'+buttons.map(b=>b.dataset.action+':'+b.textContent.trim()).join('|');
   const next={x:active.offsetLeft,y:active.offsetTop,w:active.offsetWidth,h:active.offsetHeight};
   const old=tabPositions.get(key);tabPositions.set(key,next);
   let pill=bar.querySelector('.motion-tab-indicator');
   if(!pill){pill=document.createElement('span');pill.className='motion-tab-indicator';pill.setAttribute('aria-hidden','true');bar.prepend(pill);}
   pill.style.width=next.w+'px';pill.style.height=next.h+'px';pill.style.transform=`translate(${next.x}px,${next.y}px)`;
   if(animate&&old&&(old.x!==next.x||old.y!==next.y||old.w!==next.w))play(pill,[{transform:`translate(${old.x}px,${old.y}px) scale(${old.w/next.w},${old.h/next.h})`},{transform:`translate(${next.x}px,${next.y}px) scale(1)`}]);
  });
 }
 const before=render;
 render=function(){
  before();
  const key=viewKey(),changed=key!==previousView;previousView=key;
  if(changed)for(const animation of running)animation.cancel();
  const screen=S.authenticated===false?'access':S.cid+':'+page;
  syncTabs(screen===previousScreen);previousScreen=screen;
  if(!changed)return;
  const content=document.querySelector('#content');
  play(content,[{opacity:.45,transform:'translateY(7px)'},{opacity:1,transform:'translateY(0)'}],{duration:250});
  const cards=[...document.querySelectorAll('.access-company,.workspace-metric,.access-story-copy,.access-visual,.access-card .field')].slice(0,8);
  cards.forEach((card,index)=>play(card,[{opacity:0,transform:'translateY(9px)'},{opacity:1,transform:'translateY(0)'}],{duration:340,delay:Math.min(index*35,140),fill:'backwards'}));
 };
 window.addEventListener('resize',()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>syncTabs(false));});
 reduced.addEventListener('change',()=>{if(reduced.matches)for(const animation of running)animation.cancel();});
 if(S.version)render();
})();
