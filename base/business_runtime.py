"""Integra as rotinas operacionais ao serviço local existente."""
import base64,hashlib,json,re,secrets,threading,time,uuid,functools,sqlite3,zipfile
from datetime import datetime
from pathlib import Path
from core import Store,document
from fiscal import FiscalStore,parse_xml,text,NS,validate_schema
from fiscal_events import EventStore,schema_event
from invoice_archive import atomic_write
import business_config,catalog_wizard,company_recovery,stock_control,drive_copy,rejection_center

PLANS={}
LOCK=threading.RLock()
MAINTENANCE_WAKE=threading.Event()
def locked(fn):
    @functools.wraps(fn)
    def wrapper(*args,**kwargs):
        with LOCK:return fn(*args,**kwargs)
    return wrapper
def remember(cid,kind,data):
    for key,v in list(PLANS.items()):
        if v['expires']<time.time():PLANS.pop(key,None)
    if len(PLANS)>=32:raise ValueError('Feche as prévias antigas e aguarde antes de abrir outra importação.')
    token=secrets.token_hex(24);PLANS[token]=dict(cid=cid,kind=kind,data=data,expires=time.time()+1800);return token
def recalled(cid,token,kind):
    plan=PLANS.get(str(token))
    if not plan or plan['cid']!=cid or plan['kind']!=kind or plan['expires']<time.time():raise ValueError('A prévia expirou ou pertence a outra empresa. Selecione o arquivo novamente.')
    return plan

def read_entry(raw,co):
    root=parse_xml(raw)
    if root.tag=='{'+NS+'}procEventoNFe':
        schema_event('110111',4,raw)
        inf=root.find('n:evento/n:infEvento',{'n':NS});ret=root.find('n:retEvento/n:infEvento',{'n':NS})
        if inf is None or ret is None or text(inf,'n:tpEvento')!='110111' or text(ret,'n:tpEvento')!='110111' or text(ret,'n:cStat') not in ('135','155') or text(inf,'n:chNFe')!=text(ret,'n:chNFe') or text(inf,'n:tpAmb')!=text(ret,'n:tpAmb'):raise ValueError('Importe o evento processado de cancelamento, com retorno de registro.')
        return dict(kind='cancel',key=text(inf,'n:chNFe'),environment=text(inf,'n:tpAmb'),cancelled_at=text(ret,'n:dhRegEvento') or text(inf,'n:dhEvento'))
    if root.tag!='{'+NS+'}nfeProc':raise ValueError('Importe NF-e processada, com protocolo de autorização, ou evento processado de cancelamento.')
    validate_schema(raw,'procNFe_v4.00.xsd');inf=root.find('n:NFe/n:infNFe',{'n':NS});prot=root.find('n:protNFe/n:infProt',{'n':NS})
    if inf is None or prot is None or text(prot,'n:cStat') not in ('100','150'):raise ValueError('XML sem protocolo de autorização.')
    key=inf.get('Id','')[3:];env=text(inf,'n:ide/n:tpAmb')
    if not re.fullmatch(r'\d{44}',key) or text(prot,'n:chNFe')!=key or text(prot,'n:tpAmb')!=env:raise ValueError('Protocolo divergente da NF-e.')
    emitter=text(inf,'n:emit/n:CNPJ');dest=text(inf,'n:dest/n:CNPJ') or text(inf,'n:dest/n:CPF')
    if document(co['CNPJCPF']) not in (emitter,dest):raise ValueError('A NF-e não pertence à empresa acessada.')
    return dict(kind='invoice',key=key,number=text(inf,'n:ide/n:nNF'),environment=env,issuer=text(inf,'n:emit/n:xNome'),recipient=text(inf,'n:dest/n:xNome'),direction='emitida' if emitter==document(co['CNPJCPF']) else 'recebida',stock_sign=-1 if text(inf,'n:ide/n:tpNF')=='0' else 1,items=stock_control.xml_items(raw))

def after_change(store,cid):
    # A resposta fiscal retorna imediatamente; a cópia externa não é aguardada.
    MAINTENANCE_WAKE.set()

def sync_services(store,cid,include_drive=True):
    services=[('estoque',stock_control.reconcile)]
    if include_drive:services.append(('drive',drive_copy.copy_xml))
    for name,fn in services:
        try:
            fn(store,cid)
            with store.db:store.db.execute("DELETE FROM records WHERE kind='service_status' AND company=? AND id=?",(cid,'service-'+name+'-'+cid))
        except Exception:
            # Nunca transforma uma autorização bem-sucedida em erro de transmissão.
            store.save('service_status',dict(service=name,error='Rotina pendente. Verifique as configurações; os documentos fiscais locais foram preservados.'),cid,'service-'+name+'-'+cid)

