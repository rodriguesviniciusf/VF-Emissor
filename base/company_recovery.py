"""Backup automático e restauração transacional da empresa ativa, com cópia anterior."""
import hashlib,json,os,re,shutil,sqlite3,tempfile,time,uuid,zipfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from core import document
from certificate_vault import CertificateVault
from company_backup import backup_company
from business_config import load

MAX_UPLOAD=250*1024*1024
def utc():return datetime.now(timezone.utc)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def backup_root(store,cid):
    config=load(store,cid);co=store.get('company','',cid)
    base=Path(config['backup_directory']) if config['backup_directory'] else store.path.parent/'backups-empresas'
    if config['backup_directory'] and not base.is_dir():raise ValueError('A pasta de backup configurada está indisponível.')
    return base/document(co['CNPJCPF'])

def create(store,cid,automatic=False):
    co=store.get('company','',cid);folder=backup_root(store,cid);folder.mkdir(parents=True,exist_ok=True)
    stamp=utc();prefix='automatico' if automatic else 'manual'
    name=f"{prefix}-{document(co['CNPJCPF'])}-{stamp.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.zip"
    raw=backup_company(store,cid,document(co['CNPJCPF']),CertificateVault(store.path.parent/'certificados-protegidos').path(cid))
    target=folder/name;temp=folder/(name+'.tmp')
    try:
        with temp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
    status=dict(last_backup=stamp.isoformat(),name=name,path=str(target),automatic=automatic,size=len(raw))
    store.save('backup_status',status,cid,'backup-status-'+cid)
    with store.db:store.db.execute("DELETE FROM records WHERE kind='service_status' AND company=? AND id=?",(cid,'service-backup-'+cid))
    if automatic:
        files=sorted(folder.glob('automatico-'+document(co['CNPJCPF'])+'-*.zip'),key=lambda p:p.name,reverse=True)
        for file in files[int(load(store,cid)['backup_keep']):]:
            if not file.is_symlink():file.unlink()
    return status

def automatic(store,cid):
    cfg=load(store,cid)
    if cfg['backup_enabled']!='1':return None
    try:status=store.get('backup_status',cid,'backup-status-'+cid)
    except ValueError:status={}
    last=status.get('last_backup')
    if last and (utc()-datetime.fromisoformat(last)).total_seconds()<int(cfg['backup_hours'])*3600:return None
    return create(store,cid,True)

def list_backups(store,cid):
    try:folder=backup_root(store,cid)
    except ValueError:return []
    return [dict(name=p.name,size=p.stat().st_size,modified=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()) for p in sorted(folder.glob('*.zip'),reverse=True)[:365] if p.is_file() and not p.is_symlink()]

def upload_start(store,cid,size):
    store.get('company','',cid);size=int(size)
    if not 0<size<=MAX_UPLOAD:raise ValueError('O backup deve ter até 250 MB.')
    token=uuid.uuid4().hex;folder=store.path.parent/'operacoes-temporarias'/token;folder.mkdir(parents=True)
    (folder/'owner.json').write_text(json.dumps(dict(cid=cid,size=size,created=time.time())))
    (folder/'upload.zip').touch();return token

def upload_folder(store,cid,token):
    if not re.fullmatch('[a-f0-9]{32}',str(token)):raise ValueError('Operação temporária inválida.')
    folder=store.path.parent/'operacoes-temporarias'/token
    try:owner=json.loads((folder/'owner.json').read_text())
    except (OSError,ValueError):raise ValueError('Selecione o backup novamente.')
    if owner.get('cid')!=cid or time.time()-owner.get('created',0)>86400:raise ValueError('Operação temporária expirada ou de outra empresa.')
    return folder,owner

def upload_chunk(store,cid,token,offset,data):
    folder,owner=upload_folder(store,cid,token);path=folder/'upload.zip'
    if len(data)>1024*1024 or int(offset)!=path.stat().st_size or path.stat().st_size+len(data)>owner['size']:raise ValueError('Parte do backup inválida. Selecione o arquivo novamente.')
    with path.open('ab') as f:f.write(data)
    return path.stat().st_size

