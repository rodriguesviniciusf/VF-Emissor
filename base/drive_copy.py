"""Cópia adicional de XML. Nunca move nem apaga o arquivo fiscal local."""
import hashlib,json,os
from datetime import datetime
from pathlib import Path
from core import document
from fiscal import FiscalStore
from fiscal_events import EventStore
from business_config import load
from invoice_archive import atomic_write

def copy_xml(store,cid):
    cfg=load(store,cid)
    if cfg['drive_enabled']!='1':return dict(enabled=False,copied=0,pending=0,message='Cópia para Google Drive desativada nesta empresa.')
    cnpj=document(store.get('company','',cid)['CNPJCPF']);root=Path(cfg['drive_directory'])
    if not root.is_absolute() or not root.is_dir():
        result=dict(enabled=True,copied=0,pending=1,message='Pasta sincronizada indisponível. Os XML locais estão preservados; a cópia será tentada novamente.')
        store.save('drive_status',result,cid,'drive-status-'+cid);return result
    files=[];fiscal=FiscalStore(store)
    for d in fiscal.list(cid):
        if d['status'] in ('AUTORIZADA','CANCELADA') and d['proc_xml']:
            env='producao' if d['environment']=='1' else 'homologacao';key=d['access_key'];month='20'+key[2:4]+'-'+key[4:6]
            files.append((Path(cnpj)/env/month/'emitidas'/(key+'-procNFe.xml'),d['proc_xml']))
    for env in ('1','2'):
        for e in EventStore(store).list(cid,env):
            if e.get('proc_xml') and e['status']=='REGISTRADO':
                folder=Path(cnpj)/('producao' if env=='1' else 'homologacao')/e['created'][:7]/'eventos'
                files.append((folder/(e['id']+'-procEvento.xml'),e['proc_xml']))
    if cfg['drive_entries']=='1':
        for rid,d in store.list('received',cid):
            path=store.path.parent/'xml-importados'/cid/(rid+'.xml')
            if d.get('direction')=='recebida' and path.is_file() and not path.is_symlink():files.append((Path(cnpj)/('producao' if d['environment']=='1' else 'homologacao')/d['issued_at'][:7]/'entradas'/(d['key']+'-procNFe.xml'),path.read_bytes()))
    copied=0;pending=0
    for relative,data in files:
        try:
            target=root/relative
            if target.is_file() and target.read_bytes()==data:copied+=1;continue
            if target.exists():target=target.with_name(target.stem+'-'+hashlib.sha256(data).hexdigest()[:12]+target.suffix)
            atomic_write(target,data,immutable=True);copied+=1
        except OSError:pending+=1
        except ValueError:pending+=1
    result=dict(enabled=True,copied=copied,pending=pending,checked_at=datetime.now().astimezone().isoformat(),message='Copiado para a pasta sincronizada. A conclusão do envio à nuvem é informada pelo Google Drive.' if not pending else 'Há cópias pendentes. Os XML continuam guardados no PC de emissão.')
    store.save('drive_status',result,cid,'drive-status-'+cid);return result