@locked
def state(store,cid,env):
    config=business_config.load(store,cid)
    try:drive=store.get('drive_status',cid,'drive-status-'+cid)
    except ValueError:drive={}
    try:backup=store.get('backup_status',cid,'backup-status-'+cid)
    except ValueError:backup={}
    return dict(features=config,suppliers=[dict(d,_id=rid) for rid,d in store.list('supplier',cid) if not d.get('_archived')],stock=stock_control.state(store,cid,env),rejections=rejection_center.entries(store,cid,env),backup_status=backup,drive_status=drive,service_errors=[r for _,r in store.list('service_status',cid)])

def _action(store,p,preview,base_import):
    cmd=p['action'];cid=p.get('cid','')
    if cmd=='save_features':
        result=business_config.save(store,cid,p['data']);after_change(store,cid);return dict(features=result)
    if cmd=='entry_delete':
        result=stock_control.remove_import(store,cid,p['id'],p.get('ack'))
        after_change(store,cid);return result
    if cmd=='import_catalog_preview':
        raw=base64.b64decode(p['data'],validate=True);kind=p['kind'];rows=catalog_wizard.preview(store,cid,kind,raw,p['filename'],p.get('party',''))
        token=remember(cid,'catalog',dict(kind=kind,rows=rows));return dict(token=token,rows=rows)
    if cmd=='import_catalog_apply':
        plan=recalled(cid,p['token'],'catalog')
        if 'result' not in plan:plan['result']=catalog_wizard.apply(store,cid,plan['data']['kind'],plan['data']['rows'],p.get('allow_partial') is True)
        return plan['result']
    if cmd=='entry_preview':
        raw=base64.b64decode(p['data'],validate=True)
        if len(raw)>8*1024*1024:raise ValueError('XML acima de 8 MB.')
        co=store.get('company','',cid);meta=read_entry(raw,co)
        if meta['kind']=='cancel' and not any(not d.get('_archived') and d.get('key')==meta['key'] and d.get('environment')==meta['environment'] for _,d in store.list('received',cid)):raise ValueError('Importe primeiro a NF-e relacionada a este cancelamento.')
        if meta['kind']=='invoice':
            old=next(((rid,r) for rid,r in store.list('received',cid) if not r.get('_archived') and r.get('key')==meta['key']),None)
            meta['repair']=bool(old and not (store.path.parent/'xml-importados'/cid/(old[0]+'.xml')).exists())
        return dict(token=remember(cid,'entry',dict(raw=raw,meta=meta)),**meta)
    if cmd=='entry_apply':
        plan=recalled(cid,p['token'],'entry')
        if 'result' in plan:return plan['result']
        raw=plan['data']['raw'];meta=plan['data']['meta'];co=store.get('company','',cid)
        read_entry(raw,co)
        if meta['kind']=='cancel':
            existing=next(((rid,r) for rid,r in store.list('received',cid) if not r.get('_archived') and r.get('key')==meta['key'] and r.get('environment')==meta['environment']),None)
            if not existing:raise ValueError('A importação relacionada foi excluída. Confira novamente o XML.')
            rid,rec=existing
            file=rid+'-cancel-'+hashlib.sha256(raw).hexdigest()[:16]+'.xml';atomic_write(store.path.parent/'xml-importados'/cid/file,raw,True)
            rec.update(cancelled=True,cancelled_at=meta['cancelled_at'],cancellation_files=list(dict.fromkeys(rec.get('cancellation_files',[])+[file])));store.save('received',rec,cid,rid)
            result=dict(id=rid,message='Cancelamento declarado no arquivo importado. O estoque será estornado quando houver movimento vinculado.')
        else:
            move=p.get('move_stock') is True and meta['direction']=='recebida'
            if move and business_config.load(store,cid)['stock_enabled']!='1':raise ValueError('Ative o estoque nesta empresa antes de movimentar a entrada.')
            mappings=p.get('mappings',[])
            if not isinstance(mappings,list) or len(mappings)>990:raise ValueError('Vínculos de estoque inválidos.')
            allowed={i['line'] for i in meta['items']}
            for m in mappings:
                if int(m['line']) not in allowed:raise ValueError('Item não pertence ao XML.')
                store.get('product',cid,m['product_id'])
                if stock_control.clean_qty(m.get('factor','1'))<=0:raise ValueError('Fator de conversão deve ser positivo.')
            result=base_import(dict(cid=cid,data=base64.b64encode(raw).decode()))
            rid=result['id']
            if not result.get('repaired'):
                rec=store.get('received',cid,rid);rec.update(items=meta['items'],stock_enabled=move,stock_sign=meta['stock_sign']);store.save('received',rec,cid,rid)
            for m in mappings:
                if move and not result.get('repaired'):stock_control.set_mapping(store,cid,'ENTRADA',rid,int(m['line']),m['product_id'],m.get('factor','1'))
        after_change(store,cid);plan['result']=result;return result
    if cmd=='stock_adjust':return dict(id=stock_control.manual(store,cid,store.get('company','',cid).get('environment','2'),p['product_id'],p['quantity'],p['reason']))
    if cmd=='stock_map':
        stock_control.set_mapping(store,cid,p['source'],p['id'],p['line'],p['product_id'],p.get('factor','1'));stock_control.reconcile(store,cid);return dict(ok=True)
    if cmd=='backup_now':return company_recovery.create(store,cid)
    if cmd=='backup_list':return dict(backups=company_recovery.list_backups(store,cid))
    if cmd=='restore_saved_preview':
        name=str(p['name'])
        if not re.fullmatch(r'[a-zA-Z0-9-]+\.zip',name):raise ValueError('Backup inválido.')
        file=company_recovery.backup_root(store,cid)/name
        if not file.is_file() or file.is_symlink():raise ValueError('Backup indisponível.')
        token=company_recovery.upload_start(store,cid,file.stat().st_size)
        folder,_=company_recovery.upload_folder(store,cid,token)
        import shutil
        shutil.copyfile(file,folder/'upload.zip')
        return company_recovery.inspect(store,cid,token)
    if cmd=='restore_upload_start':return dict(token=company_recovery.upload_start(store,cid,p['size']))
    if cmd=='restore_upload_chunk':return dict(offset=company_recovery.upload_chunk(store,cid,p['token'],p['offset'],base64.b64decode(p['data'],validate=True)))
    if cmd=='restore_preview':return company_recovery.inspect(store,cid,p['token'])
    if cmd=='restore_apply':
        if preview:raise ValueError('Restaure pelo aplicativo local instalado no Windows.')
        return company_recovery.restore(store,cid,p['token'],p['ack'])
    if cmd=='drive_sync':return drive_copy.copy_xml(store,cid)
    if cmd=='correction_draft':
        fs=FiscalStore(store);d=fs.get(cid,p['id'])
        if d['status']!='REJEITADA':raise ValueError('Consulte a SEFAZ; somente uma rejeição confirmada pode ser corrigida.')
        return dict(id=d['source'],note=fs.draft_for_correction(cid,p['id']))
    if cmd=='clone_latest':
        env=store.get('company','',cid).get('environment','2');notes=[(rid,n) for rid,n in store.list('note',cid) if not n.get('_archived') and n.get('environment','2')==env]
        if not notes:raise ValueError('Nenhuma NF-e salva neste ambiente para clonar.')
        rid,n=max(notes,key=lambda r:(r[1].get('issued_at',''),int(r[1].get('number') or 0)))
        from vf_workflow import duplicate
        return dict(note=duplicate(store,cid,n),source_number=n.get('number',''))
    return None

