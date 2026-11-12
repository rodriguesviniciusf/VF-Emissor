"""Validação local agregada. Não envia, reserva numeração nem usa certificado."""
from dataclasses import dataclass
from datetime import datetime
import copy,re
from core import ADDRESS,valid_document,number,calculate,consumer_final_error

@dataclass(frozen=True)
class Issue:
    field:str
    message:str

FIELDS={'xNome':'Nome','CNPJCPF':'CPF/CNPJ','xLgr':'Logradouro','nro':'Número','xBairro':'Bairro','cMun':'Código IBGE','xMun':'Município','UF':'UF','CEP':'CEP','IE':'Inscrição estadual'}
UF_IBGE=dict(zip('RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF'.split(),
                '11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53'.split()))
def validate_note(company,recipient,note,deep=True):
    issues=[]
    def add(field,message):issues.append(Issue(field,message))
    for prefix,party in [('company',company),('recipient',recipient)]:
        if not party:
            add(prefix,'Selecione o destinatário.' if prefix=='recipient' else 'Entre na empresa emitente.');continue
        for field in ('xNome','CNPJCPF')+ADDRESS+(('IE',) if prefix=='company' else ()):
            if not str(party.get(field,'')).strip():add(prefix+'.'+field,FIELDS.get(field,field)+': preenchimento obrigatório.')
        if party.get('CNPJCPF') and not valid_document(party['CNPJCPF']):add(prefix+'.CNPJCPF','CPF/CNPJ inválido.')
        uf=str(party.get('UF','')).strip().upper();mun=str(party.get('cMun','')).strip()
        if uf and uf not in UF_IBGE:add(prefix+'.UF','UF inválida.')
        if mun and (not re.fullmatch('[0-9]{7}',mun) or not mun.startswith(UF_IBGE.get(uf,'?'))):add(prefix+'.cMun','Código IBGE incompatível com a UF ou fora do formato de 7 dígitos.')
        if party.get('CEP') and not re.fullmatch('[0-9]{8}',str(party['CEP'])):add(prefix+'.CEP','CEP deve conter 8 dígitos.')
        if prefix=='recipient' and party.get('indIEDest','9')=='1' and not party.get('IE'):add(prefix+'.IE','Destinatário contribuinte precisa de IE.')
    if recipient:
        consumer_error=consumer_final_error(recipient,note)
        if consumer_error:add('final',consumer_error)
    for key,label,lo,hi in [('series','Série',0,999),('number','Número',1,999999999)]:
        try:
            if not re.fullmatch('[0-9]+',str(note.get(key,''))) or not lo<=int(note[key])<=hi:raise ValueError()
        except (ValueError,KeyError):add(key,label+' inválido.')
    if not str(note.get('nature','')).strip():add('nature','Informe a natureza da operação.')
    if note.get('destination','1') not in ('1','2'):add('destination','Destino deve ser interno ou interestadual.')
    if note.get('operation','1') not in ('0','1'):add('operation','Selecione entrada ou saída.')
    if note.get('purpose','1') not in ('1','2','3','4'):add('purpose','Finalidade inválida.')
    refs=[v.strip() for v in str(note.get('references','')).replace(';',',').split(',') if v.strip()]
    if note.get('has_reference','0')=='1' or note.get('purpose','1') in ('2','4'):
        if not refs:add('references','Importe o XML da nota de origem para preencher a referência automaticamente.')
    for key in refs:
        valid=bool(re.fullmatch('[0-9]{44}',key))
        if valid:
            total=sum(int(c)*w for c,w in zip(key[:43][::-1],([2,3,4,5,6,7,8,9]*6)))
            dv=11-total%11;valid=int(key[-1])==(0 if dv>=10 else dv)
        if not valid:add('references','XML de origem: a chave referenciada não é válida. Remova a referência e importe novamente o XML autorizado.')
    if refs and note.get('has_reference','0')!='1':add('has_reference','Marque Sim em documento referenciado para incluir as chaves no XML.')
    if len(refs)>500:add('references','Limite de 500 documentos referenciados.')
    from normal_fiscal import effective_payment
    if note.get('purpose','1') in ('3','4') and effective_payment(note)!='90':add('payment','Ajuste/devolução: selecione 90 — sem pagamento.')
    if company and recipient:
        expected='1' if company.get('UF','').strip().upper()==recipient.get('UF','').strip().upper() else '2'
        if note.get('destination','1')!=expected:add('destination','Destino da operação não corresponde às UFs do emitente e destinatário.')
    if not note.get('items'):add('items','Adicione ao menos um produto.')
    for index,item in enumerate(note.get('items',[])):
        base='item.'+str(index)+'.';rule=item.get('rule',{});product=item.get('product',{})
        for field,label in [('code','Código'),('name','Descrição'),('unit','Unidade')]:
            if not product.get(field):add(base+'product.'+field,label+' do produto obrigatório.')
        if not re.fullmatch('[0-9]{8}',product.get('NCM','')):add(base+'product.NCM','NCM deve ter 8 dígitos.')
        if rule.get('reviewed')!='1':add(base+'rule.reviewed','Revise e confirme a tributação deste item.')
        cfop=rule.get('CFOP','');prefix=('1' if note.get('destination','1')=='1' else '2') if note.get('operation','1')=='0' else ('5' if note.get('destination','1')=='1' else '6')
        if not re.fullmatch(prefix+'[0-9]{3}',cfop):add(base+'rule.CFOP','CFOP incompatível com entrada/saída e destino: deve começar com '+prefix+'.')
        from cfop_catalog import cfop_errors
        for message in cfop_errors(cfop,note):add(base+'rule.CFOP',message)
        if (company or {}).get('CRT')=='1' and recipient and recipient.get('indIEDest','9')=='9' and note.get('operation','1')=='1' and rule.get('icms_code') not in ('102','103','300','400','500') and cfop not in ('5912','5913','5915','5916','6915','6916'):
            add(base+'rule.icms_code','Destinatário não contribuinte: confira o CSOSN permitido para a operação e as exceções aplicáveis.')
        for key in ('quantity','price','discount'):
            try:
                value=number(item.get(key,''))
                if value<0 or (key=='quantity' and value<=0):raise ValueError()
                if key=='quantity' and value!=value.quantize(number('0.0001')):add(base+key,'Quantidade aceita até 4 casas decimais.')
                if key=='price' and value!=value.quantize(number('0.0000000001')):add(base+key,'Preço aceita até 10 casas decimais.')
            except ValueError:add(base+key,'Valor inválido em '+key+'.')
        try:calculate(item,rule,(company or {}).get('CRT','1'))
        except (ValueError,KeyError) as exc:
            msg=str(exc)
            if hasattr(exc,'field'):
                add(base+('product.CEST' if exc.field=='CEST' else 'taxes.'+exc.field),msg);continue
            field='rule.icms_code' if 'CSOSN' in msg or 'CST 00' in msg else 'rule.pis_code' if 'PIS' in msg else 'rule.cofins_code' if 'COFINS' in msg else 'rule.pis_rate' if 'pis_rate' in msg else 'rule.cofins_rate' if 'cofins_rate' in msg else 'discount' if 'Desconto' in msg else 'quantity'
            if 'Cálculo manual: informe ' in msg:field='manual.'+msg.split('informe ',1)[1].split(',',1)[0]
            elif 'manual diverge' in msg:field='manual.'+('icms' if 'ICMS' in msg else 'pis' if 'PIS' in msg else 'cofins')
            add(base+field,msg)
    for field,label,limit in [('info','Informações complementares',5000),('info_fisco','Informações ao Fisco',2000),('purchase_order','Pedido',60),('purchase_contract','Contrato',60),('purchase_commitment','Empenho',22)]:
        if len(str(note.get(field,'')))>limit:add(field,label+': limite de '+str(limit)+' caracteres.')
    if company and company.get('CRT') not in ('1','3'):add('company.CRT','Selecione CRT 1 (Simples Nacional) ou CRT 3 (Regime Normal).')
    from note_finance import finance_errors
    for field,message in finance_errors(note):add(field,message)
    from tax_scenarios import validate_context,TaxError
    try:validate_context(company,recipient,note)
    except ValueError as exc:
        if not isinstance(exc,TaxError):add('items',str(exc));exc=None
        if exc is not None:
            affected=getattr(exc,'item_index',next((i for i,item in enumerate(note.get('items',[])) if item.get('taxes') or item.get('rule',{}).get('icms_code') in ('201','202','203')),0))
            add('item.'+str(affected)+'.taxes.'+exc.field,str(exc))
    from interstate import issues as interstate_issues
    for issue in interstate_issues(company,recipient,note):add(issue['field'],issue['message'])
    if deep and not issues:
        from fiscal import build_unsigned,unsigned_schema_issues,TZ
        checked=copy.deepcopy(note);checked.setdefault('issued_at',datetime.now(TZ).isoformat(timespec='seconds'))
        try:
            unsigned,_,_=build_unsigned(company,recipient,checked)
            for field,message in unsigned_schema_issues(unsigned):add(field,'XML: '+message)
        except (ValueError,KeyError) as exc:add('references' if 'referenciar a si mesma' in str(exc) else 'items',str(exc))
    labels={'icms_base':'base de ICMS','pis_base':'base de PIS','cofins_base':'base de COFINS','quantity':'quantidade','price':'preço unitário','discount':'desconto','pis_rate':'alíquota de PIS','cofins_rate':'alíquota de COFINS','icms_rate':'alíquota de ICMS'}
    return [Issue(i.field,replace_labels(i.message,labels)) for i in issues]

def replace_labels(message,labels):
    for source,target in labels.items():message=message.replace(source,target)
    return message
