"""Cópias de edição no banco local. Não reservam números nem transmitem XML."""
import copy,hashlib,json,re
from datetime import datetime,timezone
from vf_workflow import duplicate
KIND='editing_draft';MAX_SIZE=1024*1024

def revision(note):return hashlib.sha256(json.dumps(note,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def valid_id(value):
    if not re.fullmatch('[a-f0-9]{32}',str(value)):raise ValueError('Cópia de edição inválida.')
    return str(value)
def get(store,cid,rid,env):
    store.get('company','',cid);data=store.get(KIND,cid,valid_id(rid))
    if data.get('environment')!=env:raise ValueError('Cópia pertence a outro ambiente.')
    return data

def can_resume(store,cid,data):
    source=data.get('source_id','')
    if not source:return True
    row=store.db.execute("SELECT data FROM records WHERE kind='note' AND company=? AND id=?",(cid,source)).fetchone()
    if not row or json.loads(row[0]).get('_archived') or revision(json.loads(row[0]))!=data.get('base_revision'):return False
    fiscal=store.db.execute('SELECT status FROM fiscal_documents WHERE company=? AND source=?',(cid,source)).fetchone()
    return not fiscal or fiscal[0] in ('PREPARADA','REJEITADA')
def list_copies(store,cid,env):
    out=[]
    for rid,data in store.list(KIND,cid):
        if data.get('environment')!=env:continue
        n=data.get('note',{});out.append(dict(id=rid,version=data['version'],updated=data['updated'],number=n.get('number',''),source_id=data.get('source_id',''),items=len(n.get('items',[])),has_pending_item=bool(data.get('pending_item')),can_resume=can_resume(store,cid,data)))
    return out

def save(store,cid,p):
    co=store.get('company','',cid);rid=valid_id(p['id']);env=co.get('environment','2');n=p.get('note');pending=p.get('pending_item')
    if not isinstance(n,dict) or (pending is not None and not isinstance(pending,dict)):raise ValueError('Cópia de edição inválida.')
    if n.get('environment')!=env:raise ValueError('O ambiente foi alterado. Abra a recuperação no ambiente da nota.')
    n={k:copy.deepcopy(v) for k,v in n.items() if not k.startswith('_') and k not in ('password','password_hash','certificate','pfx','signed_xml','proc_xml')}
    if not isinstance(n.get('items',[]),list) or len(n.get('items',[]))>990:raise ValueError('Máximo de 990 itens por cópia.')
    payload=dict(note=n,pending_item=copy.deepcopy(pending),item_index=p.get('item_index',-1),tax_tab=str(p.get('tax_tab','icms'))[:40]);index=payload['item_index']
    if len(json.dumps(payload,ensure_ascii=False).encode())>MAX_SIZE:raise ValueError('Cópia automática excede 1 MB. Salve a NF-e pelo botão Apenas salvar.')
    if not isinstance(index,int) or not (index==-1 or 0<=index<len(n.get('items',[]))):raise ValueError('Item em edição inválido.')
    try:old=get(store,cid,rid,env)
    except ValueError:
        if store.db.execute('SELECT 1 FROM records WHERE id=?',(rid,)).fetchone():raise ValueError('Cópia não pertence a esta empresa/ambiente.')
        old=None
    expected=int(p.get('version',0));write_id=valid_id(p['write_id'])
    if old and old.get('write_id')==write_id:return dict(id=rid,version=old['version'],updated=old['updated'])
    if expected!=(old['version'] if old else 0):raise ValueError('Esta cópia mudou em outro acesso. Abra Recuperar rascunhos para conferir; nenhuma edição foi sobrescrita.')
    source=str(p.get('source_id') or '')
    if source:
        valid_id(source);source_note=store.get('note',cid,source)
        if source_note.get('environment','2')!=env:raise ValueError('A nota pertence a outro ambiente.')
    if old and source!=old.get('source_id',''):raise ValueError('Origem da cópia foi alterada. Salve e reabra a nota.')
    if not old and len(list_copies(store,cid,env))>=50:raise ValueError('Há 50 cópias de edição. Recupere ou descarte uma cópia antiga antes de continuar.')
    data=dict(payload,source_id=source,base_revision=str(p.get('base_revision','')),environment=env,version=expected+1,write_id=write_id,updated=datetime.now(timezone.utc).isoformat());store.save(KIND,data,cid,rid)
    return dict(id=rid,version=data['version'],updated=data['updated'])

def restore(store,cid,rid,as_new=False):
    co=store.get('company','',cid);data=copy.deepcopy(get(store,cid,rid,co.get('environment','2')))
    if not as_new and not can_resume(store,cid,data):raise ValueError('A nota original mudou ou foi finalizada. Recupere como nova NF-e e confira os dados.')
    n=data['note']
    if as_new:
        n=duplicate(store,cid,n);n['number']='';n.pop('cnf',None)
        if data.get('pending_item'):
            item=data['pending_item'];item.get('rule',{})['reviewed']='0'
            if item.get('taxes'):item['taxes']['reviewed']='0'
            if 'normal_manual_reviewed' in item:item['normal_manual_reviewed']='0'
        data.update(source_id='',base_revision='')
    n['_id']=data.get('source_id','')
    if data.get('pending_item'):
        for field in ('sync_to_catalog','save_new_to_catalog','save_rule'):data['pending_item'][field]='0'
    return dict(data,note=n,id=rid,as_new=bool(as_new))
def drop(store,cid,rid,version=None):
    co=store.get('company','',cid);data=get(store,cid,rid,co.get('environment','2'))
    if version is not None and int(version)!=data['version']:raise ValueError('A cópia mudou em outro acesso. Atualize a lista antes de descartar.')
    with store.db:store.db.execute('DELETE FROM records WHERE kind=? AND company=? AND id=?',(KIND,cid,rid))
    return dict(ok=True)
