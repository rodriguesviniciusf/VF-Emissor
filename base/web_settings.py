"""Preferências por empresa, aplicadas somente aos novos documentos."""
import copy, re
from core import valid_document, document

DEFAULTS=dict(nature='VENDA DE MERCADORIA',operation='1',destination='1',presence='1',purpose='1',final='1',payment='01',transport_mode='9',CFOP='5102',info='',info_fisco='',rule_id='',exclude_icms='0',icms_include_ipi='0',authorized_xml='',cMunFG='')
ENUMS=dict(operation={'0','1'},destination={'1','2'},presence={'0','1','2','3','5','9'},purpose={'1','2','3','4'},final={'0','1'},transport_mode=set('012349'),exclude_icms={'0','1'},icms_include_ipi={'0','1'})
ACCOUNTANT_FIELDS='name cpf crc cnpj email phone CEP UF xMun xLgr nro xCpl xBairro'.split()

def load_settings(store,cid):
    try:data=store.get('settings',cid,'preferences-'+cid)
    except ValueError:
        try:data=store.get('settings',cid,'preferences')
        except ValueError:data={}
    return dict(defaults=dict(DEFAULTS,**data.get('defaults',{})),accountant=data.get('accountant',{}))

def save_settings(store,cid,section,data):
    current=load_settings(store,cid)
    if section=='defaults':
        out={k:str(data.get(k,current['defaults'][k])).strip() for k in DEFAULTS}
        for k,options in ENUMS.items():
            if out[k] not in options:raise ValueError('Opção inválida: '+k)
        if not out['nature'] or len(out['nature'])>60:raise ValueError('Natureza da operação: preencha até 60 caracteres.')
        if not re.fullmatch('[1256][0-9]{3}',out['CFOP']):raise ValueError('CFOP padrão: informe quatro dígitos para operação interna ou interestadual.')
        if not re.fullmatch('[0-9]{2}',out['payment']):raise ValueError('Meio de pagamento: informe o código com dois dígitos.')
        if out['cMunFG'] and not re.fullmatch('[0-9]{7}',out['cMunFG']):raise ValueError('Município do fato gerador: informe o código IBGE de sete dígitos.')
        if out['rule_id']:store.get('rule',cid,out['rule_id'])
        docs=[document(v) for v in re.split('[,;\\s]+',out['authorized_xml']) if v]
        if len(docs)>10 or any(not valid_document(v) for v in docs):raise ValueError('Informe até dez CPF/CNPJ válidos autorizados a acessar o XML.')
        out['authorized_xml']=','.join(dict.fromkeys(docs))
        for k in ('info','info_fisco'):
            if len(out[k])>(5000 if k=='info' else 2000):raise ValueError('Informações adicionais excedem o tamanho permitido.')
    elif section=='accountant':
        out={k:str(data.get(k,'')).strip() for k in ACCOUNTANT_FIELDS}
        for k,size in [('cpf',11),('cnpj',14)]:
            if out[k]:
                out[k]=document(out[k])
                if len(out[k])!=size or not valid_document(out[k]):raise ValueError(k.upper()+' do contador inválido.')
        if out['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',out['email']):raise ValueError('E-mail do contador inválido.')
        if any(len(v)>200 for v in out.values()):raise ValueError('Dados do contador excedem o tamanho permitido.')
    else:raise ValueError('Seção de configurações inválida.')
    current[section]=out;store.save('settings',current,cid,'preferences-'+cid)
    with store.db:store.db.execute("DELETE FROM records WHERE kind='settings' AND company=? AND id='preferences'",(cid,))
    return current

def new_note_defaults(store,cid):
    data=copy.deepcopy(load_settings(store,cid)['defaults'])
    for k in ('CFOP','rule_id','exclude_icms','icms_include_ipi'):data.pop(k,None)
    return data
