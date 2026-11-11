"""Retornos reais da SEFAZ e atalhos de revisão; nenhuma retransmissão implícita."""
import json,re
from fiscal import FiscalStore
from note_validation import validate_note

def field_from_reason(reason):
    lower=reason.casefold();item=re.search(r'nitem\s*[:=]\s*(\d+)',reason,re.I);index=max(0,int(item.group(1))-1) if item else 0
    path='item.'+str(index)+'.'
    if 'ncm' in lower:return path+'product.NCM'
    if 'cfop' in lower:return path+'rule.CFOP'
    if 'cean' in lower or 'gtin' in lower:return path+'product.gtin'
    if 'cest' in lower:return path+'product.CEST'
    if 'cclass' in lower:return path+'normal_groups.IBSCBS.cClassTrib'
    if 'cst' in lower or 'csosn' in lower:return path+'rule.icms_code'
    if 'inscri' in lower and 'estadual' in lower:return ('recipient.' if 'destinat' in lower else 'company.')+'IE'
    if 'cnpj' in lower or 'cpf' in lower:return ('recipient.' if 'destinat' in lower else 'company.')+'CNPJCPF'
    if 'cep' in lower:return ('recipient.' if 'destinat' in lower else 'company.')+'CEP'
    if 'munic' in lower:return ('recipient.' if 'destinat' in lower else 'company.')+'cMun'
    if 'emiss' in lower and ('data' in lower or 'hora' in lower):return 'issued_at'
    if 'pagamento' in lower:return 'payment'
    if 'destinat' in lower:return 'recipient'
    if 'total' in lower:return 'items'
    return ''

def entries(store,cid,env):
    result=[]
    for d in FiscalStore(store).list(cid):
        if d['environment']!=env or d['status'] not in ('REJEITADA','INCERTA','PROCESSANDO','ENVIANDO'):continue
        snap=json.loads(d['snapshot']);reason=d['reason'] or 'Consulte a situação antes de tentar nova transmissão.'
        issues=[]
        if d['status']=='REJEITADA':
            field=field_from_reason(reason)
            if field:issues.append(dict(field=field,message=reason,suggested=True))
            try:n=store.get('note',cid,d['source']);rec=store.get('recipient',cid,n.get('recipient_id',''));co=store.get('company','',cid)
            except ValueError:co=snap['company'];rec=snap.get('recipient',{});n=snap['note']
            issues.extend(dict(field=i.field,message=i.message,suggested=False) for i in validate_note(co,rec,n))
        result.append(dict(id=d['id'],source=d['source'],number=str(d['number']),series=str(d['series']),status=d['status'],reason=reason,recipient=snap.get('recipient',{}).get('xNome',''),issues=issues,updated=d['updated'],editable=d['status']=='REJEITADA'))
    return sorted(result,key=lambda d:d['updated'],reverse=True)