@locked
def action(store,p,preview,base_import):
    from lxml.etree import XMLSyntaxError
    try:return _action(store,p,preview,base_import)
    except (zipfile.BadZipFile,sqlite3.DatabaseError,XMLSyntaxError) as exc:raise ValueError('O arquivo não pôde ser lido ou está danificado. Confira o formato e selecione novamente.') from exc

COMMANDS={'entry_delete','save_features','import_catalog_preview','import_catalog_apply','entry_preview','entry_apply','stock_adjust','stock_map','backup_now','backup_list','restore_saved_preview','restore_upload_start','restore_upload_chunk','restore_preview','restore_apply','drive_sync','correction_draft','clone_latest'}

def start_maintenance(data_dir,stop):
    def run():
        while not stop.is_set():
            MAINTENANCE_WAKE.clear()
            store=None
            try:
                store=Store(Path(data_dir)/'vf.sqlite3');FiscalStore(store);EventStore(store)
                import ncm_catalog
                ncm_catalog.refresh(data_dir)
                for cid,co in store.list('company'):
                    if stop.is_set():break
                    try:
                        with LOCK:company_recovery.automatic(store,cid)
                    except Exception:
                        try:store.save('service_status',dict(service='backup',error='Backup automático pendente. Confira a pasta configurada.'),cid,'service-backup-'+cid)
                        except Exception:pass
                    with LOCK:sync_services(store,cid,include_drive=False)
                    # Drive fora do lock: um destino indisponível não trava a emissão.
                    try:drive_copy.copy_xml(store,cid)
                    except Exception:pass
            except Exception:pass
            finally:
                if store:store.db.close()
            if not stop.is_set():MAINTENANCE_WAKE.wait(60)
    thread=threading.Thread(target=run,name='VF-Manutencao',daemon=True);thread.start();return thread
