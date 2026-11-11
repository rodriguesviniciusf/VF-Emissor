"""Configurações operacionais estritamente por empresa."""
import copy
from datetime import datetime,timezone
from pathlib import Path

DEFAULTS=dict(stock_enabled='0',backup_enabled='1',backup_hours='24',backup_keep='30',backup_directory='',drive_enabled='0',drive_directory='',drive_entries='0',stock_baseline=[])

def load(store,cid):
    store.get('company','',cid)
    try:data=store.get('business_settings',cid,'business-'+cid)
    except ValueError:data={}
    return dict(copy.deepcopy(DEFAULTS),**data)

def directory(value,label):
    value=str(value).strip()
    if value and (not Path(value).is_absolute() or not Path(value).is_dir()):raise ValueError(label+': escolha uma pasta absoluta existente neste computador.')
    return value

def save(store,cid,data):
    old=load(store,cid);out=dict(old)
    for k in ('stock_enabled','backup_enabled','drive_enabled','drive_entries'):
        out[k]=str(data.get(k,old[k]))
        if out[k] not in ('0','1'):raise ValueError('Escolha Sim ou Não: '+k)
    for k,low,high in [('backup_hours',1,720),('backup_keep',2,365)]:
        try:v=int(str(data.get(k,old[k])))
        except ValueError:raise ValueError('Intervalo/quantidade de backups inválido.')
        if not low<=v<=high:raise ValueError('Intervalo/quantidade de backups fora do limite.')
        out[k]=str(v)
    for k,label in [('backup_directory','Pasta de backup'),('drive_directory','Pasta sincronizada do Google Drive')]:
        out[k]=directory(data.get(k,old[k]),label)
    if out['drive_enabled']=='1' and not out['drive_directory']:raise ValueError('Informe a pasta sincronizada do Google Drive.')
    if old['stock_enabled']!='1' and out['stock_enabled']=='1':
        # O saldo anterior deve ser informado; ativar não lança notas antigas sem revisão.
        out['stock_baseline']=[r[0] for r in store.db.execute("SELECT id FROM fiscal_documents WHERE company=? AND status IN ('AUTORIZADA','CANCELADA')",(cid,))]
        out['stock_started']=datetime.now(timezone.utc).isoformat()
    store.save('business_settings',out,cid,'business-'+cid);return out