def inspect(store,cid,token):
    folder,owner=upload_folder(store,cid,token);archive=folder/'upload.zip'
    if archive.stat().st_size!=owner['size']:raise ValueError('Envio do backup incompleto.')
    stage=folder/'conteudo'
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir();seen=set()
    try:
        with zipfile.ZipFile(archive) as z:
            if len(z.infolist())>50000 or sum(i.file_size for i in z.infolist())>1024*1024*1024:raise ValueError('Backup excede o limite descompactado.')
            for item in z.infolist():
                n=item.filename.rstrip('/');parts=PurePosixPath(n).parts
                if not parts or '\\' in n or ':' in n or n.startswith('/') or any(x in ('.','..') or x.rstrip(' .')!=x or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?',x) for x in n.split('/')):raise ValueError('Caminho inválido no backup.')
                if n.casefold() in seen or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Entrada duplicada ou link no backup.')
                seen.add(n.casefold())
                if parts[0] not in ('dados','backup-manifest.json'):raise ValueError('Este arquivo não é um backup de empresa do VF Emissor.')
                if item.is_dir():continue
                out=stage.joinpath(*parts);out.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as src,out.open('wb') as dst:shutil.copyfileobj(src,dst)
        dbfile=stage/'dados/vf.sqlite3';db=sqlite3.connect(dbfile.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco do backup corrompido.')
            if db.execute('PRAGMA user_version').fetchone()[0]>4:raise ValueError('Backup exige uma versão mais nova do programa.')
            companies=db.execute("SELECT id,data FROM records WHERE kind='company'").fetchall()
            if len(companies)!=1:raise ValueError('O backup deve conter somente uma empresa.')
            source,raw=companies[0];co=json.loads(raw);cnpj=document(co.get('CNPJCPF',''))
            if not re.fullmatch('[a-f0-9]{32}',source):raise ValueError('Identificação da empresa inválida no backup.')
            if cnpj!=document(store.get('company','',cid)['CNPJCPF']):raise ValueError('O CNPJ do backup é diferente da empresa acessada.')
            if db.execute("SELECT count(*) FROM records WHERE NOT ((kind='company' AND id=?) OR company=?)",(source,source)).fetchone()[0]:raise ValueError('O backup contém dados de outra empresa.')
            for table in ('fiscal_documents','fiscal_events'):
                if db.execute('SELECT count(*) FROM '+table+' WHERE company<>?',(source,)).fetchone()[0]:raise ValueError('Documentos de outra empresa no backup.')
            if db.execute('SELECT count(*) FROM fiscal_history WHERE document NOT IN (SELECT id FROM fiscal_documents)').fetchone()[0] or db.execute('SELECT count(*) FROM event_history WHERE event NOT IN (SELECT id FROM fiscal_events)').fetchone()[0]:raise ValueError('Histórico fora do escopo da empresa.')
            if db.execute('SELECT count(*) FROM fiscal_documents WHERE cnpj<>?',(cnpj,)).fetchone()[0]:raise ValueError('CNPJ fiscal divergente no backup.')
            counts=dict(db.execute("SELECT kind,count(*) FROM records GROUP BY kind").fetchall())
            counts['fiscal_documents']=db.execute('SELECT count(*) FROM fiscal_documents').fetchone()[0]
            # Todos os JSON são validados antes de iniciar a substituição.
            for rid,kind,raw in db.execute('SELECT id,kind,data FROM records'):
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,180}',str(rid)):raise ValueError('Identificador inválido no backup.')
                data=json.loads(raw)
                if not isinstance(data,dict):raise ValueError('Cadastro inválido no backup.')
                if kind=='received':
                    if not re.fullmatch(r'[a-f0-9]{32}',rid) or not re.fullmatch(r'\d{44}',data.get('key','')) or data.get('environment') not in ('1','2'):raise ValueError('Identificação do XML importado inválida.')
                    datetime.fromisoformat(data['issued_at'])
            for table in ('fiscal_documents','fiscal_events'):
                for did,env,created,updated in db.execute('SELECT id,environment,created,updated FROM '+table):
                    if not re.fullmatch(r'[a-f0-9]{32}',did) or env not in ('1','2'):raise ValueError('Identificação fiscal inválida no backup.')
                    datetime.fromisoformat(created);datetime.fromisoformat(updated)
        finally:db.close()
        vault=CertificateVault(store.path.parent/'certificados-protegidos')
        source_vault=hashlib.sha256(source.encode()).hexdigest()+'.dpapi'
        allowed=[('dados','vf.sqlite3'),('backup-manifest.json',)]
        hashes={}
        for p in stage.rglob('*'):
            if not p.is_file():continue
            parts=p.relative_to(stage).parts
            valid=parts in allowed or len(parts)>=4 and parts[:3] in [('dados','notas-fiscais',cnpj),('dados','xml-importados',source)] or parts==('dados','certificados-protegidos',source_vault)
            if not valid:raise ValueError('Arquivo fora da empresa no backup.')
            hashes[p.relative_to(stage).as_posix()]=digest(p)
        mf=stage/'backup-manifest.json';meta=json.loads(mf.read_text()) if mf.exists() else {}
        if meta and (meta.get('format')!=2 or meta.get('cnpj')!=cnpj or meta.get('company')!=source or meta.get('files')!={k:v for k,v in hashes.items() if k!='backup-manifest.json'}):raise ValueError('Integridade do backup inválida.')
        plan=dict(token=token,source=source,cnpj=cnpj,counts=counts,files=hashes,created=meta.get('created',''),legacy=not bool(meta),certificate_restorable=source==cid and (stage/'dados/certificados-protegidos'/source_vault).exists())
        (folder/'plan.json').write_text(json.dumps(plan));return plan
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise

def restore(store,cid,token,ack):
    folder,_=upload_folder(store,cid,token);plan=json.loads((folder/'plan.json').read_text());stage=folder/'conteudo'
    if ack!='RESTAURAR '+plan['cnpj']:raise ValueError('Digite RESTAURAR seguido do CNPJ para confirmar.')
    if not (folder/'plan.json').is_file():raise ValueError('Gere outra prévia da restauração.')
    if {p.relative_to(stage).as_posix():digest(p) for p in stage.rglob('*') if p.is_file()}!=plan['files']:raise ValueError('O backup preparado foi alterado. Selecione novamente.')
    # Revalida escopo e integridade antes de modificar arquivos ou banco.
    fresh=inspect(store,cid,token);stage=folder/'conteudo';source=fresh['source'];co=store.get('company','',cid)
    previous=create(store,cid);src=sqlite3.connect((stage/'dados/vf.sqlite3').resolve().as_uri()+'?mode=ro&immutable=1',uri=True);src.row_factory=sqlite3.Row
    stash=folder/'anterior';stash.mkdir(exist_ok=True);swaps=[]
    vault=CertificateVault(store.path.parent/'certificados-protegidos')
    targets=[(stage/'dados/notas-fiscais'/fresh['cnpj'],store.path.parent/'notas-fiscais'/fresh['cnpj']),(stage/'dados/xml-importados'/source,store.path.parent/'xml-importados'/cid)]
    if source==cid:targets.append((stage/'dados/certificados-protegidos'/vault.path(cid).name,vault.path(cid)))
    try:
        with store.db:
            store.db.execute('UPDATE records SET updated=updated WHERE 0')
            records=[]
            from stock_control import identity,mapping_id
            for row in src.execute('SELECT * FROM records'):
                d=json.loads(row['data']);rid=row['id'];kind=row['kind']
                if kind=='settings' and rid=='preferences' and src.execute("SELECT 1 FROM records WHERE kind='settings' AND company=? AND id=?",(source,'preferences-'+source)).fetchone():continue
                if kind=='company':
                    rid=cid;d['CNPJCPF']=co['CNPJCPF'];d['environment']='2';d['production_enabled']=False
                    if co.get('password_hash'):d['password_hash']=co['password_hash']
                    else:d.pop('password_hash',None)
                elif kind in ('settings','business_settings','drive_status','backup_status','simple_config'):
                    rid={'settings':'preferences-','business_settings':'business-','drive_status':'drive-status-','backup_status':'backup-status-','simple_config':'simple-'}[kind]+cid
                elif kind=='stock_move':rid='stock-'+identity(cid,d['environment'],d['source'],d['source_id'],d['line'],'reverse' if d.get('reverse') else 'original')
                elif kind=='stock_mapping' and source!=cid:
                    if not all(k in d for k in ('source','source_id','line')):continue
                    rid=mapping_id(cid,d['source'],d['source_id'],d['line'])
                owner=store.db.execute('SELECT kind,company FROM records WHERE id=?',(rid,)).fetchone()
                if owner and not ((owner[0]=='company' and rid==cid) or owner[1]==cid):raise ValueError('Um identificador do backup conflita com outra empresa.')
                records.append((rid,kind,'' if kind=='company' else cid,json.dumps(d,ensure_ascii=False),row['updated']))
            for table in ('fiscal_documents','fiscal_events'):
                for row in src.execute('SELECT id FROM '+table):
                    owner=store.db.execute('SELECT company FROM '+table+' WHERE id=?',(row[0],)).fetchone()
                    if owner and owner[0]!=cid:raise ValueError('Documento do backup conflita com outra empresa.')
            # Substitui somente pastas pertencentes à empresa ativa, guardando rollback.
            for index,(origin,target) in enumerate(targets):
                target.parent.mkdir(parents=True,exist_ok=True);old=stash/str(index)
                existed=target.exists()
                if existed:os.replace(target,old)
                swaps.append((target,old,existed))
                if origin.exists():
                    if origin.is_dir():shutil.copytree(origin,target)
                    else:shutil.copy2(origin,target)
            store.db.execute('DELETE FROM fiscal_history WHERE document IN (SELECT id FROM fiscal_documents WHERE company=?)',(cid,))
            store.db.execute('DELETE FROM event_history WHERE event IN (SELECT id FROM fiscal_events WHERE company=?)',(cid,))
            store.db.execute('DELETE FROM fiscal_events WHERE company=?',(cid,));store.db.execute('DELETE FROM fiscal_documents WHERE company=?',(cid,))
            store.db.execute("DELETE FROM records WHERE company=? OR (kind='company' AND id=?)",(cid,cid))
            store.db.executemany('INSERT INTO records VALUES(?,?,?,?,?)',records)
            for table in ('fiscal_documents','fiscal_events','fiscal_history','event_history'):
                cols=[r[1] for r in store.db.execute('PRAGMA table_info('+table+')')]
                if table.endswith('_history'):cols.remove('id')
                query='INSERT INTO '+table+'('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')'
                for row in src.execute('SELECT * FROM '+table):
                    values=[]
                    for col in cols:
                        value=cid if col=='company' else row[col]
                        if col=='snapshot' and value:
                            snap=json.loads(value)
                            if isinstance(snap.get('company'),dict):snap['company']['_id']=cid
                            value=json.dumps(snap,ensure_ascii=False)
                        values.append(value)
                    store.db.execute(query,values)
            store.db.execute('INSERT INTO audit(stamp,action,record) VALUES(?,?,?)',(utc().isoformat(),'RESTAURAR EMPRESA',cid))
    except Exception:
        for target,old,existed in reversed(swaps):
            if target.is_dir():shutil.rmtree(target)
            else:target.unlink(missing_ok=True)
            if existed:os.replace(old,target)
        raise
    finally:src.close()
    (folder/'plan.json').unlink(missing_ok=True)
    return dict(ok=True,backup_before=previous['name'],message='Empresa restaurada. Confira série e numeração antes de habilitar produção. Recarregue o A1 se estiver em outra conta do Windows.')
