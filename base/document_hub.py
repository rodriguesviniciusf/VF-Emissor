"""Central de documentos estritamente por empresa e ambiente."""
import hashlib,json,zipfile
from pathlib import Path
from fiscal import FiscalStore,render_danfe,parse_xml,text

def entries(store,cid,environment):
    result=[];sources=set();fiscal=FiscalStore(store)
    for doc in fiscal.list_metadata(cid):
        if doc['environment']!=environment:continue
        full=fiscal.get(cid,doc['id']);snapshot=json.loads(full['snapshot']);note=snapshot['note'];sources.add(full['source'])
        stamp=note.get('issued_at') or doc['created']
        result.append(dict(id=doc['id'],kind='fiscal',number=str(doc['number']),series=str(doc['series']),status=doc['status'],date=stamp[:10],recipient=snapshot.get('recipient',{}).get('xNome',''),key=doc['access_key'],environment=environment))
    for rid,n in store.list('note',cid):
        if n.get('environment','2')!=environment or rid in sources:continue
        rec={}
        try:rec=store.get('recipient',cid,n.get('recipient_id',''))
        except ValueError:pass
        result.append(dict(id=rid,kind='draft' if n.get('status')=='RASCUNHO' else 'imported',number=str(n.get('number','')),series=str(n.get('series','')),status=n.get('status','RASCUNHO'),date=(n.get('issued_at') or '')[:10],recipient=rec.get('xNome',''),key=n.get('key',''),environment=environment))
    from fiscal_events import EventStore
    for ev in EventStore(store).list(cid,environment):
        if ev['kind']=='INUT':result.append(dict(id=ev['id'],kind='inutil',number=str(ev['start_number'])+'–'+str(ev['end_number']),series=str(ev['series']),status=ev['status'],date=ev['created'][:10],recipient='Inutilização de numeração',key='',environment=environment))
    return result

def artifacts(store,cid,entry):
    rid=entry['id'];result={}
    if entry['kind']=='fiscal':
        d=FiscalStore(store).get(cid,rid)
        if d['environment']!=entry['environment']:raise ValueError('Documento pertence a outro ambiente.')
        key=d['access_key'];result[key+'-assinado.xml']=d['signed_xml']
        if d['proc_xml']:
            result[key+'-autorizado.xml']=d['proc_xml']
            from fiscal import serialize,NS
            prot=parse_xml(d['proc_xml']).find('n:protNFe',{'n':NS})
            if prot is not None:result[key+'-protocolo.xml']=serialize(prot)
        if d['response_xml']:result[key+'-retorno.xml']=d['response_xml']
        rows=store.db.execute('SELECT id,stamp,action,details,data FROM fiscal_history WHERE document=? ORDER BY id',(rid,)).fetchall()
        result['historico.json']=json.dumps([dict(id=r[0],stamp=r[1],action=r[2],details=r[3]) for r in rows],ensure_ascii=False,indent=2).encode('utf8')
        for id_,stamp,action,details,data in rows:
            if data:result['historico/'+str(id_)+'.xml']=data
        from fiscal_events import EventStore
        for ev in EventStore(store).list(cid,d['environment']):
            if ev['document']==rid:
                prefix='eventos/'+ev['id']+'/'
                result[prefix+'situacao.json']=json.dumps(dict(type=ev['kind'],status=ev['status'],reason=ev['reason']),ensure_ascii=False,indent=2).encode('utf8')
                for name,field in [('assinado.xml','signed_xml'),('retorno.xml','response_xml'),('processado.xml','proc_xml')]:
                    if ev[field]:result[prefix+name]=ev[field]
                for hid,action,data in store.db.execute('SELECT id,action,data FROM event_history WHERE event=? ORDER BY id',(ev['id'],)).fetchall():
                    if data:result[prefix+'historico/'+str(hid)+'.xml']=data
    elif entry['kind']=='inutil':
        from fiscal_events import EventStore
        ev=EventStore(store).get(cid,rid)
        if ev['environment']!=entry['environment']:raise ValueError('Ambiente divergente.')
        result['situacao.json']=json.dumps(dict(type=ev['kind'],status=ev['status'],reason=ev['reason']),ensure_ascii=False,indent=2).encode('utf8')
        for name,field in [('assinado.xml','signed_xml'),('retorno.xml','response_xml'),('processado.xml','proc_xml')]:
            if ev[field]:result[name]=ev[field]
    else:
        n=store.get('note',cid,rid)
        if n.get('environment','2')!=entry['environment']:raise ValueError('Ambiente divergente.')
        if entry['kind']=='draft':result['rascunho.json']=json.dumps(n,ensure_ascii=False,indent=2).encode('utf8')
        else:
            # Não abre um caminho arbitrário gravado em um XML/cadastro antigo.
            key=n.get('key','')
            if len(key)==44 and key.isdigit():
                p=store.path.parent/'xml'/cid/(key+'.xml')
                if p.is_file() and not p.is_symlink():result[key+'-importado.xml']=p.read_bytes()
    return result

def export_documents(store,cid,entry,target,include_pdf=True):
    files=artifacts(store,cid,entry)
    if include_pdf and entry['kind']=='fiscal':
        d=FiscalStore(store).get(cid,entry['id'])
        if d['status']=='AUTORIZADA' and d['proc_xml']:files[d['access_key']+'-DANFE.pdf']=render_danfe(d['proc_xml'])
    meta=dict(company=cid,environment=entry['environment'],status=entry['status'],kind=entry['kind'],files={n:hashlib.sha256(v).hexdigest() for n,v in files.items()})
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
        z.writestr('manifest.json',json.dumps(meta,ensure_ascii=False,indent=2))
    return len(files)
